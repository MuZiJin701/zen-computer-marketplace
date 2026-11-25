from __future__ import annotations

import copy
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

from ..editor_instance import EditorSpec
from ..field_mappings import vscode_capabilities, vscode_theme_colors
from ..plan import Plan
from ..storage import atomic_write_bytes, atomic_write_text, loads_jsonc, patch_jsonc_object
from .base import AdapterResult, field_capabilities

_MANAGED_SETTINGS_KEYS = (
    "workbench.colorTheme",
    "workbench.preferredDarkColorTheme",
    "workbench.preferredLightColorTheme",
    "window.autoDetectColorScheme",
)


def build_theme_json(plan: Plan, theme_name: str, mode: str | None = None, *, baseline: str = "1.140.0") -> dict[str, Any]:
    mode = mode or plan.mode
    palette = plan.palette_for(mode)
    colors = vscode_theme_colors(palette, mode, baseline)
    info_text = palette.get("info_text", palette["accent_text"])
    cyan_text = palette.get("cyan_text", palette["accent_text"])
    purple_text = palette.get("purple_text", palette["accent_text"])
    return {
        "name": theme_name,
        "type": mode,
        "colors": colors,
        "semanticHighlighting": True,
        "semanticTokenColors": {
            "namespace": cyan_text,
            "type": cyan_text,
            "class": cyan_text,
            "interface": cyan_text,
            "enum": cyan_text,
            "struct": cyan_text,
            "typeParameter": cyan_text,
            "function": info_text,
            "method": info_text,
            "variable": palette["foreground"],
            "parameter": palette["foreground"],
            "property": palette["foreground"],
            "enumMember": purple_text,
            "constant": palette["warning_text"],
            "number": palette["warning_text"],
            "regexp": palette["warning_text"],
            "operator": palette["accent_text"],
            "keyword": palette["accent_text"],
            "macro": purple_text,
            "decorator": purple_text,
            "comment": palette["muted_foreground"],
            "string": palette["success_text"],
        },
        "tokenColors": [
            {"scope": ["comment", "punctuation.definition.comment"], "settings": {"foreground": palette["muted_foreground"], "fontStyle": "italic"}},
            {"scope": ["string"], "settings": {"foreground": palette["success_text"]}},
            {"scope": ["keyword", "storage.modifier", "keyword.operator"], "settings": {"foreground": palette["accent_text"]}},
            {"scope": ["invalid"], "settings": {"foreground": palette["error_text"]}},
            {"scope": ["entity.name.function", "support.function"], "settings": {"foreground": info_text}},
            {"scope": ["entity.name.type", "support.type", "storage.type", "entity.name.class"], "settings": {"foreground": cyan_text}},
            {"scope": ["variable", "variable.parameter"], "settings": {"foreground": palette["foreground"]}},
            {"scope": ["constant.numeric", "constant.language", "keyword.other.unit"], "settings": {"foreground": palette["warning_text"]}},
            {"scope": ["constant.character.escape", "string.regexp"], "settings": {"foreground": purple_text}},
            {"scope": ["support.type.property-name", "entity.name.tag.yaml", "meta.object-literal.key", "support.type.property-name.json"], "settings": {"foreground": cyan_text}},
            {"scope": ["entity.name.tag", "support.class.component"], "settings": {"foreground": info_text}},
            {"scope": ["entity.other.attribute-name"], "settings": {"foreground": purple_text}},
            {"scope": ["entity.other.attribute-name.class", "entity.other.attribute-name.id"], "settings": {"foreground": palette["warning_text"]}},
            {"scope": ["markup.heading", "entity.name.section"], "settings": {"foreground": palette["accent_text"], "fontStyle": "bold"}},
            {"scope": ["markup.bold"], "settings": {"foreground": palette["foreground"], "fontStyle": "bold"}},
            {"scope": ["markup.italic"], "settings": {"foreground": purple_text, "fontStyle": "italic"}},
            {"scope": ["markup.underline.link", "string.other.link"], "settings": {"foreground": info_text}},
            {"scope": ["markup.inline.raw", "markup.fenced_code"], "settings": {"foreground": palette["success_text"]}},
            {"scope": ["markup.quote"], "settings": {"foreground": palette["muted_foreground"], "fontStyle": "italic"}},
            {"scope": ["punctuation.definition", "punctuation.separator", "punctuation.terminator"], "settings": {"foreground": palette["muted_foreground"]}},
        ],
    }


