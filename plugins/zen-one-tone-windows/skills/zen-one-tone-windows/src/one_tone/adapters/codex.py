from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any, Mapping

from ..plan import Plan
from ..storage import atomic_write_text
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
    if not isinstance(desktop, dict) or desktop.get("appearanceTheme") not in {"dark", "light", "system"}:
        return False
    for table_name in ("appearanceLightChromeTheme", "appearanceDarkChromeTheme"):
        theme = desktop.get(table_name)
        if not isinstance(theme, dict):
            return False
        if any(not isinstance(theme.get(key), str) for key in _THEME_FIELDS):
            return False
        if not isinstance(theme.get("contrast"), (int, float)) or isinstance(theme.get("contrast"), bool):
            return False
        if not isinstance(theme.get("opaqueWindows"), bool):
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


def _theme_updates(palettes: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {}
    for table_name, mode in zip(_THEME_TABLES, ("light", "dark")):
        palette = palettes[mode]
        updates[table_name] = {
            "accent": palette["accent"],
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
        if "fonts" not in desktop[table_name.split(".", 1)[1]]
    )


def _replace_verified_values(
    text: str,
    palettes: Mapping[str, Mapping[str, str]],
    missing_font_tables: tuple[str, ...],
) -> str:
    updates = _theme_updates(palettes)
    section = ""
    output: list[str] = []
    header_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*(?:\r?\n)?$")
    assignment_pattern = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*?)(\r?\n)?$")
    for line in text.splitlines(keepends=True):
        header = header_pattern.match(line)
        if header:
            section = header.group(1)
            output.append(line)
            continue
        assignment = assignment_pattern.match(line)
        replacement = updates.get(section, {}).get(assignment.group(2)) if assignment else None
        if replacement is None:
            output.append(line)
            continue
        newline = assignment.group(5) or ""
        output.append(f"{assignment.group(1)}{assignment.group(2)}{assignment.group(3)}{json.dumps(replacement)}{newline}")
    for table_name in missing_font_tables:
        if output and not output[-1].endswith(("\n", "\r")):
            output.append("\n")
        output.append(f"\n[{table_name}.fonts]\n")
    return "".join(output)


def _matches_plan(payload: dict[str, Any], plan: Plan) -> bool:
    desktop = payload["desktop"]
    for full_table_name, mode in zip(_THEME_TABLES, ("light", "dark")):
        theme = desktop[full_table_name.split(".", 1)[1]]
        palette = plan.palette_for(mode)
        expected = {
            "accent": palette["accent"],
            "contrast": 100,
            "ink": palette["foreground"],
            "opaqueWindows": True,
            "surface": palette["surface"],
        }
        if any(theme.get(key) != value for key, value in expected.items()):
            return False
        if not isinstance(theme.get("fonts"), dict):
            return False
        semantic = theme.get("semanticColors")
        if isinstance(semantic, dict):
            expected_semantic = {
                "diffAdded": palette["success_text"],
                "diffRemoved": palette["error_text"],
                "skill": palette["accent_text"],
            }
            if any(key in semantic and semantic[key] != value for key, value in expected_semantic.items()):
                return False
    return True


class CodexAdapter:
    target = "chatgpt-app"

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = locate_verified_codex_config(config_path)

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
            f"verified ChatGPT App config.toml: {self.config_path}{repair_message}",
            version=CHATGPT_APP_CONFIG_SCHEMA_V1,
            metadata={"field_capabilities": field_capabilities(self.target)},
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        if self._document() is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.config_path, backup_dir / "codex-config.toml")
            return AdapterResult(self.target, "ok", False, True, "ChatGPT App config.toml snapshot saved", version=CHATGPT_APP_CONFIG_SCHEMA_V1)
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"ChatGPT App snapshot failed: {error}", version=CHATGPT_APP_CONFIG_SCHEMA_V1)

    def apply(self, plan: Plan) -> AdapterResult:
        document = self._document()
        if document is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        original, payload = document
        updated = _replace_verified_values(
            original,
            {mode: plan.palette_for(mode) for mode in ("light", "dark")},
            _missing_font_tables(payload),
        )
        try:
            atomic_write_text(self.config_path, updated, newline="")
            return AdapterResult(self.target, "ok", updated != original, False, "ChatGPT App config.toml theme written", version=CHATGPT_APP_CONFIG_SCHEMA_V1)
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
            "ChatGPT App config.toml theme verified" if verified else "ChatGPT App config.toml theme does not match Plan",
            version=CHATGPT_APP_CONFIG_SCHEMA_V1,
            metadata={"field_capabilities": field_capabilities(self.target)},
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        if self.config_path is None:
            return _skip_result(f"ChatGPT App config.toml does not match {CHATGPT_APP_CONFIG_SCHEMA_V1}")
        backup = backup_dir / "codex-config.toml"
        if not backup.is_file():
            return AdapterResult(self.target, "failed", False, False, "ChatGPT App config.toml backup not found", version=CHATGPT_APP_CONFIG_SCHEMA_V1)
        try:
            shutil.copy2(backup, self.config_path)
            restored = self.config_path.read_bytes() == backup.read_bytes()
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
