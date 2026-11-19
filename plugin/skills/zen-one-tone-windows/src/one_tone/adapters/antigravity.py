from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from ..inventory import inventory_groups, inventory_report
from ..plan import Plan
from ..storage import atomic_write_text
from .base import AdapterResult, field_capabilities

try:
    import winreg
except ImportError:  # pragma: no cover - production target is Windows.
    winreg = None

ANTIGRAVITY_CONFIG_SCHEMA_V1 = "antigravity-config-v1"
_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_SEED_KEYS = (
    "background",
    "primary",
    "foregroundOverride",
    "primaryForegroundOverride",
    "codeForegroundOverride",
)


def detect_windows_app_mode() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
    except OSError:
        return None
    return "light" if value == 1 else "dark" if value == 0 else None


def default_antigravity_config_path() -> Path:
    configured = os.environ.get("ONE_TONE_ANTIGRAVITY_CONFIG")
    if configured:
        return Path(configured)
    userprofile = os.environ.get("USERPROFILE")
    home = Path(userprofile) if userprofile else Path.home()
    return home / ".gemini" / "config" / "config.json"


def default_antigravity_storage_path() -> Path:
    configured = os.environ.get("ONE_TONE_ANTIGRAVITY_STORAGE")
    if configured:
        return Path(configured)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Antigravity" / "app_storage.json"
    userprofile = os.environ.get("USERPROFILE")
    home = Path(userprofile) if userprofile else Path.home()
    return home / "AppData" / "Roaming" / "Antigravity" / "app_storage.json"


def _seed_values(palette: Mapping[str, str]) -> dict[str, str]:
    return {
        "background": palette["surface"],
        "primary": palette["accent"],
        "foregroundOverride": palette["foreground"],
        "primaryForegroundOverride": palette["accent_foreground"],
        "codeForegroundOverride": palette["accent_text"],
    }


def _effective_hub_mode(plan: Plan, explicit_mode: str | None = None) -> str:
    if explicit_mode in {"light", "dark"}:
        return explicit_mode
    instance_mode = plan.target_instances.get("antigravity", {}).get("app_mode")
    if instance_mode in {"light", "dark"}:
        return str(instance_mode)
    return plan.mode


def _generated_values(plan: Plan, hub_mode: str | None = None) -> dict[str, Any]:
    effective_mode = _effective_hub_mode(plan, hub_mode)
    values: dict[str, Any] = {
        "userSettings.themeMode": "THEME_MODE_INHERIT",
        "hubSurfaceBackgroundColor": plan.palette_for(effective_mode)["surface"],
    }
    for table, mode in (("customThemeSeedsLight", "light"), ("customThemeSeedsDark", "dark")):
        for key, value in _seed_values(plan.palette_for(mode)).items():
            values[f"userSettings.{table}.{key}"] = value
    return values


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_valid_config_payload(payload: dict[str, Any]) -> bool:
    user_settings = payload.get("userSettings")
    if user_settings is not None and not isinstance(user_settings, dict):
        return False
    if isinstance(user_settings, dict):
        theme_mode = user_settings.get("themeMode")
        if theme_mode is not None and not isinstance(theme_mode, str):
            return False
        for table in ("customThemeSeedsLight", "customThemeSeedsDark"):
            seeds = user_settings.get(table)
            if seeds is not None and not isinstance(seeds, dict):
                return False
            if isinstance(seeds, dict) and any(
                key in seeds and not isinstance(seeds[key], str) for key in _SEED_KEYS
            ):
                return False
    return True


def _is_valid_storage_payload(payload: dict[str, Any]) -> bool:
    hub_color = payload.get("hubSurfaceBackgroundColor")
    return hub_color is None or isinstance(hub_color, str)


class AntigravityAdapter:
    target = "antigravity"

    def __init__(
        self,
        config_path: Path | None = None,
        storage_path: Path | None = None,
        target_instance: Mapping[str, Any] | None = None,
        app_mode: str | None = None,
        detect_system_mode: bool = False,
    ) -> None:
        instance = dict(target_instance or {})
        self.config_path = Path(str(instance["config_path"])) if instance.get("config_path") else (config_path or default_antigravity_config_path())
        self.storage_path = Path(str(instance["storage_path"])) if instance.get("storage_path") else (storage_path or default_antigravity_storage_path())
        instance_mode = instance.get("app_mode")
        if instance_mode in {"light", "dark"}:
            self.app_mode: str | None = str(instance_mode)
        elif app_mode in {"light", "dark"}:
            self.app_mode = app_mode
        elif detect_system_mode:
            self.app_mode = detect_windows_app_mode()
        else:
            self.app_mode = None

    def _inspect(self) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None, str]:
        config_exists = self.config_path.is_file()
        storage_exists = self.storage_path.is_file()
        if not config_exists and not storage_exists:
            return False, None, None, f"Antigravity config not found: {self.config_path}"
        config_payload: dict[str, Any] = {}
        if config_exists:
            loaded = _load_json_object(self.config_path)
            if loaded is None or not _is_valid_config_payload(loaded):
                return False, None, None, f"Antigravity config.json does not match {ANTIGRAVITY_CONFIG_SCHEMA_V1}"
            config_payload = loaded
        storage_payload: dict[str, Any] = {}
        if storage_exists:
            loaded = _load_json_object(self.storage_path)
            if loaded is None or not _is_valid_storage_payload(loaded):
                return False, None, None, f"Antigravity app_storage.json does not match {ANTIGRAVITY_CONFIG_SCHEMA_V1}"
            storage_payload = loaded
        return True, config_payload, storage_payload, "verified"

    def target_instance(self) -> dict[str, Any]:
        ok, _, _, reason = self._inspect()
        if not ok:
            return {"status": "skipped", "reason": reason}
        instance: dict[str, Any] = {
            "status": "ok",
            "config_path": str(self.config_path),
            "storage_path": str(self.storage_path),
        }
        if self.app_mode in {"light", "dark"}:
            instance["app_mode"] = self.app_mode
        return instance

    def _metadata(self, plan: Plan | None = None, status: str = "supported") -> dict[str, Any]:
        statuses = {
            name: status if capability == "supported" else capability
            for name, capability in field_capabilities(self.target).items()
        }
        values = _generated_values(plan, self.app_mode) if plan else {}
        return {
            "field_capabilities": statuses,
            "generated_values": values,
            "field_inventory": inventory_report(self.target, statuses, values),
            "field_groups": inventory_groups(self.target, statuses, values),
            "target_instance": self.target_instance(),
            "rendering_verification": "untested",
        }

    def detect(self) -> AdapterResult:
        ok, _, _, reason = self._inspect()
        if not ok:
            return AdapterResult(self.target, "skipped", False, False, reason)
        return AdapterResult(
            self.target,
            "ok",
            False,
            True,
            f"verified Antigravity config: {self.config_path}; storage: {self.storage_path}; rendering untested",
            version=ANTIGRAVITY_CONFIG_SCHEMA_V1,
            metadata=self._metadata(),
        )

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        ok, _, _, reason = self._inspect()
        if not ok:
            return AdapterResult(self.target, "skipped", False, False, reason)
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            state = {
                "config_exists": self.config_path.is_file(),
                "storage_exists": self.storage_path.is_file(),
            }
            atomic_write_text(backup_dir / "antigravity-state.json", json.dumps(state, sort_keys=True))
            if state["config_exists"]:
                shutil.copy2(self.config_path, backup_dir / "antigravity-config.json")
            if state["storage_exists"]:
                shutil.copy2(self.storage_path, backup_dir / "antigravity-storage.json")
            return AdapterResult(
                self.target,
                "ok",
                False,
                True,
                "Antigravity config and storage snapshot saved",
                version=ANTIGRAVITY_CONFIG_SCHEMA_V1,
                metadata={"target_instance": self.target_instance()},
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"Antigravity snapshot failed: {error}", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)

    def apply(self, plan: Plan) -> AdapterResult:
        ok, config_payload, storage_payload, reason = self._inspect()
        if not ok or config_payload is None or storage_payload is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        try:
            updated_config = dict(config_payload)
            user_settings = dict(updated_config.get("userSettings") or {})
            user_settings["themeMode"] = "THEME_MODE_INHERIT"
            for table, mode in (("customThemeSeedsLight", "light"), ("customThemeSeedsDark", "dark")):
                existing_seeds = dict(user_settings.get(table) or {})
                existing_seeds.update(_seed_values(plan.palette_for(mode)))
                user_settings[table] = existing_seeds
            updated_config["userSettings"] = user_settings

            updated_storage = dict(storage_payload)
            hub_mode = _effective_hub_mode(plan, self.app_mode)
            updated_storage["hubSurfaceBackgroundColor"] = plan.palette_for(hub_mode)["surface"]

            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(self.config_path, json.dumps(updated_config, ensure_ascii=False, indent=2) + "\n")
            atomic_write_text(self.storage_path, json.dumps(updated_storage, ensure_ascii=False, indent=2) + "\n")
            return AdapterResult(
                self.target,
                "ok",
                True,
                False,
                "Antigravity customThemeSeeds and hubSurfaceBackgroundColor updated",
                version=ANTIGRAVITY_CONFIG_SCHEMA_V1,
                metadata=self._metadata(plan, "applied"),
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"Antigravity apply failed: {error}", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)

    def verify(self, plan: Plan) -> AdapterResult:
        ok, config_payload, storage_payload, reason = self._inspect()
        if not ok or config_payload is None or storage_payload is None:
            return AdapterResult(self.target, "skipped", False, False, reason)
        user_settings = config_payload.get("userSettings")
        verified = isinstance(user_settings, dict) and user_settings.get("themeMode") == "THEME_MODE_INHERIT"
        for table, mode in (("customThemeSeedsLight", "light"), ("customThemeSeedsDark", "dark")):
            seeds = user_settings.get(table) if isinstance(user_settings, dict) else None
            expected = _seed_values(plan.palette_for(mode))
            verified = verified and isinstance(seeds, dict) and all(seeds.get(key) == value for key, value in expected.items())
        hub_mode = _effective_hub_mode(plan, self.app_mode)
        verified = verified and storage_payload.get("hubSurfaceBackgroundColor") == plan.palette_for(hub_mode)["surface"]
        return AdapterResult(
            self.target,
            "ok" if verified else "failed",
            False,
            verified,
            "Antigravity theme verified; rendering untested" if verified else "Antigravity config or storage does not match Plan; rendering untested",
            version=ANTIGRAVITY_CONFIG_SCHEMA_V1,
            metadata=self._metadata(plan, "verified" if verified else "failed"),
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        state_path = backup_dir / "antigravity-state.json"
        if not state_path.is_file():
            return AdapterResult(self.target, "failed", False, False, "Antigravity backup state not found", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            config_backup = backup_dir / "antigravity-config.json"
            storage_backup = backup_dir / "antigravity-storage.json"
            if state.get("config_exists"):
                if not config_backup.is_file():
                    return AdapterResult(self.target, "failed", False, False, "Antigravity config backup not found", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(config_backup, self.config_path)
            elif self.config_path.exists():
                self.config_path.unlink()
            if state.get("storage_exists"):
                if not storage_backup.is_file():
                    return AdapterResult(self.target, "failed", False, False, "Antigravity storage backup not found", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(storage_backup, self.storage_path)
            elif self.storage_path.exists():
                self.storage_path.unlink()
            config_restored = (
                (self.config_path.is_file() and self.config_path.read_bytes() == config_backup.read_bytes())
                if state.get("config_exists")
                else not self.config_path.exists()
            )
            storage_restored = (
                (self.storage_path.is_file() and self.storage_path.read_bytes() == storage_backup.read_bytes())
                if state.get("storage_exists")
                else not self.storage_path.exists()
            )
            restored = config_restored and storage_restored
            return AdapterResult(
                self.target,
                "ok" if restored else "failed",
                True,
                restored,
                "Antigravity config and storage restored" if restored else "Antigravity restore verification failed",
                version=ANTIGRAVITY_CONFIG_SCHEMA_V1,
            )
        except (OSError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Antigravity rollback failed: {error}", version=ANTIGRAVITY_CONFIG_SCHEMA_V1)