def build_vsix(plan: Plan, output_path: Path, spec: EditorSpec) -> Path:
    baseline = spec.color_baseline or "1.140.0"
    theme_name = f"One Tone {spec.target}"
    dark_label = f"{theme_name} Dark"
    light_label = f"{theme_name} Light"
    package = {
        "name": f"one-tone-{spec.target}",
        "displayName": theme_name,
        "description": "Palette-generated One-Tone theme",
        "version": "0.1.0",
        "publisher": "one-tone",
        "engines": {"vscode": ">=1.80.0"},
        "contributes": {"themes": [
            {"label": f"{theme_name} Dark", "uiTheme": "vs-dark", "path": "./themes/one-tone-color-theme.json"},
            {"label": f"{theme_name} Light", "uiTheme": "vs", "path": "./themes/one-tone-light-color-theme.json"},
        ]},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("extension/package.json", json.dumps(package, ensure_ascii=False, indent=2))
        archive.writestr("extension/themes/one-tone-color-theme.json", json.dumps(build_theme_json(plan, dark_label, "dark", baseline=baseline), ensure_ascii=False, indent=2))
        archive.writestr("extension/themes/one-tone-light-color-theme.json", json.dumps(build_theme_json(plan, light_label, "light", baseline=baseline), ensure_ascii=False, indent=2))
    return output_path


class VSCodeFamilyAdapter:
    def __init__(
        self,
        spec: EditorSpec,
        command_runner: Callable[..., Any] | None = None,
        app_mode: str | None = None,
    ) -> None:
        self.spec = spec
        self.target = spec.target
        self.command_runner = command_runner
        self.app_mode = app_mode if app_mode in {"light", "dark"} else None
        self._extension_dir: Path | None = None
        self._theme_name = f"One Tone {spec.target}"

    def target_instance(self) -> dict[str, Any]:
        return self.spec.target_instance()

    def _field_capabilities(self, status: str = "supported") -> dict[str, str]:
        return field_capabilities(self.target, statuses={name: status if capability == "supported" else capability
                                                       for name, capability in vscode_capabilities(self.spec.color_baseline).items()})

    def _executable_available(self) -> bool:
        if isinstance(self.spec.executable, Path):
            if self.spec.executable.exists():
                return True
            return shutil.which(str(self.spec.executable)) is not None
        return shutil.which(str(self.spec.executable)) is not None

    def _settings_ready(self) -> bool:
        if self.spec.settings_path.is_file():
            return True
        if self.spec.resolution_source == "standard" and (
            self.spec.extensions_dir.is_dir()
            or self.spec.settings_path.parent.is_dir()
            or self.spec.settings_path.parent.parent.is_dir()
            or bool(self.spec.mirror_targets)
        ):
            return True
        return False

    def _read_settings_at(self, settings_path: Path, allow_missing: bool = False) -> dict[str, Any]:
        if not settings_path.is_file():
            if allow_missing:
                return {}
            raise FileNotFoundError(f"editor settings not found: {settings_path}")
        payload = loads_jsonc(settings_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("editor settings must be a JSON object")
        return payload

    def _read_settings(self) -> dict[str, Any]:
        return self._read_settings_at(
            self.spec.settings_path,
            allow_missing=self.spec.resolution_source == "standard",
        )

    def _extension_id(self) -> str:
        return f"one-tone.one-tone-{self.target}"

    def _theme_label(self, mode: str) -> str:
        return f"{self._theme_name} {'Light' if mode == 'light' else 'Dark'}"

    def _theme_labels(self) -> tuple[str, str]:
        return self._theme_label("dark"), self._theme_label("light")

    def _contributed_labels(self, extension_dir: Path) -> set[str] | None:
        package_path = extension_dir / "package.json"
        if not package_path.is_file():
            return None
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            themes = package.get("contributes", {}).get("themes", [])
            paths = {self._theme_label("dark"): ("./themes/one-tone-color-theme.json", "vs-dark"),
                     self._theme_label("light"): ("./themes/one-tone-light-color-theme.json", "vs")}
            return {item["label"] for item in themes if isinstance(item, dict) and item.get("label") in paths
                    and (item.get("path"), item.get("uiTheme")) == paths[item["label"]]}
        except (OSError, TypeError, AttributeError, json.JSONDecodeError):
            return set()

    def _installed_extension_dirs_in(self, extensions_dir: Path) -> list[Path]:
        prefix = f"{self._extension_id()}-"
        if not extensions_dir.is_dir():
            return []
        candidates = [
            path
            for path in extensions_dir.iterdir()
            if path.is_dir() and path.name.startswith(prefix)
        ]
        index = extensions_dir / "extensions.json"
        if index.is_file():
            try:
                entries = json.loads(index.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                entries = []
            normalized_entries = entries if isinstance(entries, list) else [entries] if isinstance(entries, dict) else []
            for entry in normalized_entries:
                if not isinstance(entry, dict):
                    continue
                identifier = entry.get("identifier", {})
                if identifier.get("id") != self._extension_id():
                    continue
                relative = entry.get("relativeLocation")
                if isinstance(relative, str):
                    candidate = extensions_dir / relative
                    if candidate.is_dir():
                        candidates.append(candidate)
        return list(dict.fromkeys(candidates))

    def _installed_extension_dirs(self) -> list[Path]:
        return self._installed_extension_dirs_in(self.spec.extensions_dir)

    def _registered_extension_dirs_in(self, extensions_dir: Path) -> list[Path]:
        index = extensions_dir / "extensions.json"
        if not index.is_file():
            return []
        try:
            entries = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        normalized_entries = entries if isinstance(entries, list) else [entries] if isinstance(entries, dict) else []
        registered: list[Path] = []
        for entry in normalized_entries:
            if not isinstance(entry, dict) or entry.get("identifier", {}).get("id") != self._extension_id():
                continue
            relative = entry.get("relativeLocation")
            if isinstance(relative, str):
                candidate = extensions_dir / relative
                if candidate.is_dir():
                    registered.append(candidate)
        return list(dict.fromkeys(registered))

    def _registered_extension_dirs(self) -> list[Path]:
        return self._registered_extension_dirs_in(self.spec.extensions_dir)

    def _theme_file(self, extension_dir: Path) -> Path | None:
        for candidate in (
            extension_dir / "themes" / "one-tone-color-theme.json",
            extension_dir / "extension" / "themes" / "one-tone-color-theme.json",
        ):
            if candidate.is_file():
                return candidate
        return None

    def _theme_files(self, extension_dir: Path) -> tuple[Path, Path] | None:
        dark = extension_dir / "themes" / "one-tone-color-theme.json"
        light = extension_dir / "themes" / "one-tone-light-color-theme.json"
        if dark.is_file() and light.is_file():
            return dark, light
        return None

    def _registration_candidate_in(self, extensions_dir: Path) -> tuple[Path | None, str | None]:
        for extension_dir in self._registered_extension_dirs_in(extensions_dir):
            if self._theme_files(extension_dir) is None:
                continue
            labels = self._contributed_labels(extension_dir)
            if labels is not None and set(self._theme_labels()) <= labels:
                return extension_dir, None
        return None, "registered extension, theme files or contributed labels are incomplete"

    def _registration_candidate(self) -> tuple[Path | None, str | None]:
        return self._registration_candidate_in(self.spec.extensions_dir)

    def _snapshot_extension_state_in(self, extensions_dir: Path, backup_dir: Path, prefix: str) -> None:
        index = extensions_dir / "extensions.json"
        index_exists = index.is_file()
        saved_entries: list[dict[str, Any]] | None = None
        if index_exists:
            shutil.copy2(index, backup_dir / f"{prefix}-extensions.json")
            try:
                loaded = json.loads(index.read_text(encoding="utf-8"))
                normalized = loaded if isinstance(loaded, list) else [loaded] if isinstance(loaded, dict) else None
                if normalized is not None:
                    saved_entries = [
                        copy.deepcopy(entry)
                        for entry in normalized
                        if isinstance(entry, dict) and entry.get("identifier", {}).get("id") == self._extension_id()
                    ]
            except (OSError, json.JSONDecodeError):
                saved_entries = None
        else:
            saved_entries = []
        obsolete = extensions_dir / ".obsolete"
        if obsolete.is_file():
            shutil.copy2(obsolete, backup_dir / f"{prefix}-extensions-obsolete")
        atomic_write_text(
            backup_dir / f"{prefix}-extensions-state.json",
            json.dumps({"index_exists": index_exists, "entries": saved_entries}, ensure_ascii=False, sort_keys=True),
        )
        installed_backup = backup_dir / f"{prefix}-installed"
        for extension_dir in self._installed_extension_dirs_in(extensions_dir):
            shutil.copytree(extension_dir, installed_backup / extension_dir.name)

    def _snapshot_extension_state(self, backup_dir: Path) -> None:
        self._snapshot_extension_state_in(self.spec.extensions_dir, backup_dir, self.target)

    def _restore_extension_state_in(self, extensions_dir: Path, backup_dir: Path, prefix: str) -> bool:
        for extension_dir in self._installed_extension_dirs_in(extensions_dir):
            shutil.rmtree(extension_dir)
        staging = extensions_dir / f"one-tone-{self.target}"
        if staging.exists():
            shutil.rmtree(staging)

        installed_backup = backup_dir / f"{prefix}-installed"
        if installed_backup.is_dir():
            extensions_dir.mkdir(parents=True, exist_ok=True)
            for extension_dir in installed_backup.iterdir():
                shutil.copytree(extension_dir, extensions_dir / extension_dir.name)

        index = extensions_dir / "extensions.json"
        index_backup = backup_dir / f"{prefix}-extensions.json"
        ext_state_path = backup_dir / f"{prefix}-extensions-state.json"
        index_restored = False
        if ext_state_path.is_file():
            try:
                ext_state = json.loads(ext_state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                ext_state = {}
            saved_entries = ext_state.get("entries")
            index_existed = bool(ext_state.get("index_exists", index_backup.is_file()))
            if isinstance(saved_entries, list):
                current_entries: list[dict[str, Any]] | None = []
                if index.is_file():
                    try:
                        loaded = json.loads(index.read_text(encoding="utf-8"))
                        if isinstance(loaded, list):
                            current_entries = [entry for entry in loaded if isinstance(entry, dict)]
                        elif isinstance(loaded, dict):
                            current_entries = [loaded]
                        else:
                            current_entries = None
                    except (OSError, json.JSONDecodeError):
                        current_entries = None
                if current_entries is not None:
                    merged = [entry for entry in current_entries if entry.get("identifier", {}).get("id") != self._extension_id()]
                    merged.extend(copy.deepcopy(entry) for entry in saved_entries if isinstance(entry, dict))
                    if not index_existed and not merged:
                        if index.exists():
                            index.unlink()
                        index_restored = not index.exists()
                    else:
                        atomic_write_text(index, json.dumps(merged, ensure_ascii=False, separators=(",", ":")))
                        try:
                            verified_entries = json.loads(index.read_text(encoding="utf-8"))
                        except (OSError, json.JSONDecodeError):
                            verified_entries = None
                        actual_own = [
                            entry
                            for entry in (verified_entries if isinstance(verified_entries, list) else [])
                            if isinstance(entry, dict) and entry.get("identifier", {}).get("id") == self._extension_id()
                        ]
                        index_restored = actual_own == saved_entries
        if not index_restored:
            if index_backup.is_file():
                atomic_write_bytes(index, index_backup.read_bytes())
                index_restored = index.read_bytes() == index_backup.read_bytes()
            elif index.exists():
                index.unlink()
                index_restored = not index.exists()
            else:
                index_restored = True

        obsolete = extensions_dir / ".obsolete"
        obsolete_backup = backup_dir / f"{prefix}-extensions-obsolete"
        if obsolete_backup.is_file():
            atomic_write_bytes(obsolete, obsolete_backup.read_bytes())
        elif obsolete.exists():
            obsolete.unlink()

        current_names = {path.name for path in self._installed_extension_dirs_in(extensions_dir)}
        backup_names = {path.name for path in installed_backup.iterdir()} if installed_backup.is_dir() else set()
        return current_names == backup_names and index_restored

    def _restore_extension_state(self, backup_dir: Path) -> bool:
        return self._restore_extension_state_in(self.spec.extensions_dir, backup_dir, self.target)

    def _remove_installed_extension_state_in(self, extensions_dir: Path) -> None:
        installed_dirs = self._installed_extension_dirs_in(extensions_dir)
        removable_dirs = [path for path in installed_dirs if self._theme_file(path) is None]
        removable_names = {path.name for path in removable_dirs}
        for extension_dir in removable_dirs:
            shutil.rmtree(extension_dir)
        staging = extensions_dir / f"one-tone-{self.target}"
        if staging.exists():
            shutil.rmtree(staging)

        index = extensions_dir / "extensions.json"
        if not index.is_file():
            return
        try:
            entries = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return
        filtered = [
            entry
            for entry in entries
            if entry.get("identifier", {}).get("id") != self._extension_id()
            or entry.get("relativeLocation") not in removable_names
        ]
        if filtered != entries:
            atomic_write_text(index, json.dumps(filtered, ensure_ascii=False, separators=(",", ":")))

    def _remove_installed_extension_state(self) -> None:
        self._remove_installed_extension_state_in(self.spec.extensions_dir)

    def _cli_requires_restart(self, completed: Any) -> bool:
        output = b"\n".join(
            value if isinstance(value, bytes) else str(value or "").encode("utf-8", errors="replace")
            for value in (getattr(completed, "stdout", b""), getattr(completed, "stderr", b""))
        ).lower()
        restart_markers = (
            b"please restart vscode before reinstalling",
            b"please restart vs code before reinstalling",
            b"please restart trae before reinstalling",
            b"restart trae before reinstalling",
            b"restart antigravity",
        )
        return any(marker in output for marker in restart_markers)

    def _cli_diagnostic(self, completed: Any) -> str:
        values = []
        for value in (getattr(completed, "stdout", b""), getattr(completed, "stderr", b"")):
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if value:
                values.append(str(value).strip())
        return " ".join(values)[:1000]

    def _manual_install_vsix_to(self, vsix_path: Path, extensions_dir: Path) -> bool:
        extensions_dir.mkdir(parents=True, exist_ok=True)
        staging = extensions_dir / f".one-tone-{self.target}-staging"
        try:
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(vsix_path) as archive:
                members = [name for name in archive.namelist() if name == "extension" or name.startswith("extension/")]
                if not members:
                    return False
                archive.extractall(staging, members)

            package_dir = staging / "extension"
            package_path = package_dir / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            extension_id = f"{package['publisher']}.{package['name']}"
            version = str(package["version"])
            if extension_id != self._extension_id():
                return False
            installed_dir = extensions_dir / f"{extension_id}-{version}"
            if installed_dir.exists():
                shutil.rmtree(installed_dir)
            shutil.move(str(package_dir), str(installed_dir))

            index = extensions_dir / "extensions.json"
            entries = []
            if index.is_file():
                loaded = json.loads(index.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    entries = loaded
                elif isinstance(loaded, dict):
                    entries = [loaded]
            relative_location = installed_dir.name
            location = {
                "$mid": 1,
                "fsPath": str(installed_dir),
                "_sep": 1,
                "path": "/" + str(installed_dir).replace("\\", "/"),
                "scheme": "file",
            }
            replacement = {
                "identifier": {"id": extension_id},
                "version": version,
                "location": location,
                "relativeLocation": relative_location,
                "metadata": {"pinned": True, "source": "vsix"},
            }
            entries = [
                replacement if entry.get("identifier", {}).get("id") == extension_id else entry
                for entry in entries
                if isinstance(entry, dict)
            ]
            if not any(entry.get("identifier", {}).get("id") == extension_id for entry in entries):
                entries.append(replacement)
            atomic_write_text(index, json.dumps(entries, ensure_ascii=False, separators=(",", ":")))
            return True
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, zipfile.BadZipFile):
            return False
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def _manual_install_vsix(self, vsix_path: Path) -> bool:
        return self._manual_install_vsix_to(vsix_path, self.spec.extensions_dir)

    def _apply_theme_settings_to(self, settings_path: Path, mode: str, allow_missing: bool = True) -> dict[str, Any]:
        raw_text = settings_path.read_text(encoding="utf-8") if settings_path.is_file() else ""
        settings = self._read_settings_at(settings_path, allow_missing=allow_missing)
        updates = {
            "workbench.colorTheme": self._theme_label(mode),
            "workbench.preferredDarkColorTheme": self._theme_label("dark"),
            "workbench.preferredLightColorTheme": self._theme_label("light"),
            "window.autoDetectColorScheme": True,
        }
        settings.update(updates)
        atomic_write_text(
            settings_path,
            patch_jsonc_object(raw_text, updates, expected_dict=settings),
        )
        return settings

    @staticmethod
    def _snapshot_settings_entries(settings_path: Path) -> dict[str, Any] | None:
        if not settings_path.is_file():
            return {key: {"existed": False} for key in _MANAGED_SETTINGS_KEYS}
        try:
            payload = loads_jsonc(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return {
            key: ({"existed": True, "value": copy.deepcopy(payload[key])} if key in payload else {"existed": False})
            for key in _MANAGED_SETTINGS_KEYS
        }

    @staticmethod
    def _restore_settings_file(
        settings_path: Path,
        backup_file: Path,
        existed_before: bool,
        key_entries: Mapping[str, Any] | None,
    ) -> bool:
        if isinstance(key_entries, Mapping) and settings_path.is_file():
            try:
                raw_text = settings_path.read_text(encoding="utf-8")
                current = loads_jsonc(raw_text)
            except (OSError, ValueError, json.JSONDecodeError):
                current = None
            if isinstance(current, dict):
                updates = {
                    key: copy.deepcopy(entry["value"])
                    for key, entry in key_entries.items()
                    if isinstance(entry, Mapping) and entry.get("existed")
                }
                removals = [
                    key
                    for key, entry in key_entries.items()
                    if isinstance(entry, Mapping) and not entry.get("existed")
                ]
                expected = dict(current)
                for key in removals:
                    expected.pop(key, None)
                expected.update(updates)
                if not existed_before and not expected:
                    settings_path.unlink()
                    return not settings_path.exists()
                atomic_write_text(
                    settings_path,
                    patch_jsonc_object(raw_text, updates, removals, expected_dict=expected),
                )
                try:
                    verified = loads_jsonc(settings_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    return False
                return isinstance(verified, dict) and all(
                    (key in verified and verified[key] == updates[key] and type(verified[key]) is type(updates[key]))
                    for key in updates
                ) and all(key not in verified for key in removals)
        if existed_before:
            backup_bytes = backup_file.read_bytes()
            atomic_write_bytes(settings_path, backup_bytes)
            return settings_path.read_bytes() == backup_bytes
        if settings_path.exists():
            settings_path.unlink()
        return not settings_path.exists()

    def detect(self) -> AdapterResult:
        if self.spec.resolution_status != "ok":
            return AdapterResult(self.target, "skipped", False, False, self.spec.resolution_message or f"{self.target} configuration path is ambiguous")
        if not self._settings_ready():
            return AdapterResult(self.target, "skipped", False, False, f"{self.target} settings not found: {self.spec.settings_path}")
        if not self._executable_available():
            return AdapterResult(self.target, "skipped", False, False, f"{self.target} executable not found: {self.spec.executable}")
        if not self.spec.color_baseline:
            return AdapterResult(self.target, "skipped", False, False, "Workbench version has no verified public color baseline; configuration preserved",
                                 metadata={"target_instance": self.target_instance(), "field_capabilities": self._field_capabilities()})
        return AdapterResult(
            self.target,
            "ok",
            False,
            True,
            f"{self.target} detected at {self.spec.settings_path}",
            metadata={"target_instance": self.target_instance(), "field_capabilities": self._field_capabilities()},
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        if not self._settings_ready():
            return AdapterResult(self.target, "failed", False, False, "editor settings not found")
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            primary_exists = self.spec.settings_path.is_file()
            if primary_exists:
                shutil.copy2(self.spec.settings_path, backup_dir / f"{self.target}-settings.json")
            primary_entries = self._snapshot_settings_entries(self.spec.settings_path)
            self._snapshot_extension_state(backup_dir)
            mirror_states = []
            for idx, (mirror_settings, mirror_extensions) in enumerate(self.spec.mirror_targets):
                prefix = f"{self.target}-mirror-{idx}"
                m_exists = mirror_settings.is_file()
                if m_exists:
                    shutil.copy2(mirror_settings, backup_dir / f"{prefix}-settings.json")
                m_entries = self._snapshot_settings_entries(mirror_settings)
                self._snapshot_extension_state_in(mirror_extensions, backup_dir, prefix)
                mirror_states.append({"index": idx, "settings_exists": m_exists, "settings_entries": m_entries})
            state_payload = {"primary_exists": primary_exists, "primary_entries": primary_entries, "mirrors": mirror_states}
            atomic_write_text(backup_dir / f"{self.target}-settings-state.json", json.dumps(state_payload, sort_keys=True))
            return AdapterResult(
                self.target,
                "ok",
                False,
                True,
                f"{self.target} settings snapshot saved",
                metadata={"target_instance": self.target_instance()},
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"{self.target} snapshot failed: {error}")

    def apply(self, plan: Plan) -> AdapterResult:
        if not self.spec.color_baseline:
            return AdapterResult(self.target, "skipped", False, False, "Workbench color baseline is unverified; configuration preserved")
        try:
            settings = self._read_settings()
            artifacts_dir = self.spec.artifacts_dir or self.spec.extensions_dir.parent / ".one-tone-artifacts"
            vsix_path = build_vsix(plan, artifacts_dir / f"{self.target}-{plan.id}.vsix", self.spec)
            self.spec.extensions_dir.mkdir(parents=True, exist_ok=True)
            self._remove_installed_extension_state()
            active_mode = self.app_mode or plan.mode
            settings = self._apply_theme_settings_to(
                self.spec.settings_path,
                active_mode,
                allow_missing=(self.spec.resolution_source == "standard"),
            )
            command = [
                str(self.spec.executable),
                "--install-extension",
                str(vsix_path),
                "--force",
                "--user-data-dir",
                str(self.spec.settings_path.parent.parent),
                "--extensions-dir",
                str(self.spec.extensions_dir),
            ]
            if self.command_runner is None:
                completed = subprocess.run(command, check=False, capture_output=True, timeout=30)
            else:
                completed = self.command_runner(command, check=False, capture_output=True)
            cli_returncode = getattr(completed, "returncode", 0) if completed is not None else 0
            cli_warning = ""
            cli_diagnostic = ""
            if completed is not None and cli_returncode not in (0, None):
                cli_diagnostic = self._cli_diagnostic(completed)
                if self._cli_requires_restart(completed):
                    if not self._manual_install_vsix(vsix_path):
                        cli_warning = f" CLI returned {cli_returncode}; manual installation fallback failed."
                    else:
                        cli_warning = f" CLI returned {cli_returncode}; manual installation fallback completed."
                else:
                    cli_warning = f" CLI returned {cli_returncode}; final installation evidence was used."
            extension_dir, evidence_error = self._registration_candidate()
            if extension_dir is None and self.command_runner is None:
                # If a launcher/shim ignored --extensions-dir, install directly into the target extensions_dir.
                if self._manual_install_vsix(vsix_path):
                    extension_dir, evidence_error = self._registration_candidate()
            if extension_dir is None:
                return AdapterResult(self.target, "failed", True, False, f"{self.target} extension installation evidence failed: {evidence_error}{cli_warning}")
            self._extension_dir = extension_dir

            for mirror_settings, mirror_extensions in self.spec.mirror_targets:
                self._remove_installed_extension_state_in(mirror_extensions)
                self._apply_theme_settings_to(mirror_settings, active_mode, allow_missing=True)
                if not self._manual_install_vsix_to(vsix_path, mirror_extensions):
                    return AdapterResult(self.target, "failed", True, False, f"{self.target} mirror extension installation failed at {mirror_extensions}")

            status = "partial" if cli_returncode not in (0, None) else "ok"
            return AdapterResult(
                self.target, status, True, False, f"{self.target} VSIX installed and theme selected.{cli_warning}",
                metadata={
                    "field_capabilities": self._field_capabilities("applied"),
                    "generated_values": build_theme_json(plan, self._theme_label(plan.mode), baseline=self.spec.color_baseline)["colors"],
                    "theme_registration": "applied",
                    "theme_activation": "applied",
                    "theme_labels": list(self._theme_labels()),
                    "auto_detect_enabled": settings.get("window.autoDetectColorScheme") is True,
                    "target_instance": self.target_instance(),
                    "cli_returncode": cli_returncode,
                    "cli_diagnostic": cli_diagnostic,
                },
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
            return AdapterResult(self.target, "failed", False, False, f"{self.target} apply failed: {error}")

    def _verify_instance_target(self, plan: Plan, settings_path: Path, extensions_dir: Path, preferred_dir: Path | None = None) -> tuple[bool, str]:
        if not settings_path.is_file():
            return False, f"{self.target} settings not found at {settings_path}"
        settings = self._read_settings_at(settings_path)
        candidates = self._registered_extension_dirs_in(extensions_dir)
        extension_dir = preferred_dir if preferred_dir in candidates else (
            max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
        )
        contributed_labels = self._contributed_labels(extension_dir) if extension_dir else None
        labels_ok = contributed_labels is not None and set(self._theme_labels()) <= contributed_labels
        verified = (
            settings.get("workbench.colorTheme") in self._theme_labels()
            and settings.get("workbench.preferredDarkColorTheme") == self._theme_label("dark")
            and settings.get("workbench.preferredLightColorTheme") == self._theme_label("light")
            and settings.get("window.autoDetectColorScheme") is True
            and extension_dir is not None
            and self._theme_files(extension_dir) is not None
            and labels_ok
        )
        if not verified:
            return False, f"{self.target} theme verification failed"
        for mode, path in zip(("dark", "light"), self._theme_files(extension_dir)):
            actual = json.loads(path.read_text(encoding="utf-8"))
            expected = build_theme_json(plan, self._theme_label(mode), mode, baseline=self.spec.color_baseline)
            if actual != expected:
                return False, f"{self.target} {mode} theme contents do not match Plan"
        return True, ""

    def verify(self, plan: Plan) -> AdapterResult:
        if not self.spec.color_baseline:
            return AdapterResult(self.target, "skipped", False, False, "Workbench color baseline is unverified")
        try:
            ok, error_message = self._verify_instance_target(plan, self.spec.settings_path, self.spec.extensions_dir, self._extension_dir)
            if not ok:
                return AdapterResult(self.target, "failed", False, False, error_message)
            for mirror_settings, mirror_extensions in self.spec.mirror_targets:
                m_ok, m_error = self._verify_instance_target(plan, mirror_settings, mirror_extensions)
                if not m_ok:
                    return AdapterResult(self.target, "failed", False, False, m_error)
            settings = self._read_settings()
            ai_supported = self.spec.ai_panel_supported if self.spec.ai_panel_supported is not None else (self.target == "vscode")
            if ai_supported:
                status = "ok"
                message = f"{self.target} registration and active theme verified"
            else:
                status = "partial"
                message = f"{self.target} registration and active theme verified; AI-specific panels are outside standard theme fields"
            return AdapterResult(
                self.target,
                status,
                False,
                True,
                message,
                metadata={
                    "field_capabilities": self._field_capabilities("verified"),
                    "generated_values": build_theme_json(plan, self._theme_label(plan.mode), baseline=self.spec.color_baseline)["colors"],
                    "theme_registration": "verified",
                    "theme_activation": "verified",
                    "theme_labels": list(self._theme_labels()),
                    "auto_detect_enabled": settings.get("window.autoDetectColorScheme") is True,
                },
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"{self.target} verify failed: {error}")

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        state_path = backup_dir / f"{self.target}-settings-state.json"
        backup = backup_dir / f"{self.target}-settings.json"
        primary_existed = True
        primary_entries: Mapping[str, Any] | None = None
        mirror_states: list[dict[str, Any]] = []
        if state_path.is_file():
            try:
                loaded_state = json.loads(state_path.read_text(encoding="utf-8"))
                primary_existed = bool(loaded_state.get("primary_exists", True))
                raw_primary_entries = loaded_state.get("primary_entries")
                if isinstance(raw_primary_entries, dict):
                    primary_entries = raw_primary_entries
                mirror_states = list(loaded_state.get("mirrors", []))
            except (OSError, json.JSONDecodeError):
                primary_existed = True
        if primary_existed and not backup.is_file():
            return AdapterResult(self.target, "failed", False, False, f"{self.target} settings backup not found")
        try:
            primary_settings_restored = self._restore_settings_file(
                self.spec.settings_path,
                backup,
                primary_existed,
                primary_entries,
            )
            extensions_restored = self._restore_extension_state(backup_dir)
            restored = primary_settings_restored and extensions_restored

            mirror_state_by_idx = {int(item["index"]): item for item in mirror_states if isinstance(item, dict) and "index" in item}
            for idx, (mirror_settings, mirror_extensions) in enumerate(self.spec.mirror_targets):
                prefix = f"{self.target}-mirror-{idx}"
                m_backup = backup_dir / f"{prefix}-settings.json"
                m_state = mirror_state_by_idx.get(idx, {})
                m_existed = bool(m_state.get("settings_exists", m_backup.is_file()))
                m_entries = m_state.get("settings_entries") if isinstance(m_state.get("settings_entries"), dict) else None
                m_settings_ok = self._restore_settings_file(mirror_settings, m_backup, m_existed, m_entries)
                m_ext_ok = self._restore_extension_state_in(mirror_extensions, backup_dir, prefix)
                restored = restored and m_settings_ok and m_ext_ok
            return AdapterResult(self.target, "ok" if restored else "failed", True, restored, f"{self.target} settings and extension restored")
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"{self.target} rollback failed: {error}")
