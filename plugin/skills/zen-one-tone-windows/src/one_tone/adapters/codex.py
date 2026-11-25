from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any, Mapping

from ..plan import Plan
from ..inventory import inventory_groups, inventory_report
from ..storage import atomic_write_bytes, atomic_write_text
from .base import AdapterResult, field_capabilities

CHATGPT_APP_CONFIG_SCHEMA_V1 = "chatgpt-app-config-v1"
_THEME_TABLES = (
    "desktop.appearanceLightChromeTheme",
    "desktop.appearanceDarkChromeTheme",
)
_THEME_FIELDS = ("accent", "ink", "surface")
_SEMANTIC_FIELDS = ("diffAdded", "diffRemoved", "skill")


def default_codex_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "config.toml"
    userprofile = os.environ.get("USERPROFILE")
    home = Path(userprofile) if userprofile else Path.home()
    return home / ".codex" / "config.toml"


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _load_payload(path: Path) -> tuple[str, dict[str, Any]] | None:
    try:
        text = _read_text(path)
        payload = tomllib.loads(text)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return text, payload


def _is_v1_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    desktop = payload.get("desktop")
    if not isinstance(desktop, dict):
        return False
    appearance_theme = desktop.get("appearanceTheme")
    has_theme_table = any(name in desktop for name in ("appearanceLightChromeTheme", "appearanceDarkChromeTheme"))
    if appearance_theme is None and not has_theme_table:
        return False
    if appearance_theme is not None and appearance_theme not in {"dark", "light", "system"}:
        return False
    for table_name in ("appearanceLightChromeTheme", "appearanceDarkChromeTheme"):
        if table_name not in desktop:
            continue
        theme = desktop.get(table_name)
        if not isinstance(theme, dict):
            return False
        if any(key in theme and not isinstance(theme.get(key), str) for key in _THEME_FIELDS):
            return False
        if "accentSource" in theme and not isinstance(theme.get("accentSource"), str):
            return False
        if "contrast" in theme and (not isinstance(theme.get("contrast"), (int, float)) or isinstance(theme.get("contrast"), bool)):
            return False
        if "opaqueWindows" in theme and not isinstance(theme.get("opaqueWindows"), bool):
            return False
        for optional_table in ("fonts", "semanticColors"):
            value = theme.get(optional_table)
            if value is not None and not isinstance(value, dict):
                return False
        semantic = theme.get("semanticColors")
        if isinstance(semantic, dict) and any(
            key in semantic and not isinstance(semantic[key], str) for key in _SEMANTIC_FIELDS
        ):
            return False
    return True


def locate_verified_codex_config(explicit_path: Path | None = None) -> Path | None:
    path = explicit_path or default_codex_config_path()
    loaded = _load_payload(path) if path.is_file() else None
    if loaded is None or not _is_v1_payload(loaded[1]):
        return None
    return path


def _skip_result(message: str) -> AdapterResult:
    return AdapterResult("chatgpt-app", "skipped", False, False, message)


