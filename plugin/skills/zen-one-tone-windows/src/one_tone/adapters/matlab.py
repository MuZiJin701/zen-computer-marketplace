from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable, Mapping

from ..inventory import inventory_groups, inventory_report
from ..palette import _oklch_color, _oklch_components, contrast_ratio, parse_hex_color
from ..plan import Plan
from ..storage import atomic_write_text
from .base import AdapterResult, close_windows_process, create_kernel32, field_capabilities, probe_windows_process, verify_unredirected_path

try:
    import winreg
except ImportError:  # pragma: no cover - production target is Windows.
    winreg = None

MATLAB_MLSETTINGS_SCHEMA_V1 = "matlab-mlsettings-v1"
_EXPECTED_SCHEMA_JSON = "com.mathworks/settings/jsonschema/1-1-0"
_MIN_RELEASE = (2025, 0)
_RELEASE_PATTERN = re.compile(r"^R(\d{4})([ab])$", re.IGNORECASE)

_SCHEMA_ENTRY = "fsroot/schema.json"
_MANIFEST_ENTRY = "metadata/filesystemManifest.xml"
_RELEASE_INFO_ENTRY = "metadata/mwcorePropertiesReleaseInfo.xml"
_MANIFEST_NS = "http://schemas.mathworks.com/package/2013/filesystemManifest"
_MANIFEST_ROOT_TAG = f"{{{_MANIFEST_NS}}}fileEntries"
_MANIFEST_ENTRY_TAG = f"{{{_MANIFEST_NS}}}fileEntry"
ET.register_namespace("", _MANIFEST_NS)

_APPEARANCE_GROUP = "/settingstree/matlab/appearance"
_COLORS_GROUP = "/settingstree/matlab/colors"
_COMMANDWINDOW_GROUP = "/settingstree/matlab/colors/commandwindow"
_PROGRAMMINGTOOLS_GROUP = "/settingstree/matlab/colors/programmingtools"
_DISPLAYSETTINGS_GROUP = "/settingstree/matlab/editor/displaysettings"
_LINELIMIT_GROUP = "/settingstree/matlab/editor/displaysettings/linelimit"

_DESKTOP_COLOR_ROLES: tuple[tuple[str, str], ...] = (
    ("BackgroundColor", "surface"),
    ("ForegroundColor", "foreground"),
)

_SYNTAX_COLOR_ROLES: tuple[tuple[str, str], ...] = (
    ("CodeColor", "foreground"),
    ("NormalColor", "foreground"),
    ("KeywordColor", "info_text"),
    ("CommentColor", "muted_foreground"),
    ("StringColor", "purple_text"),
    ("UnterminatedStringColor", "error_text"),
    ("SystemCommandColor", "warning_text"),
    ("ValidationSectionColor", "cyan_text"),
    ("SyntaxErrorColor", "error_text"),
    ("ErrorColor", "error_text"),
    ("WarningColor", "warning_text"),
    ("HyperlinkColor", "accent_text"),
    ("CodeAnalyzerWarningColor", "warning_text"),
    ("CodeAnalyzerInfoColor", "info_text"),
    ("AutofixHighlightColor", "surface_subtle"),
    ("VariableHighlightColor", "selection_background"),
    ("VariablesWithSharedScopeColor", "cyan_text"),
    ("HighlightCurrentLineColor", "surface_raised"),
    ("LineColor", "border"),
)

_SYNTAX_NON_TEXT_KEYS = frozenset({
    "AutofixHighlightColor",
    "VariableHighlightColor",
    "HighlightCurrentLineColor",
    "LineColor",
})

_LIGHT_RGB_MIRROR_GROUPS: tuple[tuple[str, bool, tuple[str, ...]], ...] = (
    (
        _COLORS_GROUP,
        True,
        (
            "KeywordColor",
            "CommentColor",
            "StringColor",
            "UnterminatedStringColor",
            "SystemCommandColor",
            "ValidationSectionColor",
            "SyntaxErrorColor",
        ),
    ),
    (
        _COMMANDWINDOW_GROUP,
        True,
        (
            "ErrorColor",
            "WarningColor",
            "HyperlinkColor",
        ),
    ),
    (
        _PROGRAMMINGTOOLS_GROUP,
        True,
        (
            "CodeAnalyzerWarningColor",
            "CodeAnalyzerInfoColor",
            "AutofixHighlightColor",
            "VariableHighlightColor",
            "VariablesWithSharedScopeColor",
        ),
    ),
    (
        _DISPLAYSETTINGS_GROUP,
        True,
        ("HighlightCurrentLineColor",),
    ),
    (
        _LINELIMIT_GROUP,
        True,
        ("LineColor",),
    ),
)

_MANAGED_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    _APPEARANCE_GROUP: ("MATLABTheme",),
    _COLORS_GROUP: (
        "DesktopColors",
        "SyntaxHighlightingColors",
        "KeywordColor",
        "CommentColor",
        "StringColor",
        "UnterminatedStringColor",
        "SystemCommandColor",
        "ValidationSectionColor",
        "SyntaxErrorColor",
    ),
    _COMMANDWINDOW_GROUP: ("ErrorColor", "WarningColor", "HyperlinkColor"),
    _PROGRAMMINGTOOLS_GROUP: (
        "CodeAnalyzerWarningColor",
        "CodeAnalyzerInfoColor",
        "AutofixHighlightColor",
        "VariableHighlightColor",
        "VariablesWithSharedScopeColor",
    ),
    _DISPLAYSETTINGS_GROUP: ("HighlightCurrentLineColor",),
    _LINELIMIT_GROUP: ("LineColor",),
}

_JSON_MAP_MANAGED_KEYS: dict[str, tuple[str, ...]] = {
    "DesktopColors": tuple(key for key, _ in _DESKTOP_COLOR_ROLES),
    "SyntaxHighlightingColors": tuple(key for key, _ in _SYNTAX_COLOR_ROLES),
}

_GROUP_VISIBILITY: dict[str, bool] = {
    _APPEARANCE_GROUP: False,
    _COLORS_GROUP: True,
    _COMMANDWINDOW_GROUP: True,
    _PROGRAMMINGTOOLS_GROUP: True,
    _DISPLAYSETTINGS_GROUP: True,
    _LINELIMIT_GROUP: True,
}


