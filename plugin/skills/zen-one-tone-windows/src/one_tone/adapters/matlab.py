from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from ..inventory import inventory_groups, inventory_report
from ..palette import parse_hex_color
from ..plan import Plan
from ..storage import atomic_write_text
from .base import AdapterResult, field_capabilities

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

_LIGHT_RGB_MIRROR_GROUPS: tuple[tuple[str, bool, tuple[tuple[str, str], ...]], ...] = (
    (
        _COLORS_GROUP,
        True,
        (
            ("KeywordColor", "info_text"),
            ("CommentColor", "muted_foreground"),
            ("StringColor", "purple_text"),
            ("UnterminatedStringColor", "error_text"),
            ("SystemCommandColor", "warning_text"),
            ("ValidationSectionColor", "cyan_text"),
            ("SyntaxErrorColor", "error_text"),
        ),
    ),
    (
        _COMMANDWINDOW_GROUP,
        True,
        (
            ("ErrorColor", "error_text"),
            ("WarningColor", "warning_text"),
            ("HyperlinkColor", "accent_text"),
        ),
    ),
    (
        _PROGRAMMINGTOOLS_GROUP,
        True,
        (
            ("CodeAnalyzerWarningColor", "warning_text"),
            ("CodeAnalyzerInfoColor", "info_text"),
            ("AutofixHighlightColor", "surface_subtle"),
            ("VariableHighlightColor", "selection_background"),
            ("VariablesWithSharedScopeColor", "cyan_text"),
        ),
    ),
    (
        _DISPLAYSETTINGS_GROUP,
        True,
        (
            ("HighlightCurrentLineColor", "surface_raised"),
        ),
    ),
    (
        _LINELIMIT_GROUP,
        True,
        (
            ("LineColor", "border"),
        ),
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


def is_matlab_running() -> bool:
    """Return True if a MATLAB.exe process is currently running on Windows."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        th32cs_snapprocess = 0x00000002
        invalid_handle = ctypes.c_void_p(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_uint32),
                ("cntUsage", ctypes.c_uint32),
                ("th32ProcessID", ctypes.c_uint32),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", ctypes.c_uint32),
                ("cntThreads", ctypes.c_uint32),
                ("th32ParentProcessID", ctypes.c_uint32),
                ("pcPriClassBase", ctypes.c_int32),
                ("dwFlags", ctypes.c_uint32),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
        if snapshot == invalid_handle:
            return False
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                if entry.szExeFile.casefold() == "matlab.exe":
                    return True
                has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            return False
        finally:
            kernel32.CloseHandle(snapshot)
    except (AttributeError, OSError):
        return False


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
                    root_path = Path(root_str.strip())
                    release = _read_version_info_release(root_path) or normalize_matlab_release(subname)
                    if release:
                        found.append((release, root_path))
        except OSError:
            continue
    return found


def _inspect_mlsettings(path: Path) -> tuple[bool, str | None, str]:
    if not path.is_file():
        return False, None, f"MATLAB settings file not found: {path}"
    if not zipfile.is_zipfile(path):
        return False, None, f"MATLAB settings file is not a valid OPC ZIP archive: {path}"
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            if _SCHEMA_ENTRY not in names or _MANIFEST_ENTRY not in names:
                return False, None, f"MATLAB settings archive is missing required schema or manifest: {path}"
            schema = archive.read(_SCHEMA_ENTRY).decode("utf-8", errors="replace").strip()
            if schema != _EXPECTED_SCHEMA_JSON:
                return False, None, f"Unsupported MATLAB settings schema '{schema}' in {path}"
            ET.fromstring(archive.read(_MANIFEST_ENTRY))
            release: str | None = None
            if _RELEASE_INFO_ENTRY in names:
                try:
                    info_root = ET.fromstring(archive.read(_RELEASE_INFO_ENTRY))
                    node = info_root.find("release")
                    release = normalize_matlab_release(node.text if node is not None else None)
                except ET.ParseError:
                    release = None
            if release is None:
                release = normalize_matlab_release(path.parent.name)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        return False, None, f"Failed to read MATLAB settings archive {path}: {error}"
    if release is None:
        return False, None, f"Unable to determine MATLAB release for {path}"
    if not is_supported_matlab_release(release):
        return False, release, f"MATLAB {release} uses legacy desktop architecture; R2025a or newer is required"
    return True, release, "verified"


def discover_matlab_instance(
    *,
    appdata: Path | None = None,
    explicit_settings: Path | None = None,
    prefdir: Path | None = None,
    registry_roots: list[tuple[str, Path]] | None = None,
) -> dict[str, Any]:
    """Discover a single Active Target instance for MATLAB desktop (>= R2025a)."""
    if explicit_settings is not None:
        ok, release, reason = _inspect_mlsettings(explicit_settings)
        if not ok:
            return {"status": "skipped", "reason": reason}
        return {
            "status": "ok",
            "settings_path": str(explicit_settings),
            "release": release,
            "source": "explicit",
        }

    if prefdir is not None:
        candidate = prefdir / "matlab.mlsettings"
        ok, release, reason = _inspect_mlsettings(candidate)
        if not ok:
            return {"status": "skipped", "reason": reason}
        return {
            "status": "ok",
            "settings_path": str(candidate),
            "release": release,
            "source": "prefdir",
        }

    resolved_appdata = appdata or Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
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
        settings_path = matlab_roaming / release / "matlab.mlsettings"
        candidates_by_release[parsed] = (release, settings_path, root_path)

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
                candidates_by_release[parsed] = (release, child / "matlab.mlsettings", None)

    uninitialized: list[str] = []
    invalid_reasons: list[str] = []
    for parsed in sorted(candidates_by_release, reverse=True):
        release, settings_path, root_path = candidates_by_release[parsed]
        if not settings_path.is_file():
            uninitialized.append(release)
            continue
        ok, detected_release, reason = _inspect_mlsettings(settings_path)
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


def _desktop_colors_for(palette: Mapping[str, str]) -> dict[str, str]:
    return {key: palette[role].lower() for key, role in _DESKTOP_COLOR_ROLES}


def _syntax_colors_for(palette: Mapping[str, str]) -> dict[str, str]:
    return {key: palette[role].lower() for key, role in _SYNTAX_COLOR_ROLES}


def _rgb_list(hex_color: str) -> list[int]:
    return list(parse_hex_color(hex_color))


def _generated_values(plan: Plan) -> dict[str, Any]:
    values: dict[str, Any] = {
        "matlab.appearance.MATLABTheme": "System",
    }
    for mode in ("light", "dark"):
        palette = plan.palette_for(mode)
        for key, value in _desktop_colors_for(palette).items():
            values[f"matlab.colors.DesktopColors.{mode}.{key}"] = value
        for key, value in _syntax_colors_for(palette).items():
            values[f"matlab.colors.SyntaxHighlightingColors.{mode}.{key}"] = value
    light_palette = plan.palette_for("light")
    for group_path, _, role_pairs in _LIGHT_RGB_MIRROR_GROUPS:
        prefix = group_path.removeprefix("/settingstree/").replace("/", ".")
        for key, role in role_pairs:
            values[f"{prefix}.{key}"] = _rgb_list(light_palette[role])
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


def _decode_str_value(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, str) else None


def _decode_json_map(raw: Any) -> dict[str, Any]:
    text = _decode_str_value(raw)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
        and all(isinstance(channel, int) for channel in parsed["mwdata"])
    ):
        return list(parsed["mwdata"])
    return None


def _zip_rel_for_group(group_path: str) -> str:
    return f"fsroot{group_path}/settings.json"


def _read_group_doc(entries: Mapping[str, tuple[zipfile.ZipInfo, bytes]], group_path: str) -> dict[str, Any] | None:
    zip_rel = _zip_rel_for_group(group_path)
    if zip_rel not in entries:
        return None
    try:
        doc = json.loads(entries[zip_rel][1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _group_settings_by_name(doc: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not doc:
        return {}
    items = doc.get("settings")
    if not isinstance(items, list):
        return {}
    return {
        str(item["name"]): dict(item)
        for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


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
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class MatlabAdapter:
    target = "matlab"

    def __init__(
        self,
        settings_path: Path | None = None,
        *,
        target_instance: Mapping[str, Any] | None = None,
        is_running_fn: Callable[[], bool] | None = None,
        appdata: Path | None = None,
        registry_roots: list[tuple[str, Path]] | None = None,
    ) -> None:
        self._is_running_fn = is_running_fn or is_matlab_running
        if target_instance is not None:
            self._resolved_instance = dict(target_instance)
            self.settings_path: Path | None = (
                Path(str(target_instance["settings_path"]))
                if target_instance.get("status") == "ok" and target_instance.get("settings_path")
                else None
            )
            self.release: str | None = (
                str(target_instance["release"])
                if target_instance.get("release")
                else None
            )
        elif settings_path is not None:
            self._resolved_instance = discover_matlab_instance(explicit_settings=settings_path)
            self.settings_path = settings_path if self._resolved_instance.get("status") == "ok" else None
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

    def _inspect(self) -> tuple[bool, Path | None, str | None, str]:
        if self._resolved_instance.get("status") != "ok" or self.settings_path is None:
            return False, None, None, str(self._resolved_instance.get("reason") or "MATLAB target not found")
        ok, release, reason = _inspect_mlsettings(self.settings_path)
        if not ok:
            return False, None, release, reason
        return True, self.settings_path, release or self.release, "verified"

    def target_instance(self) -> dict[str, Any]:
        ok, path, release, reason = self._inspect()
        if not ok or path is None or release is None:
            return {"status": "skipped", "reason": reason}
        instance = {
            "status": "ok",
            "settings_path": str(path),
            "release": release,
            "source": str(self._resolved_instance.get("source") or "verified"),
        }
        if self._resolved_instance.get("matlab_root"):
            instance["matlab_root"] = str(self._resolved_instance["matlab_root"])
        return instance

    def _metadata(self, plan: Plan | None = None, status: str = "supported") -> dict[str, Any]:
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
            "target_instance": self.target_instance(),
            "rendering_verification": "untested",
            "desktop_chrome": {
                "status": "unsupported",
                "reason": "MATLAB Toolstrip, header, and sidebar colors are compiled into the installation themes.json bundle; One-Tone does not edit installation bundles",
            },
        }

    def detect(self) -> AdapterResult:
        ok, path, release, reason = self._inspect()
        if not ok or path is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        return AdapterResult(
            self.target,
            "partial",
            False,
            True,
            f"verified MATLAB {release} settings ({path}); Toolstrip/Header chrome unsupported; rendering untested",
            version=MATLAB_MLSETTINGS_SCHEMA_V1,
            metadata=self._metadata(),
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        ok, path, release, reason = self._inspect()
        if not ok or path is None or release is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        if self._is_running_fn():
            return AdapterResult(
                self.target,
                "skipped",
                False,
                False,
                "MATLAB is currently running; close MATLAB and retry to avoid settings overwrite on exit",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": self.target_instance()},
            )
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / "matlab.mlsettings")

            with zipfile.ZipFile(path, "r") as archive:
                entries = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}
            manifest_root = ET.fromstring(entries[_MANIFEST_ENTRY][1])
            tag = f"{{{_MANIFEST_NS}}}fileEntry"
            manifest_entries = {el.attrib.get("name", ""): el.attrib.get("type", "") for el in manifest_root.findall(tag)}

            groups_state: dict[str, Any] = {}
            for group_path, keys in _MANAGED_GROUP_KEYS.items():
                zip_rel = _zip_rel_for_group(group_path)
                doc = _read_group_doc(entries, group_path)
                by_name = _group_settings_by_name(doc)
                key_states: dict[str, Any] = {}
                for key in keys:
                    if key in by_name:
                        key_states[key] = {"existed": True, "item": by_name[key]}
                    else:
                        key_states[key] = {"existed": False}
                groups_state[group_path] = {
                    "group_file_existed": zip_rel in entries,
                    "manifest_folder_existed": manifest_entries.get(group_path) == "Folder",
                    "entries": key_states,
                }

            state_payload = {
                "schema": MATLAB_MLSETTINGS_SCHEMA_V1,
                "settings_path": str(path),
                "release": release,
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
                metadata={"target_instance": self.target_instance()},
            )
        except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB snapshot failed: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

    def apply(self, plan: Plan) -> AdapterResult:
        ok, path, release, reason = self._inspect()
        if not ok or path is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        if self._is_running_fn():
            return AdapterResult(
                self.target,
                "skipped",
                False,
                False,
                "MATLAB is currently running; close MATLAB and retry to avoid settings overwrite on exit",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata={"target_instance": self.target_instance()},
            )
        try:
            with zipfile.ZipFile(path, "r") as archive:
                entries = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}

            manifest_root = ET.fromstring(entries[_MANIFEST_ENTRY][1])
            tag = f"{{{_MANIFEST_NS}}}fileEntry"
            manifest_map = {el.attrib.get("name", ""): el for el in manifest_root.findall(tag)}

            # Merge DesktopColors and SyntaxHighlightingColors preserving any unrelated subkeys
            existing_colors_doc = _read_group_doc(entries, _COLORS_GROUP)
            existing_colors = _group_settings_by_name(existing_colors_doc)

            desktop_map = _decode_json_map(existing_colors.get("DesktopColors", {}).get("value"))
            syntax_map = _decode_json_map(existing_colors.get("SyntaxHighlightingColors", {}).get("value"))
            for mode in ("light", "dark"):
                palette = plan.palette_for(mode)
                desktop_mode = dict(desktop_map.get(mode) or {}) if isinstance(desktop_map.get(mode), dict) else {}
                desktop_mode.update(_desktop_colors_for(palette))
                desktop_map[mode] = desktop_mode

                syntax_mode = dict(syntax_map.get(mode) or {}) if isinstance(syntax_map.get(mode), dict) else {}
                syntax_mode.update(_syntax_colors_for(palette))
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

            light_palette = plan.palette_for("light")
            for group_path, _, role_pairs in _LIGHT_RGB_MIRROR_GROUPS:
                target_updates = group_updates.setdefault(group_path, {})
                for key, role in role_pairs:
                    target_updates[key] = _setting_entry(
                        key,
                        _encode_rgb_value(_rgb_list(light_palette[role])),
                        visible=True,
                        is_vector=True,
                    )

            updated_files: dict[str, bytes] = {}
            for group_path, updates in group_updates.items():
                doc = _read_group_doc(entries, group_path) or _new_group_doc(group_path, _GROUP_VISIBILITY[group_path])
                by_name = _group_settings_by_name(doc)
                by_name.update(updates)
                doc["settings"] = [by_name[key] for key in sorted(by_name)]
                zip_rel = _zip_rel_for_group(group_path)
                updated_files[zip_rel] = _serialize_group_doc(doc)

                if group_path in manifest_map and manifest_map[group_path].attrib.get("type") == "Folder":
                    manifest_root.remove(manifest_map.pop(group_path))
                file_entry_name = f"{group_path}/settings.json"
                if file_entry_name not in manifest_map:
                    el = ET.Element(tag, {"content": f"/{zip_rel}", "name": file_entry_name, "type": "File"})
                    manifest_root.append(el)
                    manifest_map[file_entry_name] = el

            _atomic_write_zip(path, entries, updated_files, set(), _serialize_manifest(manifest_root))
            return AdapterResult(
                self.target,
                "partial",
                True,
                False,
                f"MATLAB {release} desktop colors and System theme applied; Toolstrip/Header chrome unsupported",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
                metadata=self._metadata(plan, "applied"),
            )
        except (OSError, zipfile.BadZipFile, ET.ParseError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB apply failed: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

    def verify(self, plan: Plan) -> AdapterResult:
        ok, path, release, reason = self._inspect()
        if not ok or path is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        try:
            with zipfile.ZipFile(path, "r") as archive:
                entries = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}
            manifest_root = ET.fromstring(entries[_MANIFEST_ENTRY][1])
            tag = f"{{{_MANIFEST_NS}}}fileEntry"
            manifest_files = {
                el.attrib.get("name", ""): el.attrib.get("content", "")
                for el in manifest_root.findall(tag)
                if el.attrib.get("type") == "File"
            }
        except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB verify read failed: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        mismatches: list[str] = []
        for group_path in _MANAGED_GROUP_KEYS:
            expected_name = f"{group_path}/settings.json"
            expected_content = f"/{_zip_rel_for_group(group_path)}"
            if manifest_files.get(expected_name) != expected_content:
                mismatches.append(f"manifest:{expected_name}")

        appearance_items = _group_settings_by_name(_read_group_doc(entries, _APPEARANCE_GROUP))
        if _decode_str_value(appearance_items.get("MATLABTheme", {}).get("value")) != "System":
            mismatches.append("matlab.appearance.MATLABTheme")

        colors_items = _group_settings_by_name(_read_group_doc(entries, _COLORS_GROUP))
        desktop_map = _decode_json_map(colors_items.get("DesktopColors", {}).get("value"))
        syntax_map = _decode_json_map(colors_items.get("SyntaxHighlightingColors", {}).get("value"))
        for mode in ("light", "dark"):
            palette = plan.palette_for(mode)
            actual_desktop = desktop_map.get(mode) if isinstance(desktop_map.get(mode), dict) else {}
            for key, expected in _desktop_colors_for(palette).items():
                if str(actual_desktop.get(key, "")).lower() != expected:
                    mismatches.append(f"DesktopColors.{mode}.{key}")
            actual_syntax = syntax_map.get(mode) if isinstance(syntax_map.get(mode), dict) else {}
            for key, expected in _syntax_colors_for(palette).items():
                if str(actual_syntax.get(key, "")).lower() != expected:
                    mismatches.append(f"SyntaxHighlightingColors.{mode}.{key}")

        light_palette = plan.palette_for("light")
        for group_path, _, role_pairs in _LIGHT_RGB_MIRROR_GROUPS:
            items = _group_settings_by_name(_read_group_doc(entries, group_path))
            for key, role in role_pairs:
                if _decode_rgb_value(items.get(key, {}).get("value")) != _rgb_list(light_palette[role]):
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
            metadata=self._metadata(plan, "verified" if verified else "failed"),
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        if self._is_running_fn():
            return AdapterResult(
                self.target,
                "failed",
                False,
                False,
                "MATLAB is currently running; close MATLAB and retry rollback to avoid settings overwrite on exit",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )
        state_path = backup_dir / "matlab-state.json"
        if not state_path.is_file():
            return AdapterResult(self.target, "failed", False, False, "MATLAB backup state not found", version=MATLAB_MLSETTINGS_SCHEMA_V1)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB backup state unreadable: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        path = self.settings_path or (Path(state["settings_path"]) if isinstance(state.get("settings_path"), str) else None)
        if path is None or not path.is_file() or not zipfile.is_zipfile(path):
            return AdapterResult(self.target, "failed", False, False, f"MATLAB settings archive unavailable for field rollback: {path}", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        groups_state = state.get("groups")
        if not isinstance(groups_state, dict):
            return AdapterResult(self.target, "failed", False, False, "MATLAB backup state is missing group snapshots", version=MATLAB_MLSETTINGS_SCHEMA_V1)

        try:
            with zipfile.ZipFile(path, "r") as archive:
                entries = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}
            manifest_root = ET.fromstring(entries[_MANIFEST_ENTRY][1])
            tag = f"{{{_MANIFEST_NS}}}fileEntry"
            manifest_map = {el.attrib.get("name", ""): el for el in manifest_root.findall(tag)}

            updated_files: dict[str, bytes] = {}
            removed_files: set[str] = set()

            for group_path, group_info in groups_state.items():
                if not isinstance(group_info, dict):
                    continue
                zip_rel = _zip_rel_for_group(group_path)
                file_entry_name = f"{group_path}/settings.json"
                doc = _read_group_doc(entries, group_path)
                by_name = _group_settings_by_name(doc)

                for key, key_state in (group_info.get("entries") or {}).items():
                    if not isinstance(key_state, dict):
                        continue
                    if key_state.get("existed") and isinstance(key_state.get("item"), dict):
                        by_name[key] = dict(key_state["item"])
                    else:
                        by_name.pop(key, None)

                if not by_name and not group_info.get("group_file_existed"):
                    if zip_rel in entries:
                        removed_files.add(zip_rel)
                    if file_entry_name in manifest_map:
                        manifest_root.remove(manifest_map.pop(file_entry_name))
                    if group_info.get("manifest_folder_existed") and group_path not in manifest_map:
                        el = ET.Element(tag, {"content": "", "name": group_path, "type": "Folder"})
                        manifest_root.append(el)
                        manifest_map[group_path] = el
                else:
                    restored_doc = doc or _new_group_doc(group_path, _GROUP_VISIBILITY.get(group_path, True))
                    restored_doc["settings"] = [by_name[key] for key in sorted(by_name)]
                    updated_files[zip_rel] = _serialize_group_doc(restored_doc)
                    if group_path in manifest_map and manifest_map[group_path].attrib.get("type") == "Folder":
                        manifest_root.remove(manifest_map.pop(group_path))
                    if file_entry_name not in manifest_map:
                        el = ET.Element(tag, {"content": f"/{zip_rel}", "name": file_entry_name, "type": "File"})
                        manifest_root.append(el)
                        manifest_map[file_entry_name] = el

            _atomic_write_zip(path, entries, updated_files, removed_files, _serialize_manifest(manifest_root))

            # Verify field-level restoration
            with zipfile.ZipFile(path, "r") as archive:
                verify_entries = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}
            verify_manifest = ET.fromstring(verify_entries[_MANIFEST_ENTRY][1])
            verify_manifest_map = {el.attrib.get("name", ""): el.attrib.get("type", "") for el in verify_manifest.findall(tag)}

            restored = True
            for group_path, group_info in groups_state.items():
                if not isinstance(group_info, dict):
                    continue
                zip_rel = _zip_rel_for_group(group_path)
                file_entry_name = f"{group_path}/settings.json"
                doc = _read_group_doc(verify_entries, group_path)
                by_name = _group_settings_by_name(doc)
                for key, key_state in (group_info.get("entries") or {}).items():
                    if key_state.get("existed"):
                        if by_name.get(key) != key_state.get("item"):
                            restored = False
                    else:
                        if key in by_name:
                            restored = False
                if zip_rel in verify_entries:
                    if verify_manifest_map.get(file_entry_name) != "File":
                        restored = False
                else:
                    if file_entry_name in verify_manifest_map:
                        restored = False
                    if group_info.get("manifest_folder_existed") and verify_manifest_map.get(group_path) != "Folder":
                        restored = False

            return AdapterResult(
                self.target,
                "ok" if restored else "failed",
                True,
                restored,
                "MATLAB managed settings restored (field-level)" if restored else "MATLAB field-level restore verification failed",
                version=MATLAB_MLSETTINGS_SCHEMA_V1,
            )
        except (OSError, zipfile.BadZipFile, ET.ParseError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"MATLAB rollback failed: {error}", version=MATLAB_MLSETTINGS_SCHEMA_V1)