def _theme_metadata(plan: Plan | None = None, status: str = "supported", *, target_instance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    statuses = {name: status if capability == "supported" else capability for name, capability in field_capabilities("chatgpt-app").items()}
    values = {f"{table.removeprefix('desktop.')}.{key}": value for table, entries in _theme_updates(plan.palettes).items() for key, value in entries.items()} if plan else {}
    if plan:
        values["appearanceTheme"] = "system"
    metadata: dict[str, Any] = {
        "field_capabilities": statuses,
        "generated_values": values,
        "field_inventory": inventory_report("chatgpt-app", statuses, values),
        "field_groups": inventory_groups("chatgpt-app", statuses, values),
        "rendering_verification": "untested",
        "embedded_terminal": {
            "status": "unsupported",
            "reason": "The embedded terminal uses an independent xterm/CSS theme; no verified user setting exposes its ANSI table or minimumContrastRatio",
        },
    }
    if target_instance is not None:
        metadata["target_instance"] = dict(target_instance)
    return metadata


def _theme_updates(palettes: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {"desktop": {"appearanceTheme": "system"}}
    for table_name, mode in zip(_THEME_TABLES, ("light", "dark")):
        palette = palettes[mode]
        updates[table_name] = {
            "accent": palette["accent"],
            "accentSource": "custom",
            "contrast": 100,
            "ink": palette["foreground"],
            "opaqueWindows": True,
            "surface": palette["surface"],
        }
        updates[f"{table_name}.semanticColors"] = {
            "diffAdded": palette["success_text"],
            "diffRemoved": palette["error_text"],
            "skill": palette["accent_text"],
        }
    return updates


def _missing_font_tables(payload: dict[str, Any]) -> tuple[str, ...]:
    desktop = payload["desktop"]
    return tuple(
        table_name
        for table_name in _THEME_TABLES
        if not isinstance(desktop.get(table_name.split(".", 1)[1]), dict)
        or "fonts" not in desktop[table_name.split(".", 1)[1]]
    )


def _replace_verified_values(
    text: str,
    palettes: Mapping[str, Mapping[str, str]],
    missing_font_tables: tuple[str, ...],
) -> str:
    updates = _theme_updates(palettes)
    pending = {section: dict(values) for section, values in updates.items()}
    section = ""
    output: list[str] = []
    header_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?(?:\r?\n)?$")
    assignment_pattern = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*?)(\r?\n)?$")
    for line in text.splitlines(keepends=True):
        header = header_pattern.match(line)
        if header:
            if output and not output[-1].endswith(("\n", "\r")):
                output.append("\n")
            for key, value in pending.pop(section, {}).items():
                output.append(f"{key} = {json.dumps(value)}\n")
            section = header.group(1)
            output.append(line)
            continue
        assignment = assignment_pattern.match(line)
        if assignment and section in _THEME_TABLES and assignment.group(2) == "semanticColors":
            # Replace inline semanticColors = { ... } by omitting it here so the managed table block is emitted cleanly.
            continue
        replacement = updates.get(section, {}).get(assignment.group(2)) if assignment else None
        if replacement is None:
            output.append(line)
            continue
        newline = assignment.group(5) or ""
        pending.get(section, {}).pop(assignment.group(2), None)
        output.append(f"{assignment.group(1)}{assignment.group(2)}{assignment.group(3)}{json.dumps(replacement)}{newline}")
    if output and not output[-1].endswith(("\n", "\r")):
        output.append("\n")
    for key, value in pending.pop(section, {}).items():
        output.append(f"{key} = {json.dumps(value)}\n")
    for table_name, values in pending.items():
        if values:
            output.append(f"\n[{table_name}]\n")
            output.extend(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    for table_name in missing_font_tables:
        if output and not output[-1].endswith(("\n", "\r")):
            output.append("\n")
        output.append(f"\n[{table_name}.fonts]\n")
    return "".join(output)


def _matches_plan(payload: dict[str, Any], plan: Plan) -> bool:
    desktop = payload["desktop"]
    if desktop.get("appearanceTheme") != "system":
        return False
    updates = _theme_updates(plan.palettes)
    for full_table_name, mode in zip(_THEME_TABLES, ("light", "dark")):
        theme = desktop.get(full_table_name.split(".", 1)[1])
        if not isinstance(theme, dict):
            return False
        expected = updates[full_table_name]
        if any(theme.get(key) != value for key, value in expected.items()):
            return False
        if not isinstance(theme.get("fonts"), dict):
            return False
        semantic = theme.get("semanticColors")
        expected_semantic = updates[f"{full_table_name}.semanticColors"]
        if not isinstance(semantic, dict) or any(semantic.get(key) != value for key, value in expected_semantic.items()):
            return False
    return True


class CodexAdapter:
    target = "chatgpt-app"

    def __init__(self, config_path: Path | None = None, *, target_instance: Mapping[str, Any] | None = None) -> None:
        self._frozen_instance: dict[str, Any] | None = dict(target_instance) if target_instance is not None else None
        if self._frozen_instance is not None:
            raw_path = self._frozen_instance.get("config_path")
            if self._frozen_instance.get("status") == "ok" and isinstance(raw_path, str) and raw_path and Path(raw_path).is_absolute():
                self.config_path: Path | None = Path(raw_path)
            else:
                self.config_path = None
        else:
            self.config_path = locate_verified_codex_config(config_path)

    def target_instance(self) -> dict[str, Any]:
        if self._frozen_instance is not None:
            return dict(self._frozen_instance)
        document = self._document()
        if self.config_path is None or document is None:
            return {"status": "skipped", "reason": f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}"}
        return {"status": "ok", "config_path": str(self.config_path.resolve())}

    def _document(self) -> tuple[str, dict[str, Any]] | None:
        if self.config_path is None:
            return None
        loaded = _load_payload(self.config_path)
        if loaded is None or not _is_v1_payload(loaded[1]):
            return None
        return loaded

    def detect(self) -> AdapterResult:
        if self.config_path is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        document = self._document()
        if document is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        missing_font_tables = _missing_font_tables(document[1])
        repair_message = (
            f"; Apply will add {', '.join(f'{table}.fonts' for table in missing_font_tables)}"
            if missing_font_tables
            else ""
        )
        return AdapterResult(
            self.target,
            "ok",
            False,
            not missing_font_tables,
            f"verified ChatGPT App config.toml: {self.config_path}{repair_message}; embedded terminal unsupported; rendering untested",
            version=CHATGPT_APP_CONFIG_SCHEMA_V1,
            metadata=_theme_metadata(target_instance=self.target_instance()),
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        if self._document() is None or self.config_path is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.config_path, backup_dir / "codex-config.toml")
            return AdapterResult(
                self.target,
                "ok",
                False,
                True,
                "ChatGPT App config.toml snapshot saved",
                version=CHATGPT_APP_CONFIG_SCHEMA_V1,
                metadata={"target_instance": self.target_instance()},
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"ChatGPT App snapshot failed: {error}", version=CHATGPT_APP_CONFIG_SCHEMA_V1)

    def apply(self, plan: Plan) -> AdapterResult:
        document = self._document()
        if document is None or self.config_path is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        original, payload = document
        updated = _replace_verified_values(
            original,
            {mode: plan.palette_for(mode) for mode in ("light", "dark")},
            _missing_font_tables(payload),
        )
        try:
            candidate = tomllib.loads(updated)
            if not _is_v1_payload(candidate) or not _matches_plan(candidate, plan):
                return _skip_result("ChatGPT App TOML layout cannot be safely updated; configuration preserved")
            atomic_write_text(self.config_path, updated, newline="")
            return AdapterResult(
                self.target,
                "ok",
                updated != original,
                False,
                "ChatGPT App config.toml theme written",
                version=CHATGPT_APP_CONFIG_SCHEMA_V1,
                metadata=_theme_metadata(plan, "applied", target_instance=self.target_instance()),
            )
        except tomllib.TOMLDecodeError:
            return _skip_result("ChatGPT App TOML layout cannot be safely updated; configuration preserved")
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"ChatGPT App apply failed: {error}", version=CHATGPT_APP_CONFIG_SCHEMA_V1)

    def verify(self, plan: Plan) -> AdapterResult:
        document = self._document()
        if document is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        verified = _matches_plan(document[1], plan)
        return AdapterResult(
            self.target,
            "ok" if verified else "failed",
            False,
            verified,
            "ChatGPT App config.toml theme verified; embedded terminal unsupported; rendering untested" if verified else "ChatGPT App config.toml theme does not match Plan; rendering untested",
            version=CHATGPT_APP_CONFIG_SCHEMA_V1,
            metadata=_theme_metadata(plan, "verified" if verified else "failed", target_instance=self.target_instance()),
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        target_path = self.config_path
        if target_path is None and isinstance(metadata, Mapping) and isinstance(metadata.get("target_instance"), Mapping):
            raw_meta_path = metadata["target_instance"].get("config_path")
            if isinstance(raw_meta_path, str) and raw_meta_path and Path(raw_meta_path).is_absolute():
                target_path = Path(raw_meta_path)
        if target_path is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        backup = backup_dir / "codex-config.toml"
        if not backup.is_file():
            return AdapterResult(self.target, "failed", False, False, "ChatGPT App config.toml backup not found", version=CHATGPT_APP_CONFIG_SCHEMA_V1)
        try:
            backup_bytes = backup.read_bytes()
            atomic_write_bytes(target_path, backup_bytes)
            restored = target_path.read_bytes() == backup_bytes
            return AdapterResult(
                self.target,
                "ok" if restored else "failed",
                True,
                restored,
                "ChatGPT App config.toml restored" if restored else "ChatGPT App config.toml restore verification failed",
                version=CHATGPT_APP_CONFIG_SCHEMA_V1,
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"ChatGPT App rollback failed: {error}", version=CHATGPT_APP_CONFIG_SCHEMA_V1)