def parse_matlab_release(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = _RELEASE_PATTERN.match(value.strip())
    if not match:
        return None
    year = int(match.group(1))
    half = 0 if match.group(2).lower() == "a" else 1
    return year, half


def normalize_matlab_release(value: str | None) -> str | None:
    parsed = parse_matlab_release(value)
    if parsed is None:
        return None
    return f"R{parsed[0]}{'a' if parsed[1] == 0 else 'b'}"


def is_supported_matlab_release(value: str | None) -> bool:
    parsed = parse_matlab_release(value)
    return parsed is not None and parsed >= _MIN_RELEASE


def _resolve_abs_path(path: Path) -> Path:
    return path.expanduser().resolve()


def _verify_unredirected_path(frozen_path: Path) -> tuple[bool, Path | None, str]:
    """Ensure a frozen absolute path has not been redirected via a symlink or junction."""
    return verify_unredirected_path(frozen_path, "MATLAB settings")


_create_kernel32 = create_kernel32


def probe_matlab_process() -> tuple[str, str]:
    """Probe whether MATLAB.exe is running on Windows (fail-closed -> 'unknown')."""
    if sys.platform != "win32":
        return "stopped", "non-windows host"
    return probe_windows_process("MATLAB.exe", kernel32_factory=_create_kernel32)


def is_matlab_running() -> bool:
    """Return True if MATLAB.exe is running or process state cannot be verified (fail-closed)."""
    status, _ = probe_matlab_process()
    return status != "stopped"


def _read_version_info_release(matlab_root: Path) -> str | None:
    version_file = matlab_root / "VersionInfo.xml"
    if not version_file.is_file():
        return None
    try:
        root = ET.fromstring(version_file.read_bytes())
    except (OSError, ET.ParseError):
        return None
    node = root.find("release")
    return normalize_matlab_release(node.text if node is not None else None)


def _registry_matlab_roots() -> list[tuple[str, Path]]:
    if winreg is None:
        return []
    found: list[tuple[str, Path]] = []
    for base_key in (r"SOFTWARE\MathWorks\MATLAB", r"SOFTWARE\WOW6432Node\MathWorks\MATLAB"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_key) as key:
                index = 0
                while True:
                    try:
                        subname = winreg.EnumKey(key, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, subname) as subkey:
                            root_str = winreg.QueryValueEx(subkey, "MATLABROOT")[0]
                    except OSError:
                        continue
                    if not isinstance(root_str, str) or not root_str.strip():
                        continue
                    root_path = _resolve_abs_path(Path(root_str.strip()))
                    release = _read_version_info_release(root_path) or normalize_matlab_release(subname)
                    if release:
                        found.append((release, root_path))
        except OSError:
            continue
    return found


def _zip_rel_for_group(group_path: str) -> str:
    return f"fsroot{group_path}/settings.json"


def _decode_str_value(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, str) else None


def _parse_json_map_strict(raw: Any) -> tuple[bool, dict[str, Any]]:
    """Strictly parse a MATLAB JSON-encoded string setting into a dict (empty string -> {})."""
    text = _decode_str_value(raw)
    if text is None:
        return False, {}
    if text == "":
        return True, {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False, {}
    if not isinstance(parsed, dict):
        return False, {}
    for mode in ("light", "dark"):
        if mode in parsed and not isinstance(parsed[mode], dict):
            return False, {}
    return True, parsed


def _decode_rgb_value(raw: Any) -> list[int] | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        isinstance(parsed, dict)
        and parsed.get("mwtype") == "int32"
        and parsed.get("mwsize") == [1, 3]
        and isinstance(parsed.get("mwdata"), list)
        and len(parsed["mwdata"]) == 3
        and all(isinstance(channel, int) and not isinstance(channel, bool) for channel in parsed["mwdata"])
    ):
        return list(parsed["mwdata"])
    return None


def _parse_and_validate_manifest(
    manifest_bytes: bytes,
    archive_names: set[str],
) -> tuple[bool, ET.Element | None, dict[str, ET.Element], str]:
    try:
        root = ET.fromstring(manifest_bytes)
    except (ET.ParseError, LookupError, ValueError) as error:
        return False, None, {}, f"Invalid filesystemManifest.xml XML: {error}"
    if root.tag != _MANIFEST_ROOT_TAG:
        return False, None, {}, f"Unexpected filesystemManifest.xml root tag: {root.tag}"
    managed_file_targets = {
        f"{group_path}/settings.json": f"/{_zip_rel_for_group(group_path)}"
        for group_path in _MANAGED_GROUP_KEYS
    }
    manifest_map: dict[str, ET.Element] = {}
    for child in root:
        if child.tag != _MANIFEST_ENTRY_TAG:
            return False, None, {}, f"Unexpected manifest child tag: {child.tag}"
        name = child.attrib.get("name")
        entry_type = child.attrib.get("type")
        content = child.attrib.get("content")
        if not name or not name.startswith("/"):
            return False, None, {}, f"Malformed manifest entry name: {name!r}"
        if entry_type not in {"File", "Folder"}:
            return False, None, {}, f"Malformed manifest entry type for {name}: {entry_type!r}"
        if content is None:
            return False, None, {}, f"Missing manifest content attribute for {name}"
        if name in manifest_map:
            return False, None, {}, f"Duplicate manifest entry: {name}"
        if entry_type == "File":
            if not content.startswith("/"):
                return False, None, {}, f"Invalid manifest file content path for {name}: {content!r}"
            if content.lstrip("/") not in archive_names:
                return False, None, {}, f"Manifest references missing archive entry: {content}"
        if name in managed_file_targets:
            expected_content = managed_file_targets[name]
            if entry_type != "File" or content != expected_content:
                return (
                    False,
                    None,
                    {},
                    f"Manifest entry for {name} has inconsistent target {content!r} (expected File -> {expected_content!r})",
                )
        if name in _MANAGED_GROUP_KEYS and entry_type != "Folder":
            return False, None, {}, f"Manifest folder entry for {name} has unexpected type {entry_type!r}"
        manifest_map[name] = child
    return True, root, manifest_map, "ok"


def _read_and_validate_group_doc(
    entries: Mapping[str, tuple[zipfile.ZipInfo, bytes]],
    group_path: str,
) -> tuple[bool, dict[str, Any] | None, dict[str, dict[str, Any]], str]:
    zip_rel = _zip_rel_for_group(group_path)
    if zip_rel not in entries:
        return True, None, {}, "absent"
    try:
        doc = json.loads(entries[zip_rel][1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return False, None, {}, f"Corrupted JSON in {zip_rel}: {error}"
    if not isinstance(doc, dict):
        return False, None, {}, f"Settings group {zip_rel} must be a JSON object"
    if doc.get("path") != group_path:
        return False, None, {}, f"Settings group {zip_rel} declares path {doc.get('path')!r}, expected {group_path!r}"
    items = doc.get("settings")
    if not isinstance(items, list):
        return False, None, {}, f"Settings group {zip_rel} has non-list 'settings'"
    by_name: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            return False, None, {}, f"Settings group {zip_rel} contains malformed setting item"
        name = item["name"]
        if name in by_name:
            return False, None, {}, f"Settings group {zip_rel} contains duplicate setting {name!r}"
        if name in _MANAGED_GROUP_KEYS.get(group_path, ()):
            has_value = item.get("hasValue")
            if not isinstance(has_value, bool):
                return (
                    False,
                    None,
                    {},
                    f"Invalid hasValue flag for {group_path}.{name}: expected bool",
                )
            expected_is_vector = not (
                (group_path == _APPEARANCE_GROUP and name == "MATLABTheme")
                or (group_path == _COLORS_GROUP and name in _JSON_MAP_MANAGED_KEYS)
            )
            if item.get("isVector") is not expected_is_vector:
                return (
                    False,
                    None,
                    {},
                    f"Invalid isVector flag for {group_path}.{name}: expected {expected_is_vector}",
                )
            if has_value is True:
                if group_path == _COLORS_GROUP and name in _JSON_MAP_MANAGED_KEYS:
                    ok_map, _ = _parse_json_map_strict(item.get("value"))
                    if not ok_map:
                        return False, None, {}, f"Corrupted JSON color map in {group_path}.{name}"
                elif group_path == _APPEARANCE_GROUP and name == "MATLABTheme":
                    if _decode_str_value(item.get("value")) is None:
                        return False, None, {}, f"Corrupted string setting in {group_path}.{name}"
                elif expected_is_vector:
                    if _decode_rgb_value(item.get("value")) is None:
                        return False, None, {}, f"Corrupted RGB vector setting in {group_path}.{name}"
        by_name[name] = dict(item)
    return True, doc, by_name, "ok"


class _LiveProcessBlockedError(RuntimeError):
    """Raised when the final pre-replace live-process guard blocks writing."""


class _WriteTargetRedirectedError(RuntimeError):
    """Raised when the target settings path is redirected before atomic replace."""


_ARCHIVE_READ_ERRORS = (
    OSError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    ET.ParseError,
    LookupError,
    NotImplementedError,
    RuntimeError,
    zlib.error,
    EOFError,
)


def _read_zip_entries_strict(raw_bytes: bytes) -> tuple[bool, dict[str, tuple[zipfile.ZipInfo, bytes]], str]:
    entries: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as archive:
        for info in archive.infolist():
            if info.filename in entries:
                return False, {}, f"Duplicate ZIP member in MATLAB settings archive: {info.filename}"
            entries[info.filename] = (info, archive.read(info))
    return True, entries, "ok"


def _load_and_validate_mlsettings(
    path: Path,
) -> tuple[
    bool,
    bytes,
    dict[str, tuple[zipfile.ZipInfo, bytes]],
    ET.Element | None,
    dict[str, ET.Element],
    str | None,
    str,
]:
    if not path.is_file():
        return False, b"", {}, None, {}, None, f"MATLAB settings file not found: {path}"
    try:
        raw_bytes = path.read_bytes()
    except OSError as error:
        return False, b"", {}, None, {}, None, f"Failed to read MATLAB settings archive {path}: {error}"
    if not zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        return False, b"", {}, None, {}, None, f"MATLAB settings file is not a valid OPC ZIP archive: {path}"
    try:
        ok_zip, entries, zip_err = _read_zip_entries_strict(raw_bytes)
        if not ok_zip:
            return False, b"", {}, None, {}, None, f"{zip_err} ({path})"
        names = set(entries)
        if _SCHEMA_ENTRY not in names or _MANIFEST_ENTRY not in names:
            return False, b"", {}, None, {}, None, f"MATLAB settings archive is missing required schema or manifest: {path}"
        schema = entries[_SCHEMA_ENTRY][1].decode("utf-8", errors="replace").strip()
        if schema != _EXPECTED_SCHEMA_JSON:
            return False, b"", {}, None, {}, None, f"Unsupported MATLAB settings schema '{schema}' in {path}"
        ok_manifest, manifest_root, manifest_map, manifest_err = _parse_and_validate_manifest(entries[_MANIFEST_ENTRY][1], names)
        if not ok_manifest or manifest_root is None:
            return False, b"", {}, None, {}, None, f"Invalid MATLAB settings manifest in {path}: {manifest_err}"
        for group_path in _MANAGED_GROUP_KEYS:
            ok_group, _, _, group_err = _read_and_validate_group_doc(entries, group_path)
            if not ok_group:
                return False, b"", {}, None, {}, None, f"Invalid MATLAB settings group in {path}: {group_err}"
        release: str | None = None
        if _RELEASE_INFO_ENTRY in names:
            try:
                info_root = ET.fromstring(entries[_RELEASE_INFO_ENTRY][1])
                node = info_root.find("release")
                raw_release = node.text.strip() if (node is not None and node.text) else ""
            except (ET.ParseError, LookupError, ValueError):
                return False, b"", {}, None, {}, None, f"Corrupted release info XML in {path}"
            if not raw_release:
                return False, b"", {}, None, {}, None, f"Missing or empty <release> in {_RELEASE_INFO_ENTRY} for {path}"
            release = normalize_matlab_release(raw_release)
            if release is None:
                return False, b"", {}, None, {}, None, f"Invalid MATLAB release {raw_release!r} in {_RELEASE_INFO_ENTRY} for {path}"
        else:
            release = normalize_matlab_release(path.parent.name)
    except _ARCHIVE_READ_ERRORS as error:
        return False, b"", {}, None, {}, None, f"Failed to read MATLAB settings archive {path}: {error}"
    if release is None:
        return False, b"", {}, None, {}, None, f"Unable to determine MATLAB release for {path}"
    if not is_supported_matlab_release(release):
        return False, b"", {}, None, {}, release, f"MATLAB {release} uses legacy desktop architecture; R2025a or newer is required"
    return True, raw_bytes, entries, manifest_root, manifest_map, release, "verified"


def _inspect_mlsettings(path: Path) -> tuple[bool, str | None, str]:
    ok, _, _, _, _, release, reason = _load_and_validate_mlsettings(path)
    return ok, release, reason


def discover_matlab_instance(
    *,
    appdata: Path | None = None,
    explicit_settings: Path | None = None,
    prefdir: Path | None = None,
    registry_roots: list[tuple[str, Path]] | None = None,
) -> dict[str, Any]:
    """Discover a single Active Target instance for MATLAB desktop (>= R2025a)."""
    if explicit_settings is not None:
        resolved_explicit = _resolve_abs_path(explicit_settings)
        ok, release, reason = _inspect_mlsettings(resolved_explicit)
        if not ok:
            return {"status": "skipped", "reason": reason}
        return {
            "status": "ok",
            "settings_path": str(resolved_explicit),
            "release": release,
            "source": "explicit",
        }

    if prefdir is not None:
        candidate = _resolve_abs_path(prefdir) / "matlab.mlsettings"
        ok, release, reason = _inspect_mlsettings(candidate)
        if not ok:
            return {"status": "skipped", "reason": reason}
        return {
            "status": "ok",
            "settings_path": str(candidate),
            "release": release,
            "source": "prefdir",
        }

    resolved_appdata = _resolve_abs_path(appdata or Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")))
    matlab_roaming = resolved_appdata / "MathWorks" / "MATLAB"

    candidates_by_release: dict[tuple[int, int], tuple[str, Path, Path | None]] = {}
    legacy_releases: list[str] = []

    roots = _registry_matlab_roots() if registry_roots is None else list(registry_roots)
    for release, root_path in roots:
        parsed = parse_matlab_release(release)
        if parsed is None:
            continue
        if parsed < _MIN_RELEASE:
            legacy_releases.append(release)
            continue
        settings_path = (matlab_roaming / release / "matlab.mlsettings").resolve()
        candidates_by_release[parsed] = (release, settings_path, _resolve_abs_path(root_path))

    if matlab_roaming.is_dir():
        for child in matlab_roaming.iterdir():
            if not child.is_dir():
                continue
            release = normalize_matlab_release(child.name)
            parsed = parse_matlab_release(release)
            if parsed is None or release is None:
                continue
            if parsed < _MIN_RELEASE:
                legacy_releases.append(release)
                continue
            if parsed not in candidates_by_release:
                candidates_by_release[parsed] = (release, (child / "matlab.mlsettings").resolve(), None)

    uninitialized: list[str] = []
    invalid_reasons: list[str] = []
    for parsed in sorted(candidates_by_release, reverse=True):
        release, settings_path, root_path = candidates_by_release[parsed]
        if not settings_path.is_file():
            uninitialized.append(release)
            continue
        ok, detected_release, reason = _inspect_mlsettings(settings_path)
        if ok and detected_release != release:
            invalid_reasons.append(
                f"MATLAB release mismatch in {settings_path}: expected {release}, archive declares {detected_release}"
            )
            continue
        if ok:
            instance: dict[str, Any] = {
                "status": "ok",
                "settings_path": str(settings_path),
                "release": detected_release or release,
                "source": "registry" if root_path is not None else "appdata",
            }
            if root_path is not None:
                instance["matlab_root"] = str(root_path)
            return instance
        invalid_reasons.append(reason)

    if uninitialized:
        return {
            "status": "skipped",
            "reason": f"MATLAB {uninitialized[0]} has not been initialized yet (matlab.mlsettings not found); launch MATLAB once first",
        }
    if invalid_reasons:
        return {"status": "skipped", "reason": invalid_reasons[0]}
    if legacy_releases:
        return {
            "status": "skipped",
            "reason": f"Only legacy MATLAB desktop ({legacy_releases[0]}) found; R2025a or newer is required",
        }
    return {"status": "skipped", "reason": "MATLAB installation or settings not found"}


def _mix_oklch(first: str, second: str, fraction: float) -> str:
    l1, c1, h1 = _oklch_components(first)
    l2, c2, h2 = _oklch_components(second)
    hue = h2 if c2 > 0.005 else h1
    return _oklch_color(hue, l1 + (l2 - l1) * fraction, c1 + (c2 - c1) * fraction)


def _ensure_contrast_on_backgrounds(
    color: str,
    backgrounds: tuple[str, ...],
    min_ratio: float,
    mode: str,
) -> str:
    if all(contrast_ratio(color, bg) >= min_ratio for bg in backgrounds):
        return color
    lightness, chroma, hue = _oklch_components(color)
    target_l = 0.04 if mode == "light" else 0.97
    for step in range(1, 61):
        frac = step / 60.0
        cand_l = lightness + (target_l - lightness) * frac
        cand_c = chroma * (1.0 - 0.35 * frac)
        candidate = _oklch_color(hue, cand_l, cand_c)
        if all(contrast_ratio(candidate, bg) >= min_ratio for bg in backgrounds):
            return candidate
    return "#121212" if mode == "light" else "#F2F2F2"


def _matlab_mode_colors(palette: Mapping[str, str], mode: str) -> tuple[dict[str, str], dict[str, str]]:
    """Build contrast-verified DesktopColors and SyntaxHighlightingColors for a Mode."""
    bg_surface = palette["surface"]
    bg_current_line = palette["surface_raised"]
    bg_autofix = palette["surface_subtle"]
    bg_variable = _mix_oklch(bg_surface, palette["selection_background"], 0.35)
    all_backgrounds = (bg_surface, bg_current_line, bg_autofix, bg_variable)

    primary_fg = _ensure_contrast_on_backgrounds(palette["foreground"], (bg_surface, bg_current_line), 7.0, mode)
    primary_fg = _ensure_contrast_on_backgrounds(primary_fg, all_backgrounds, 4.5, mode)

    desktop = {
        "BackgroundColor": bg_surface.lower(),
        "ForegroundColor": primary_fg.lower(),
    }

    syntax: dict[str, str] = {}
    for key, role in _SYNTAX_COLOR_ROLES:
        if key in {"CodeColor", "NormalColor"}:
            syntax[key] = primary_fg.lower()
        elif key == "HighlightCurrentLineColor":
            syntax[key] = bg_current_line.lower()
        elif key == "AutofixHighlightColor":
            syntax[key] = bg_autofix.lower()
        elif key == "VariableHighlightColor":
            syntax[key] = bg_variable.lower()
        elif key == "LineColor":
            syntax[key] = palette[role].lower()
        else:
            adjusted = _ensure_contrast_on_backgrounds(palette[role], all_backgrounds, 4.5, mode)
            syntax[key] = adjusted.lower()
    return desktop, syntax


def _rgb_list(hex_color: str) -> list[int]:
    return list(parse_hex_color(hex_color))


def _generated_values(plan: Plan) -> dict[str, Any]:
    values: dict[str, Any] = {
        "matlab.appearance.MATLABTheme": "System",
    }
    mode_syntax: dict[str, dict[str, str]] = {}
    for mode in ("light", "dark"):
        desktop, syntax = _matlab_mode_colors(plan.palette_for(mode), mode)
        mode_syntax[mode] = syntax
        for key, value in desktop.items():
            values[f"matlab.colors.DesktopColors.{mode}.{key}"] = value
        for key, value in syntax.items():
            values[f"matlab.colors.SyntaxHighlightingColors.{mode}.{key}"] = value
    light_syntax = mode_syntax["light"]
    for group_path, _, keys in _LIGHT_RGB_MIRROR_GROUPS:
        prefix = group_path.removeprefix("/settingstree/").replace("/", ".")
        for key in keys:
            values[f"{prefix}.{key}"] = _rgb_list(light_syntax[key])
    return values


def _setting_entry(name: str, value_str: str, *, visible: bool, is_vector: bool) -> dict[str, Any]:
    return {
        "attributes": {
            "readonly": False,
            "runtimeDefaultFcn": {},
            "settingValueValidator": {},
            "validationFcn": {},
            "visible": visible,
        },
        "hasValue": True,
        "isUserDefined": False,
        "isVector": is_vector,
        "name": name,
        "value": value_str,
    }


def _encode_str_value(text: str) -> str:
    return json.dumps(text, separators=(",", ":"))


def _encode_rgb_value(rgb: list[int]) -> str:
    return json.dumps({"mwdata": rgb, "mwsize": [1, 3], "mwtype": "int32"}, separators=(",", ":"))


def _new_group_doc(group_path: str, visible: bool) -> dict[str, Any]:
    return {
        "attributes": {
            "groupName": group_path.rstrip("/").split("/")[-1],
            "readonly": False,
            "validationFcn": {},
            "visible": visible,
        },
        "path": group_path,
        "settings": [],
    }


def _serialize_group_doc(doc: Mapping[str, Any]) -> bytes:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _serialize_manifest(root: ET.Element) -> bytes:
    children = sorted(list(root), key=lambda el: el.attrib.get("name", ""))
    root[:] = children
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n' + ET.tostring(root, encoding="utf-8")


def _atomic_write_zip(
    path: Path,
    original_entries: Mapping[str, tuple[zipfile.ZipInfo, bytes]],
    updated_files: Mapping[str, bytes],
    removed_files: set[str],
    manifest_bytes: bytes,
    *,
    pre_replace_check: Callable[[], tuple[bool, str]] | None = None,
) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            written: set[str] = set()
            for name, (info, data) in original_entries.items():
                if name in removed_files:
                    continue
                if name == _MANIFEST_ENTRY:
                    zout.writestr(name, manifest_bytes)
                elif name in updated_files:
                    zout.writestr(name, updated_files[name])
                else:
                    zout.writestr(info, data)
                written.add(name)
            for name, data in sorted(updated_files.items()):
                if name not in written and name not in removed_files:
                    zout.writestr(name, data)
        if pre_replace_check is not None:
            blocked, reason = pre_replace_check()
            if blocked:
                raise _LiveProcessBlockedError(reason)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _active_setting_item(
    items: Mapping[str, dict[str, Any]],
    name: str,
    *,
    expected_is_vector: bool,
) -> dict[str, Any] | None:
    item = items.get(name)
    if not isinstance(item, dict):
        return None
    if item.get("hasValue") is not True:
        return None
    if item.get("isVector") is not expected_is_vector:
        return None
    return item


def _snapshot_json_map_state(
    item: Mapping[str, Any] | None,
    managed_keys: tuple[str, ...],
) -> dict[str, Any]:
    existed = item is not None
    has_value = bool(item is not None and item.get("hasValue") is True)
    parsed_map: dict[str, Any] = {}
    if has_value and item is not None:
        ok, decoded = _parse_json_map_strict(item.get("value"))
        if ok:
            parsed_map = decoded
    modes_state: dict[str, Any] = {}
    for mode in ("light", "dark"):
        mode_map = parsed_map.get(mode)
        mode_existed = isinstance(mode_map, dict)
        key_states: dict[str, Any] = {}
        for subkey in managed_keys:
            if mode_existed and subkey in mode_map:
                key_states[subkey] = {"existed": True, "value": mode_map[subkey]}
            else:
                key_states[subkey] = {"existed": False}
        modes_state[mode] = {
            "mode_existed": mode_existed,
            "keys": key_states,
        }
    return {
        "kind": "json_map",
        "existed": existed,
        "has_value": has_value,
        "item": dict(item) if item is not None else None,
        "modes": modes_state,
    }


def _normalize_json_map_state(
    key: str,
    key_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Upgrade legacy snapshot states lacking kind/modes into subkey-level json_map state."""
    if key_state.get("kind") == "json_map" and isinstance(key_state.get("modes"), dict):
        return dict(key_state)
    old_item = key_state.get("item") if key_state.get("existed") and isinstance(key_state.get("item"), dict) else None
    return _snapshot_json_map_state(old_item, _JSON_MAP_MANAGED_KEYS[key])


def _restore_json_map_item(
    current_item: Mapping[str, Any] | None,
    key: str,
    key_state: Mapping[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Restore only managed subkeys in a MATLAB JSON-map setting, preserving post-Apply unmanaged subkeys."""
    current_map: dict[str, Any] = {}
    if current_item is not None and current_item.get("hasValue") is True:
        ok, decoded = _parse_json_map_strict(current_item.get("value"))
        if not ok:
            return False, None
        current_map = {k: (dict(v) if isinstance(v, dict) else v) for k, v in decoded.items()}

    modes_state = key_state.get("modes")
    if not isinstance(modes_state, dict):
        return False, None

    for mode in ("light", "dark"):
        mode_info = modes_state.get(mode)
        if not isinstance(mode_info, dict):
            continue
        mode_map = dict(current_map[mode]) if isinstance(current_map.get(mode), dict) else {}
        for subkey, sub_state in (mode_info.get("keys") or {}).items():
            if not isinstance(sub_state, dict):
                continue
            if sub_state.get("existed"):
                mode_map[subkey] = sub_state.get("value")
            else:
                mode_map.pop(subkey, None)
        if mode_map or mode_info.get("mode_existed"):
            current_map[mode] = mode_map
        else:
            current_map.pop(mode, None)

    if current_map:
        base_item = (
            dict(key_state["item"])
            if key_state.get("existed") and isinstance(key_state.get("item"), dict)
            else dict(current_item)
            if isinstance(current_item, dict)
            else _setting_entry(key, "", visible=False, is_vector=False)
        )
        base_item["hasValue"] = True
        base_item["isVector"] = False
        base_item["value"] = _encode_str_value(json.dumps(current_map, separators=(",", ":")))
        return True, base_item

    if key_state.get("existed") and isinstance(key_state.get("item"), dict):
        return True, dict(key_state["item"])
    return True, None


class MatlabAdapter:
    target = "matlab"

    def __init__(
        self,
        settings_path: Path | None = None,
        *,
        target_instance: Mapping[str, Any] | None = None,
        is_running_fn: Callable[[], bool] | None = None,
        process_closer: Callable[[], tuple[bool, str]] | None = None,
        appdata: Path | None = None,
        registry_roots: list[tuple[str, Path]] | None = None,
    ) -> None:
        self._custom_is_running = is_running_fn is not None
        self._is_running_fn = is_running_fn or is_matlab_running
        if process_closer is not None:
            self._process_closer: Callable[[], tuple[bool, str]] | None = process_closer
        elif is_running_fn is None:
            self._process_closer = lambda: close_windows_process("MATLAB.exe", process_probe=probe_matlab_process)
        else:
            self._process_closer = None
        self._expected_release: str | None = None
        self._expected_release_error: str | None = None
        if target_instance is not None:
            self._resolved_instance = dict(target_instance)
            raw_path = target_instance.get("settings_path")
            self.settings_path: Path | None = (
                Path(str(raw_path))
                if target_instance.get("status") == "ok" and isinstance(raw_path, str) and raw_path
                else None
            )
            raw_release = target_instance.get("release")
            normalized_release = normalize_matlab_release(str(raw_release)) if isinstance(raw_release, str) and raw_release else None
            self.release: str | None = normalized_release
            self._expected_release = normalized_release
            if target_instance.get("status") == "ok" and (
                normalized_release is None or not is_supported_matlab_release(normalized_release)
            ):
                self._expected_release_error = f"Invalid or unsupported MATLAB release in target_instance: {raw_release!r}"
        elif settings_path is not None:
            resolved = _resolve_abs_path(settings_path)
            self._resolved_instance = discover_matlab_instance(explicit_settings=resolved)
            self.settings_path = (
                Path(str(self._resolved_instance["settings_path"]))
                if self._resolved_instance.get("status") == "ok"
                else None
            )
            self.release = self._resolved_instance.get("release")
        else:
            env_settings = os.environ.get("ONE_TONE_MATLAB_SETTINGS")
            env_prefdir = os.environ.get("MATLAB_PREFDIR")
            self._resolved_instance = discover_matlab_instance(
                appdata=appdata,
                explicit_settings=Path(env_settings) if env_settings else None,
                prefdir=Path(env_prefdir) if (env_prefdir and not env_settings) else None,
                registry_roots=registry_roots,
            )
            self.settings_path = (
                Path(str(self._resolved_instance["settings_path"]))
                if self._resolved_instance.get("status") == "ok" and self._resolved_instance.get("settings_path")
                else None
            )
            self.release = self._resolved_instance.get("release")

    def _is_process_blocked(self) -> tuple[bool, str]:
        try:
            running = self._is_running_fn()
        except Exception as error:
            return True, f"Unable to verify whether MATLAB is running ({error}); refusing to write settings"
        if running is not False:
            return True, "MATLAB is running or process status could not be verified; close MATLAB and retry to avoid settings overwrite on exit"
        return False, ""

    def _ensure_process_stopped(self) -> tuple[bool, str, bool]:
        if not self._custom_is_running:
            try:
                status, detail = probe_matlab_process()
            except Exception as error:
                return True, f"Unable to verify whether MATLAB is running ({error}); refusing to write settings", False
            if status == "stopped":
                return False, "", False
            if status == "running" and self._process_closer is not None:
                try:
                    closed, close_detail = self._process_closer()
                except Exception as error:
                    return True, f"Unable to close running MATLAB ({error}); refusing to write settings", False
                try:
                    status, detail = probe_matlab_process()
                except Exception as error:
                    return True, f"Unable to verify MATLAB exit after shutdown ({error}); refusing to write settings", False
                if closed and status == "stopped":
                    return False, "", True
                suffix = f" ({close_detail or detail})" if (close_detail or detail) else ""
                return True, f"MATLAB remained running or could not be verified after shutdown attempt{suffix}; close MATLAB and retry to avoid settings overwrite on exit", False
            suffix = f" ({detail})" if detail else ""
            return True, f"MATLAB is running or process status could not be verified{suffix}; close MATLAB and retry to avoid settings overwrite on exit", False

        blocked, reason = self._is_process_blocked()
        if not blocked:
            return False, "", False
        if self._process_closer is not None:
            try:
                closed, close_detail = self._process_closer()
            except Exception as error:
                return True, f"Unable to close running MATLAB ({error}); refusing to write settings", False
            still_blocked, after_reason = self._is_process_blocked()
            if closed and not still_blocked:
                return False, "", True
            return True, close_detail or after_reason, False
        return True, reason, False

    def _pre_replace_guard(
        self,
        frozen_path: Path,
        expected_raw_bytes: bytes | None = None,
    ) -> Callable[[], tuple[bool, str]]:
        def _check() -> tuple[bool, str]:
            blocked, reason = self._is_process_blocked()
            if blocked:
                return True, reason
            ok_path, resolved, path_err = _verify_unredirected_path(frozen_path)
            if not ok_path or resolved is None:
                raise _WriteTargetRedirectedError(path_err)
            if expected_raw_bytes is not None:
                try:
                    current_bytes = resolved.read_bytes()
                except OSError as error:
                    raise _WriteTargetRedirectedError(f"MATLAB settings archive unavailable before replace: {error}") from error
                if current_bytes != expected_raw_bytes:
                    raise _WriteTargetRedirectedError(
                        f"MATLAB settings archive changed concurrently before atomic replace: {frozen_path}"
                    )
            return False, ""

        return _check

    def _load_checked(
        self,
    ) -> tuple[
        bool,
        Path | None,
        bytes,
        dict[str, tuple[zipfile.ZipInfo, bytes]],
        ET.Element | None,
        dict[str, ET.Element],
        str | None,
        str,
    ]:
        if self._resolved_instance.get("status") != "ok" or self.settings_path is None:
            return False, None, b"", {}, None, {}, None, str(self._resolved_instance.get("reason") or "MATLAB target not found")
        if self._expected_release_error is not None:
            return False, None, b"", {}, None, {}, None, self._expected_release_error
        ok_path, _, path_err = _verify_unredirected_path(self.settings_path)
        if not ok_path:
            return False, None, b"", {}, None, {}, None, path_err
        ok, raw_bytes, entries, manifest_root, manifest_map, release, reason = _load_and_validate_mlsettings(self.settings_path)
        if not ok:
            return False, None, b"", {}, None, {}, release, reason
        if self._expected_release is not None and release != self._expected_release:
            return (
                False,
                None,
                b"",
                {},
                None,
                {},
                release,
                f"MATLAB release mismatch at {self.settings_path}: expected {self._expected_release}, found {release}",
            )
        return True, self.settings_path, raw_bytes, entries, manifest_root, manifest_map, release or self.release, "verified"

    def _inspect(self) -> tuple[bool, Path | None, str | None, str]:
        ok, path, _, _, _, _, release, reason = self._load_checked()
        return ok, path, release, reason

    def _instance_payload(self, path: Path, release: str) -> dict[str, Any]:
        instance = {
            "status": "ok",
            "settings_path": str(path),
            "release": release,
            "source": str(self._resolved_instance.get("source") or "verified"),
        }
        if self._resolved_instance.get("matlab_root"):
            instance["matlab_root"] = str(self._resolved_instance["matlab_root"])
        return instance

    def target_instance(self) -> dict[str, Any]:
        ok, path, release, reason = self._inspect()
        if not ok or path is None or release is None:
            return {"status": "skipped", "reason": reason}
        return self._instance_payload(path, release)

    def _metadata(
        self,
        plan: Plan | None = None,
        status: str = "supported",
        *,
        target_instance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        statuses = {
            name: status if capability == "supported" else capability
            for name, capability in field_capabilities(self.target).items()
        }
        values = _generated_values(plan) if plan else {}
        return {
            "field_capabilities": statuses,
            "generated_values": values,
            "field_inventory": inventory_report(self.target, statuses, values),
            "field_groups": inventory_groups(self.target, statuses, values),
            "target_instance": dict(target_instance) if target_instance is not None else self.target_instance(),
            "rendering_verification": "untested",
            "desktop_chrome": {
                "status": "unsupported",
                "reason": "MATLAB Toolstrip, header, and sidebar colors are compiled into the installation themes.json bundle; One-Tone does not edit installation bundles",
            },
        }

    def detect(self) -> AdapterResult:
        ok, path, release, reason = self._inspect()
        if not ok or path is None or release is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        return AdapterResult(
            self.target,
            "partial",
            False,
            True,
            f"verified MATLAB {release} settings ({path}); Toolstrip/Header chrome unsupported; rendering untested",
            version=MATLAB_MLSETTINGS_SCHEMA_V1,
            metadata=self._metadata(target_instance=self._instance_payload(path, release)),
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        ok, path, raw_bytes, entries, _, manifest_map, release, reason = self._load_checked()
        if not ok or path is None or release is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        instance = self._instance_payload(path, release)
        blocked, block_reason, was_closed = self._ensure_process_stopped()
        if blocked:
            return AdapterResult(
                self.target,
                "skipped",
                False,
                False,
                block_reason,
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": instance},
            )
        if was_closed:
            ok, path, raw_bytes, entries, _, manifest_map, release, reason = self._load_checked()
            if not ok or path is None or release is None:
                return AdapterResult(self.target, "skipped", False, False, reason)
            instance = self._instance_payload(path, release)
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / "matlab.mlsettings").write_bytes(raw_bytes)
            snapshot_sha256 = hashlib.sha256(raw_bytes).hexdigest()

            groups_state: dict[str, Any] = {}
            for group_path, keys in _MANAGED_GROUP_KEYS.items():
                zip_rel = _zip_rel_for_group(group_path)
                ok_group, _, by_name, group_err = _read_and_validate_group_doc(entries, group_path)
                if not ok_group:
                    return AdapterResult(self.target, "failed", False, False, f"MATLAB snapshot failed: {group_err}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
                key_states: dict[str, Any] = {}
                for key in keys:
                    if key in _JSON_MAP_MANAGED_KEYS:
                        key_states[key] = _snapshot_json_map_state(by_name.get(key), _JSON_MAP_MANAGED_KEYS[key])
                    elif key in by_name:
                        key_states[key] = {"kind": "item", "existed": True, "item": by_name[key]}
                    else:
                        key_states[key] = {"kind": "item", "existed": False}
                folder_el = manifest_map.get(group_path)
                groups_state[group_path] = {
                    "group_file_existed": zip_rel in entries,
                    "manifest_folder_existed": folder_el is not None and folder_el.attrib.get("type") == "Folder",
                    "entries": key_states,
                }

            state_payload = {
                "schema": MATLAB_MLSETTINGS_SCHEMA_V1,
                "settings_path": str(path),
                "release": release,
                "snapshot_sha256": snapshot_sha256,
                "groups": groups_state,
            }
            atomic_write_text(backup_dir / "matlab-state.json", json.dumps(state_payload, ensure_ascii=False, sort_keys=True))
            return AdapterResult(
                self.target,
                "ok",
                False,
                True,
                f"MATLAB {release} settings snapshot saved",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": instance},
            )
        except _ARCHIVE_READ_ERRORS as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB snapshot failed: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

    @staticmethod
    def _read_snapshot_guard(backup_dir: Path) -> tuple[bool, tuple[str, str] | None, str]:
        state_path = backup_dir / "matlab-state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return False, None, f"MATLAB snapshot state unreadable: {error}"
        snap_path = state.get("settings_path")
        snap_sha = state.get("snapshot_sha256")
        if not isinstance(snap_path, str) or not snap_path or not Path(snap_path).is_absolute():
            return False, None, f"MATLAB snapshot settings_path is invalid: {snap_path!r}"
        if not isinstance(snap_sha, str) or len(snap_sha) != 64:
            return False, None, "MATLAB snapshot state is missing snapshot_sha256"
        return True, (os.path.normcase(os.path.normpath(snap_path)), snap_sha), "ok"

    def apply_with_backup(self, plan: Plan, backup_dir: Path) -> AdapterResult:
        return self.apply(plan, backup_dir=backup_dir)

    def apply(self, plan: Plan, *, backup_dir: Path | None = None) -> AdapterResult:
        expected_snapshot: tuple[str, str] | None = None
        if backup_dir is not None:
            ok_guard, expected_snapshot, guard_err = self._read_snapshot_guard(backup_dir)
            if not ok_guard or expected_snapshot is None:
                return AdapterResult(
                    self.target,
                    "failed",
                    False,
                    False,
                    f"MATLAB apply aborted before write: {guard_err}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                    metadata={"aborted_before_write": True},
                )
        ok, path, raw_bytes, entries, manifest_root, manifest_map, release, reason = self._load_checked()
        if not ok or path is None or manifest_root is None:
            if expected_snapshot is not None:
                return AdapterResult(
                    self.target,
                    "failed",
                    False,
                    False,
                    f"MATLAB apply aborted before write (archive changed or invalid since snapshot): {reason}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                    metadata={"aborted_before_write": True},
                )
            return AdapterResult(self.target, "skipped", False, False, reason)
        blocked, block_reason, was_closed = self._ensure_process_stopped()
        instance = self._instance_payload(path, release or str(self.release or ""))
        if blocked:
            return AdapterResult(
                self.target,
                "skipped",
                False,
                False,
                block_reason,
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": instance},
            )
        if was_closed:
            ok, path, raw_bytes, entries, manifest_root, manifest_map, release, reason = self._load_checked()
            if not ok or path is None or manifest_root is None:
                if expected_snapshot is not None:
                    return AdapterResult(
                        self.target,
                        "failed",
                        False,
                        False,
                        f"MATLAB apply aborted before write (archive changed or invalid after closing MATLAB): {reason}",
                        version=MATLAB_MLSETTINGS_SCHEMA_V1,
                        metadata={"aborted_before_write": True},
                    )
                return AdapterResult(self.target, "skipped", False, False, reason)
            instance = self._instance_payload(path, release or str(self.release or ""))
        if expected_snapshot is not None:
            actual_key = (
                os.path.normcase(os.path.normpath(str(path))),
                hashlib.sha256(raw_bytes).hexdigest(),
            )
            if actual_key != expected_snapshot:
                return AdapterResult(
                    self.target,
                    "failed",
                    False,
                    False,
                    f"MATLAB settings archive changed since snapshot: {path}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                    metadata={"aborted_before_write": True},
                )
        replaced = False
        try:
            ok_colors, _, existing_colors, colors_err = _read_and_validate_group_doc(entries, _COLORS_GROUP)
            if not ok_colors:
                return AdapterResult(
                    self.target,
                    "failed",
                    False,
                    False,
                    f"MATLAB apply aborted: {colors_err}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                    metadata={"aborted_before_write": True},
                )

            desktop_map: dict[str, Any] = {}
            existing_desktop_item = _active_setting_item(existing_colors, "DesktopColors", expected_is_vector=False)
            if existing_desktop_item is not None:
                ok_map, decoded = _parse_json_map_strict(existing_desktop_item.get("value"))
                if not ok_map:
                    return AdapterResult(
                        self.target,
                        "failed",
                        False,
                        False,
                        "MATLAB apply aborted: corrupted DesktopColors",
                        version=MATLAB_MLSETTINGS_SCHEMA_V1,
                        metadata={"aborted_before_write": True},
                    )
                desktop_map = decoded

            syntax_map: dict[str, Any] = {}
            existing_syntax_item = _active_setting_item(existing_colors, "SyntaxHighlightingColors", expected_is_vector=False)
            if existing_syntax_item is not None:
                ok_map, decoded = _parse_json_map_strict(existing_syntax_item.get("value"))
                if not ok_map:
                    return AdapterResult(
                        self.target,
                        "failed",
                        False,
                        False,
                        "MATLAB apply aborted: corrupted SyntaxHighlightingColors",
                        version=MATLAB_MLSETTINGS_SCHEMA_V1,
                        metadata={"aborted_before_write": True},
                    )
                syntax_map = decoded

            mode_syntax: dict[str, dict[str, str]] = {}
            for mode in ("light", "dark"):
                mode_desktop, mode_syntax_colors = _matlab_mode_colors(plan.palette_for(mode), mode)
                mode_syntax[mode] = mode_syntax_colors
                desktop_mode = dict(desktop_map.get(mode) or {})
                desktop_mode.update(mode_desktop)
                desktop_map[mode] = desktop_mode

                syntax_mode = dict(syntax_map.get(mode) or {})
                syntax_mode.update(mode_syntax_colors)
                syntax_map[mode] = syntax_mode

            group_updates: dict[str, dict[str, dict[str, Any]]] = {
                _APPEARANCE_GROUP: {
                    "MATLABTheme": _setting_entry("MATLABTheme", _encode_str_value("System"), visible=False, is_vector=False),
                },
                _COLORS_GROUP: {
                    "DesktopColors": _setting_entry(
                        "DesktopColors",
                        _encode_str_value(json.dumps(desktop_map, separators=(",", ":"))),
                        visible=False,
                        is_vector=False,
                    ),
                    "SyntaxHighlightingColors": _setting_entry(
                        "SyntaxHighlightingColors",
                        _encode_str_value(json.dumps(syntax_map, separators=(",", ":"))),
                        visible=False,
                        is_vector=False,
                    ),
                },
            }

            light_syntax = mode_syntax["light"]
            for group_path, _, keys in _LIGHT_RGB_MIRROR_GROUPS:
                target_updates = group_updates.setdefault(group_path, {})
                for key in keys:
                    target_updates[key] = _setting_entry(
                        key,
                        _encode_rgb_value(_rgb_list(light_syntax[key])),
                        visible=True,
                        is_vector=True,
                    )

            updated_files: dict[str, bytes] = {}
            for group_path, updates in group_updates.items():
                ok_group, existing_doc, by_name, group_err = _read_and_validate_group_doc(entries, group_path)
                if not ok_group:
                    return AdapterResult(
                        self.target,
                        "failed",
                        False,
                        False,
                        f"MATLAB apply aborted: {group_err}",
                        version=MATLAB_MLSETTINGS_SCHEMA_V1,
                        metadata={"aborted_before_write": True},
                    )
                doc = dict(existing_doc) if existing_doc is not None else _new_group_doc(group_path, _GROUP_VISIBILITY[group_path])
                by_name.update(updates)
                doc["settings"] = [by_name[key] for key in sorted(by_name)]
                zip_rel = _zip_rel_for_group(group_path)
                updated_files[zip_rel] = _serialize_group_doc(doc)

                if group_path in manifest_map and manifest_map[group_path].attrib.get("type") == "Folder":
                    manifest_root.remove(manifest_map.pop(group_path))
                file_entry_name = f"{group_path}/settings.json"
                expected_content = f"/{zip_rel}"
                existing_el = manifest_map.get(file_entry_name)
                if existing_el is None:
                    el = ET.Element(_MANIFEST_ENTRY_TAG, {"content": expected_content, "name": file_entry_name, "type": "File"})
                    manifest_root.append(el)
                    manifest_map[file_entry_name] = el
                else:
                    existing_el.attrib["type"] = "File"
                    existing_el.attrib["content"] = expected_content

            _atomic_write_zip(
                path,
                entries,
                updated_files,
                set(),
                _serialize_manifest(manifest_root),
                pre_replace_check=self._pre_replace_guard(path, expected_raw_bytes=raw_bytes),
            )
            replaced = True
            return AdapterResult(
                self.target,
                "partial",
                True,
                False,
                f"MATLAB {release} desktop colors and System theme applied; Toolstrip/Header chrome unsupported",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata=self._metadata(plan, "applied", target_instance=instance),
            )
        except _LiveProcessBlockedError as error:
            return AdapterResult(
                self.target,
                "skipped",
                False,
                False,
                str(error),
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": instance},
            )
        except (_WriteTargetRedirectedError, json.JSONDecodeError, *_ARCHIVE_READ_ERRORS) as error:
            if replaced:
                return AdapterResult(
                    self.target,
                    "failed",
                    True,
                    False,
                    f"MATLAB apply failed after write: {error}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                )
            return AdapterResult(
                self.target,
                "failed",
                False,
                False,
                f"MATLAB apply failed: {error}",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"aborted_before_write": True},
            )

    def verify(self, plan: Plan) -> AdapterResult:
        if self._resolved_instance.get("status") != "ok" or self.settings_path is None:
            reason = str(self._resolved_instance.get("reason") or "MATLAB target not found")
            return AdapterResult(self.target, "skipped", False, False, reason)
        ok, path, _, entries, _, manifest_map, release, reason = self._load_checked()
        if not ok or path is None:
            return AdapterResult(
                self.target,
                "failed",
                False,
                False,
                f"MATLAB verify failed: {reason}",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata=self._metadata(plan, "failed", target_instance={"status": "skipped", "reason": reason}),
            )
        instance = self._instance_payload(path, release or str(self.release or ""))

        mismatches: list[str] = []
        for group_path in _MANAGED_GROUP_KEYS:
            expected_name = f"{group_path}/settings.json"
            expected_content = f"/{_zip_rel_for_group(group_path)}"
            el = manifest_map.get(expected_name)
            if el is None or el.attrib.get("type") != "File" or el.attrib.get("content") != expected_content:
                mismatches.append(f"manifest:{expected_name}")

        ok_app, _, appearance_items, app_err = _read_and_validate_group_doc(entries, _APPEARANCE_GROUP)
        if not ok_app:
            mismatches.append(f"appearance:{app_err}")
        else:
            theme_item = _active_setting_item(appearance_items, "MATLABTheme", expected_is_vector=False)
            if theme_item is None or _decode_str_value(theme_item.get("value")) != "System":
                mismatches.append("matlab.appearance.MATLABTheme")

        ok_colors, _, colors_items, colors_err = _read_and_validate_group_doc(entries, _COLORS_GROUP)
        mode_syntax: dict[str, dict[str, str]] = {}
        mode_desktop: dict[str, dict[str, str]] = {}
        for mode in ("light", "dark"):
            mode_desktop[mode], mode_syntax[mode] = _matlab_mode_colors(plan.palette_for(mode), mode)

        if not ok_colors:
            mismatches.append(f"colors:{colors_err}")
        else:
            desktop_item = _active_setting_item(colors_items, "DesktopColors", expected_is_vector=False)
            syntax_item = _active_setting_item(colors_items, "SyntaxHighlightingColors", expected_is_vector=False)
            desktop_ok, desktop_map = _parse_json_map_strict(desktop_item.get("value")) if desktop_item is not None else (False, {})
            syntax_ok, syntax_map = _parse_json_map_strict(syntax_item.get("value")) if syntax_item is not None else (False, {})
            if not desktop_ok:
                mismatches.append("matlab.colors.DesktopColors")
            if not syntax_ok:
                mismatches.append("matlab.colors.SyntaxHighlightingColors")
            for mode in ("light", "dark"):
                actual_desktop = desktop_map.get(mode) if isinstance(desktop_map.get(mode), dict) else {}
                for key, expected in mode_desktop[mode].items():
                    if str(actual_desktop.get(key, "")).lower() != expected:
                        mismatches.append(f"DesktopColors.{mode}.{key}")
                actual_syntax = syntax_map.get(mode) if isinstance(syntax_map.get(mode), dict) else {}
                for key, expected in mode_syntax[mode].items():
                    if str(actual_syntax.get(key, "")).lower() != expected:
                        mismatches.append(f"SyntaxHighlightingColors.{mode}.{key}")

        light_syntax = mode_syntax["light"]
        for group_path, _, keys in _LIGHT_RGB_MIRROR_GROUPS:
            ok_group, _, items, group_err = _read_and_validate_group_doc(entries, group_path)
            if not ok_group:
                mismatches.append(f"{group_path}:{group_err}")
                continue
            for key in keys:
                item = _active_setting_item(items, key, expected_is_vector=True)
                if item is None or _decode_rgb_value(item.get("value")) != _rgb_list(light_syntax[key]):
                    mismatches.append(f"{group_path}.{key}")

        verified = not mismatches
        return AdapterResult(
            self.target,
            "partial" if verified else "failed",
            False,
            verified,
            f"MATLAB {release} desktop colors verified; Toolstrip/Header chrome unsupported; rendering untested"
            if verified
            else f"MATLAB settings mismatch ({', '.join(mismatches[:5])}); rendering untested",
            version=MATLAB_MLSETTINGS_SCHEMA_V1,
            metadata=self._metadata(plan, "verified" if verified else "failed", target_instance=instance),
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        blocked, block_reason, _ = self._ensure_process_stopped()
        if blocked:
            return AdapterResult(
                self.target,
                "failed",
                False,
                False,
                block_reason,
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )
        state_path = backup_dir / "matlab-state.json"
        if not state_path.is_file():
            return AdapterResult(self.target, "failed", False, False, "MATLAB backup state not found", version=MATLAB_MLSETTINGS_SCHEMA_V1)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB backup state unreadable: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        snapshot_path_raw = state.get("settings_path")
        if not isinstance(snapshot_path_raw, str) or not snapshot_path_raw or not Path(snapshot_path_raw).is_absolute():
            return AdapterResult(self.target, "failed", False, False, f"MATLAB snapshot settings_path must be absolute: {snapshot_path_raw!r}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
        frozen_snapshot_path = Path(snapshot_path_raw)
        ok_unredirected, path, redirect_err = _verify_unredirected_path(frozen_snapshot_path)
        if not ok_unredirected or path is None:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB rollback aborted: {redirect_err}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
        expected_norm = os.path.normcase(os.path.normpath(str(frozen_snapshot_path)))
        if self.settings_path is not None:
            if not self.settings_path.is_absolute():
                return AdapterResult(self.target, "failed", False, False, f"MATLAB adapter settings_path must be absolute for rollback: {self.settings_path}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
            if os.path.normcase(os.path.normpath(str(self.settings_path))) != expected_norm:
                return AdapterResult(
                    self.target,
                    "failed",
                    False,
                    False,
                    f"MATLAB rollback aborted: adapter path {self.settings_path} does not match snapshot path {frozen_snapshot_path}",
                    version=MATLAB_MLSETTINGS_SCHEMA_V1,
                )
        if isinstance(metadata, Mapping) and isinstance(metadata.get("target_instance"), Mapping):
            meta_path = metadata["target_instance"].get("settings_path")
            if isinstance(meta_path, str) and meta_path and Path(meta_path).is_absolute():
                if os.path.normcase(os.path.normpath(str(meta_path))) != expected_norm:
                    return AdapterResult(
                        self.target,
                        "failed",
                        False,
                        False,
                        f"MATLAB rollback aborted: transaction metadata path {meta_path} does not match snapshot path {frozen_snapshot_path}",
                        version=MATLAB_MLSETTINGS_SCHEMA_V1,
                    )
        ok_load, raw_bytes, entries, manifest_root, manifest_map, detected_release, load_err = _load_and_validate_mlsettings(path)
        if not ok_load or manifest_root is None:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB rollback aborted (archive invalid): {load_err}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
        expected_release = normalize_matlab_release(state.get("release")) if isinstance(state.get("release"), str) else None
        if expected_release is not None and detected_release != expected_release:
            return AdapterResult(
                self.target,
                "failed",
                False,
                False,
                f"MATLAB rollback aborted: release mismatch at {path} (expected {expected_release}, found {detected_release})",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )

        groups_state = state.get("groups")
        if not isinstance(groups_state, dict):
            return AdapterResult(self.target, "failed", False, False, "MATLAB backup state is missing group snapshots", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        replaced = False
        try:
            updated_files: dict[str, bytes] = {}
            removed_files: set[str] = set()

            for group_path, group_info in groups_state.items():
                if not isinstance(group_info, dict):
                    continue
                zip_rel = _zip_rel_for_group(group_path)
                file_entry_name = f"{group_path}/settings.json"
                ok_group, doc, by_name, group_err = _read_and_validate_group_doc(entries, group_path)
                if not ok_group:
                    return AdapterResult(self.target, "failed", False, False, f"MATLAB rollback aborted: {group_err}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

                for key, key_state in (group_info.get("entries") or {}).items():
                    if not isinstance(key_state, dict):
                        continue
                    if key in _JSON_MAP_MANAGED_KEYS:
                        normalized_state = _normalize_json_map_state(key, key_state)
                        ok_restore, restored_item = _restore_json_map_item(by_name.get(key), key, normalized_state)
                        if not ok_restore:
                            return AdapterResult(self.target, "failed", False, False, f"MATLAB rollback aborted: corrupted {key}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
                        if restored_item is not None:
                            by_name[key] = restored_item
                        else:
                            by_name.pop(key, None)
                    elif key_state.get("existed") and isinstance(key_state.get("item"), dict):
                        by_name[key] = dict(key_state["item"])
                    else:
                        by_name.pop(key, None)

                if not by_name and not group_info.get("group_file_existed"):
                    if zip_rel in entries:
                        removed_files.add(zip_rel)
                    if file_entry_name in manifest_map:
                        manifest_root.remove(manifest_map.pop(file_entry_name))
                    if group_info.get("manifest_folder_existed") and group_path not in manifest_map:
                        el = ET.Element(_MANIFEST_ENTRY_TAG, {"content": "", "name": group_path, "type": "Folder"})
                        manifest_root.append(el)
                        manifest_map[group_path] = el
                else:
                    restored_doc = dict(doc) if doc is not None else _new_group_doc(group_path, _GROUP_VISIBILITY.get(group_path, True))
                    restored_doc["settings"] = [by_name[key] for key in sorted(by_name)]
                    updated_files[zip_rel] = _serialize_group_doc(restored_doc)
                    if group_path in manifest_map and manifest_map[group_path].attrib.get("type") == "Folder":
                        manifest_root.remove(manifest_map.pop(group_path))
                    expected_content = f"/{zip_rel}"
                    if file_entry_name not in manifest_map:
                        el = ET.Element(_MANIFEST_ENTRY_TAG, {"content": expected_content, "name": file_entry_name, "type": "File"})
                        manifest_root.append(el)
                        manifest_map[file_entry_name] = el
                    else:
                        manifest_map[file_entry_name].attrib["type"] = "File"
                        manifest_map[file_entry_name].attrib["content"] = expected_content

            _atomic_write_zip(
                path,
                entries,
                updated_files,
                removed_files,
                _serialize_manifest(manifest_root),
                pre_replace_check=self._pre_replace_guard(frozen_snapshot_path, expected_raw_bytes=raw_bytes),
            )
            replaced = True

            # Verify field-level restoration
            ok_vload, _, verify_entries, _, verify_manifest_map, _, _ = _load_and_validate_mlsettings(path)
            restored = ok_vload

            for group_path, group_info in groups_state.items():
                if not restored or not isinstance(group_info, dict):
                    continue
                zip_rel = _zip_rel_for_group(group_path)
                file_entry_name = f"{group_path}/settings.json"
                ok_vgroup, _, by_name, _ = _read_and_validate_group_doc(verify_entries, group_path)
                if not ok_vgroup:
                    restored = False
                    break
                for key, key_state in (group_info.get("entries") or {}).items():
                    if not isinstance(key_state, dict):
                        continue
                    if key in _JSON_MAP_MANAGED_KEYS:
                        normalized_state = _normalize_json_map_state(key, key_state)
                        actual_item = by_name.get(key)
                        actual_map: dict[str, Any] = {}
                        if actual_item is not None and actual_item.get("hasValue") is True:
                            ok_m, decoded_m = _parse_json_map_strict(actual_item.get("value"))
                            if not ok_m:
                                restored = False
                                break
                            actual_map = decoded_m
                        for mode, mode_info in (normalized_state.get("modes") or {}).items():
                            actual_mode = actual_map.get(mode) if isinstance(actual_map.get(mode), dict) else {}
                            for subkey, sub_state in (mode_info.get("keys") or {}).items():
                                if sub_state.get("existed"):
                                    if actual_mode.get(subkey) != sub_state.get("value"):
                                        restored = False
                                else:
                                    if subkey in actual_mode:
                                        restored = False
                    elif key_state.get("existed"):
                        if by_name.get(key) != key_state.get("item"):
                            restored = False
                    else:
                        if key in by_name:
                            restored = False
                if zip_rel in verify_entries:
                    el = verify_manifest_map.get(file_entry_name)
                    if el is None or el.attrib.get("type") != "File" or el.attrib.get("content") != f"/{zip_rel}":
                        restored = False
                else:
                    if file_entry_name in verify_manifest_map:
                        restored = False
                    if group_info.get("manifest_folder_existed"):
                        folder_el = verify_manifest_map.get(group_path)
                        if folder_el is None or folder_el.attrib.get("type") != "Folder":
                            restored = False

            return AdapterResult(
                self.target,
                "ok" if restored else "failed",
                True,
                restored,
                "MATLAB managed settings restored (field-level)" if restored else "MATLAB field-level restore verification failed",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )
        except (_LiveProcessBlockedError, _WriteTargetRedirectedError) as error:
            return AdapterResult(self.target, "failed", False, False, str(error), version=MATLAB_MLSETTINGS_SCHEMA_V1)
        except (json.JSONDecodeError, *_ARCHIVE_READ_ERRORS) as error:
            return AdapterResult(
                self.target,
                "failed",
                replaced,
                False,
                f"MATLAB rollback failed after write: {error}" if replaced else f"MATLAB rollback failed: {error}",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )
