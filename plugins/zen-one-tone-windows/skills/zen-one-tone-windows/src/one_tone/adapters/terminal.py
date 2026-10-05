from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from ..palette import contrast_ratio, parse_hex_color
from ..plan import Plan
from ..field_mappings import TERMINAL_APPEARANCE_FIELDS, terminal_capabilities, terminal_palette_key, terminal_scheme_colors
from ..storage import atomic_write_text
from .base import AdapterResult, field_capabilities

_SCHEME_NAME = "One Tone"
_THEME_NAME = "One Tone"
_SCHEME_MAPPING = {"light": f"{_SCHEME_NAME} Light", "dark": f"{_SCHEME_NAME} Dark"}
_PSREADLINE_FIELDS = ("InlinePrediction", "ListPrediction", "ListPredictionSelected")
_PROFILE_START = "# >>> one-tone windows-terminal prediction colors >>>"
_PROFILE_END = "# <<< one-tone windows-terminal prediction colors <<<"
_NATIVE_FIELD = "profile.adjustIndistinguishableColors"


def _powershell_probe() -> str:
    return """
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
  throw 'One-Tone requires PowerShell 7 or newer; Windows PowerShell is not selected'
}
Import-Module PSReadLine -ErrorAction SilentlyContinue
$module = Get-Module PSReadLine
$fields = @()
$options = Get-PSReadLineOption -ErrorAction SilentlyContinue
if ($null -ne $options) {
  $fields = @($options | Get-Member -MemberType Property | Select-Object -ExpandProperty Name | Where-Object { $_ -in @('InlinePredictionColor','ListPredictionColor','ListPredictionSelectedColor') } | ForEach-Object { $_ -replace 'Color$','' })
}
[ordered]@{
  profile = [string]$PROFILE.CurrentUserAllHosts
  version = if ($null -ne $module) { [string]$module.Version } else { '' }
  host_version = [string]$PSVersionTable.PSVersion
  edition = [string]$PSVersionTable.PSEdition
  fields = $fields
} | ConvertTo-Json -Compress
"""


def _powershell_candidates() -> list[Path]:
    configured = os.environ.get("ONE_TONE_POWERSHELL_EXECUTABLE")
    if configured:
        return [Path(configured)]
    resolved = shutil.which("pwsh")
    return [Path(resolved)] if resolved else []


def _ansi_expression(color: str, background: bool = False) -> str:
    red, green, blue = parse_hex_color(color)
    channel = 48 if background else 38
    return f"[char]27 + '[{channel};2;{red};{green};{blue}m'"


def _checked_text_color(palette: Mapping[str, str], role: str, background: str) -> str:
    try:
        color = palette[role]
    except KeyError as error:
        raise ValueError(f"{role} is unavailable in the Plan Palette") from error
    if contrast_ratio(color, background) < 4.5:
        raise ValueError(f"{role} does not meet the required contrast against the Terminal surface")
    return color


def _prediction_profile_block(plan: Plan) -> str:
    light = plan.palette_for("light")
    dark = plan.palette_for("dark")
    prediction_role = terminal_palette_key("InlinePrediction")
    selected_foreground_role = terminal_palette_key("ListPredictionSelected")
    light_prediction = _checked_text_color(light, prediction_role, light["surface"])
    dark_prediction = _checked_text_color(dark, prediction_role, dark["surface"])
    lines = [
        _PROFILE_START,
        "if ($env:WT_SESSION) {",
        "  $oneToneLightMode = $false",
        "  try {",
        "    $oneToneLightMode = ((Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' -Name AppsUseLightTheme -ErrorAction Stop).AppsUseLightTheme -eq 1)",
        "  } catch { }",
        f"  $oneToneInlinePrediction = if ($oneToneLightMode) {{ {_ansi_expression(light_prediction)} }} else {{ {_ansi_expression(dark_prediction)} }}",
        f"  $oneToneListPrediction = if ($oneToneLightMode) {{ {_ansi_expression(light_prediction)} }} else {{ {_ansi_expression(dark_prediction)} }}",
        f"  $oneToneListPredictionSelected = if ($oneToneLightMode) {{ {_ansi_expression(light[selected_foreground_role])} + {_ansi_expression(light['selection_background'], True)} }} else {{ {_ansi_expression(dark[selected_foreground_role])} + {_ansi_expression(dark['selection_background'], True)} }}",
        "  Set-PSReadLineOption -Colors @{",
        "    InlinePrediction = $oneToneInlinePrediction",
        "    ListPrediction = $oneToneListPrediction",
        "    ListPredictionSelected = $oneToneListPredictionSelected",
        "  }",
        "}",
        _PROFILE_END,
    ]
    return "\n".join(lines)


def _replace_profile_block(content: str, block: str) -> str:
    start = content.find(_PROFILE_START)
    end = content.find(_PROFILE_END)
    if (start < 0) != (end < 0) or end >= 0 and end < start:
        raise ValueError("PowerShell Profile contains an incomplete One Tone block")
    if start >= 0:
        end += len(_PROFILE_END)
        return content[:start] + block + content[end:]
    separator = "" if not content or content.endswith(("\n", "\r")) else "\n"
    return content + separator + block + "\n"


def _remove_profile_block(content: str) -> str:
    start = content.find(_PROFILE_START)
    end = content.find(_PROFILE_END)
    if start < 0 or end < start:
        raise ValueError("PowerShell Profile does not contain a complete One Tone block")
    return content[:start] + content[end + len(_PROFILE_END):]


def _restore_managed_profile_block(current: str, original: str) -> str:
    original_start = original.find(_PROFILE_START)
    original_end = original.find(_PROFILE_END)
    if original_start >= 0 and original_end >= original_start:
        original_block = original[original_start:original_end + len(_PROFILE_END)]
        return _replace_profile_block(current, original_block)
    if _PROFILE_START not in current and _PROFILE_END not in current:
        return current
    return _remove_profile_block(current)


def _managed_profile_matches(content: str, original: str) -> bool:
    original_start = original.find(_PROFILE_START)
    original_end = original.find(_PROFILE_END)
    if original_start >= 0 and original_end >= original_start:
        expected = original[original_start:original_end + len(_PROFILE_END)]
        return expected in content
    return _PROFILE_START not in content and _PROFILE_END not in content


def resolve_default_profile(settings: dict[str, Any]) -> tuple[int, str] | None:
    profiles = settings.get("profiles", {})
    profile_list = profiles.get("list", [])
    if not isinstance(profile_list, list):
        return None
    default = profiles.get("default")
    if default is not None:
        for index, profile in enumerate(profile_list):
            if str(profile.get("guid")) == str(default) or profile.get("name") == default:
                return index, "profiles.default resolved by GUID/name"
        return None
    default = settings.get("defaultProfile")
    if default is not None:
        for index, profile in enumerate(profile_list):
            if str(profile.get("guid")) == str(default) or profile.get("name") == default:
                return index, "defaultProfile resolved by GUID/name"
    for index, profile in enumerate(profile_list):
        if not profile.get("source"):
            return index, "profiles.default is null; first local profile selected"
    return None


def _profile_appearances(settings: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    profiles = settings["profiles"]
    parents = (profiles.get("defaults", {}), *profiles.get("list", []))
    return (*parents, *(profile["unfocusedAppearance"] for profile in parents if isinstance(profile.get("unfocusedAppearance"), dict)))


def _palette_colors(plan: Plan, mode: str | None = None) -> dict[str, str]:
    return terminal_scheme_colors(plan.palette_for(mode or plan.mode))


def _scheme_colors(plan: Plan, mode: str | None = None) -> dict[str, str]:
    colors = _palette_colors(plan, mode)
    palette = plan.palette_for(mode or plan.mode)
    name = _SCHEME_NAME if mode is None else f"{_SCHEME_NAME} {mode.title()}"
    return {"name": name, "cursorColor": palette["accent_text"], **colors}


def _theme_colors(plan: Plan, mode: str | None = None, capabilities: Mapping[str, str] | None = None) -> dict[str, Any]:
    palette = plan.palette_for(mode or plan.mode)
    name = _THEME_NAME if mode is None else f"{_THEME_NAME} {mode.title()}"
    theme = {
        "name": name,
        "window": {
            "applicationTheme": "system",
            "frame": palette[terminal_palette_key("window.frame")],
            "unfocusedFrame": palette[terminal_palette_key("window.unfocusedFrame")],
        },
        "tabRow": {
            "background": palette[terminal_palette_key("tabRow.background")],
            "unfocusedBackground": palette[terminal_palette_key("tabRow.unfocusedBackground")],
        },
        "tab": {
            "background": palette[terminal_palette_key("tab.background")],
            "unfocusedBackground": palette[terminal_palette_key("tab.unfocusedBackground")],
        },
    }
    capabilities = capabilities or terminal_capabilities(plan.target_instances.get("terminal", {}))
    for field in ("window.frame", "window.unfocusedFrame"):
        if capabilities.get(field) != "supported":
            theme["window"].pop(field.split(".")[1], None)
    if capabilities.get("window.useMica") == "supported":
        theme["window"]["useMica"] = False
    return theme


def _generated_values(plan: Plan) -> dict[str, Any]:
    palette = plan.palette_for(plan.mode)
    theme = _theme_colors(plan)
    try:
        profile = _prediction_profile_block(plan)
    except ValueError:
        profile = None
    values = {
        **_scheme_colors(plan),
        "profile.colorScheme": dict(_SCHEME_MAPPING),
        **{name: value for name, (value, _) in TERMINAL_APPEARANCE_FIELDS.items()
           if name not in {"window.frame", "window.unfocusedFrame"}},
        "window.applicationTheme": theme["window"]["applicationTheme"],
        **{f"window.{key}": value for key, value in theme["window"].items() if key != "applicationTheme"},
        **{f"tabRow.{key}": value for key, value in theme["tabRow"].items()},
        **{f"tab.{key}": value for key, value in theme["tab"].items()},
    }
    if profile is not None:
        values.update({field: profile for field in _PSREADLINE_FIELDS})
    return values


class TerminalAdapter:
    target = "terminal"

    def __init__(
        self,
        settings_path: Path,
        target_instance: Mapping[str, Any] | None = None,
        powershell_executable: Path | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        discover_shell: bool = False,
        terminal_executable: Path | None = None,
    ) -> None:
        self.settings_path = settings_path
        self._profile_index: int | None = None
        self._resolution_message = ""
        self._target_instance = dict(target_instance or {})
        self._terminal_executable = terminal_executable
        self._native_info = dict(self._target_instance.get("native_correction", {}))
        self._windows_build = self._target_instance.get("windows_build") if self._target_instance else (
            sys.getwindowsversion().build if hasattr(sys, "getwindowsversion") else None
        )
        self._powershell_executable = powershell_executable
        self._command_runner = command_runner or subprocess.run
        self._discover_shell_enabled = discover_shell or command_runner is not None or bool(target_instance)
        self._profile_path: Path | None = None
        self._shell_info: dict[str, Any] = {}
        self._shell_discovered = bool(self._target_instance)
        self._load_shell_instance()

    def _discover_native_correction(self) -> None:
        if self._native_info:
            return
        self._native_info = {"status": "unsupported", "reason": "Windows Terminal version could not be verified"}
        if self._target_instance or self._terminal_executable is None:
            return
        try:
            executable = self._terminal_executable
            shim = executable.with_suffix(".shim")
            if shim.is_file():
                match = re.search(r'^path = "([^"]+)"$', shim.read_text(encoding="utf-8"), re.MULTILINE)
                if not match:
                    return
                executable = Path(match[1])
            # Read the executable version resource without launching a Terminal window.
            escaped = str(executable).replace("'", "''")
            completed = self._command_runner(
                [shutil.which("pwsh") or "pwsh", "-NoProfile", "-NonInteractive", "-Command",
                 f"(Get-Item -LiteralPath '{escaped}').VersionInfo.FileVersion"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            version = (completed.stdout or "").strip()
            match = re.fullmatch(r"(\d+)\.(\d+)\.\d+(?:\.\d+)?", version)
            supported = completed.returncode == 0 and match is not None and tuple(map(int, match.groups())) >= (1, 16)
            self._native_info = {
                "status": "supported" if supported else "unsupported",
                "executable": str(executable), "version": version,
                "reason": "" if supported else "adjustIndistinguishableColors=always requires Windows Terminal >= 1.16",
            }
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            self._native_info["reason"] = f"Windows Terminal capability discovery failed: {error}"

    def _load_shell_instance(self) -> None:
        instance = self._target_instance
        if instance.get("powershell_executable"):
            self._powershell_executable = Path(str(instance["powershell_executable"]))
        if instance.get("profile_path"):
            self._profile_path = Path(str(instance["profile_path"]))
        info = instance.get("psreadline")
        if isinstance(info, dict):
            self._shell_info = dict(info)

    def _discover_shell(self) -> None:
        if self._target_instance or self._shell_discovered:
            return
        self._shell_discovered = True
        if not self._discover_shell_enabled:
            self._shell_info = {"status": "not-applicable", "reason": "PSReadLine discovery disabled for this adapter"}
            return
        candidates = [self._powershell_executable] if self._powershell_executable is not None else _powershell_candidates()
        if not candidates:
            self._shell_info = {"status": "not-applicable", "reason": "PowerShell 7 (pwsh) not found; Windows PowerShell is not selected"}
            return
        fallback: dict[str, Any] = {"status": "unsupported", "reason": "PowerShell hosts do not expose PSReadLine prediction fields"}
        for executable in candidates:
            self._powershell_executable = executable
            try:
                completed = self._command_runner(
                    [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _powershell_probe()],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if completed.returncode != 0:
                    raise ValueError("PowerShell 7 capability probe failed")
                payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
                if not isinstance(payload, dict):
                    raise ValueError("PowerShell capability probe must return a JSON object")
                host_version = str(payload.get("host_version", ""))
                host_major = host_version.split(".", 1)[0]
                if payload.get("edition") != "Core" or not host_major.isdigit() or int(host_major) < 7:
                    raise ValueError("PowerShell 7 host could not be verified; Windows PowerShell is not selected")
                fields = payload.get("fields", [])
                if isinstance(fields, str):
                    fields = [fields]
                if not isinstance(fields, list):
                    raise ValueError("PSReadLine fields must be a list")
                fields = sorted({str(field) for field in fields})
                profile_path = Path(str(payload.get("profile", ""))) if payload.get("profile") else None
                fallback = {
                    "status": "supported" if profile_path is not None and set(_PSREADLINE_FIELDS) <= set(fields) else "unsupported",
                    "version": str(payload.get("version", "")),
                    "host_version": host_version,
                    "edition": "Core",
                    "fields": fields,
                    "reason": "required PSReadLine prediction fields are unavailable" if set(_PSREADLINE_FIELDS) - set(fields) else "",
                }
                if fallback["status"] == "supported":
                    self._profile_path = profile_path
                    self._shell_info = fallback
                    return
            except (OSError, ValueError, IndexError, TypeError, subprocess.TimeoutExpired) as error:
                fallback = {"status": "unsupported", "reason": f"PowerShell capability discovery failed: {error}"}
        self._shell_info = fallback

    def target_instance(self) -> dict[str, Any]:
        self._discover_shell()
        self._discover_native_correction()
        instance: dict[str, Any] = {"status": "ok", "settings_path": str(self.settings_path)}
        instance["native_correction"] = dict(self._native_info)
        instance["windows_build"] = self._windows_build
        if self._powershell_executable is not None:
            instance["powershell_executable"] = str(self._powershell_executable)
        if self._profile_path is not None:
            instance["profile_path"] = str(self._profile_path)
        if self._shell_info:
            instance["psreadline"] = dict(self._shell_info)
        return instance

    def _appearance_capabilities(self) -> dict[str, str]:
        self._discover_native_correction()
        return terminal_capabilities({"native_correction": self._native_info, "windows_build": self._windows_build})

    def _shell_capabilities(self, status: str) -> dict[str, str]:
        return {field: status for field in _PSREADLINE_FIELDS}

    def _metadata(self, status: str = "supported", plan: Plan | None = None, native_status: str | None = None, stage: str = "supported") -> dict[str, Any]:
        self._discover_native_correction()
        capabilities = field_capabilities(self.target, statuses={
            **{name: stage if capability == "supported" else capability for name, capability in field_capabilities(self.target).items()},
            **{name: stage if capability == "supported" else capability for name, capability in self._appearance_capabilities().items()},
            **self._shell_capabilities(status),
            _NATIVE_FIELD: native_status or self._native_info["status"],
        })
        metadata = {
            "field_capabilities": capabilities,
            "target_instance": self.target_instance(),
            "psreadline": dict(self._shell_info),
            "native_correction": dict(self._native_info),
            "rendering_verification": "untested",
            "rendering_limitations": [
                "Configuration matches do not prove final rendering contrast; dim, reverse, selection, ANSI256 and RGB need visual acceptance",
                "A single ANSI table cannot guarantee every application-owned foreground/background pair",
            ],
        }
        if plan is not None:
            metadata["generated_values"] = {name: value for name, value in _generated_values(plan).items()
                                            if capabilities.get(name) not in {"unsupported", "not-applicable"}}
            if self._native_info["status"] == "supported":
                metadata["generated_values"][_NATIVE_FIELD] = "always"
        return metadata

    def _apply_profile(self, plan: Plan) -> tuple[str, str]:
        status = self._shell_info.get("status", "not-applicable")
        if status != "supported":
            return status, str(self._shell_info.get("reason") or "PSReadLine prediction colors are not supported")
        if self._profile_path is None:
            return "unsupported", "PSReadLine Profile path was not discovered"
        try:
            content = self._read_profile() if self._profile_path.is_file() else ""
            atomic_write_text(
                self._profile_path,
                _replace_profile_block(content, _prediction_profile_block(plan)),
                newline="",
            )
            return "applied", "PSReadLine prediction colors updated for Windows Terminal sessions"
        except ValueError as error:
            self._shell_info.update({"status": "unsupported", "reason": f"PSReadLine Profile update skipped: {error}"})
            return "unsupported", f"PSReadLine prediction colors unavailable: {error}"
        except OSError as error:
            self._shell_info.update({"status": "unsupported", "reason": f"PSReadLine Profile update failed: {error}"})
            return "failed", f"PSReadLine Profile update failed: {error}"

    def _verify_profile(self, plan: Plan) -> tuple[str, bool, str]:
        status = self._shell_info.get("status", "not-applicable")
        if status != "supported":
            return status, True, str(self._shell_info.get("reason") or "PSReadLine prediction colors are not supported")
        if self._profile_path is None:
            return "unsupported", True, "PSReadLine Profile path was not discovered"
        try:
            content = self._read_profile() if self._profile_path.is_file() else ""
            expected = _prediction_profile_block(plan)
            return "verified", content.find(expected) >= 0, "PSReadLine prediction colors verified"
        except ValueError as error:
            self._shell_info.update({"status": "unsupported", "reason": f"PSReadLine Profile verify skipped: {error}"})
            return "unsupported", True, f"PSReadLine prediction colors unavailable: {error}"
        except OSError as error:
            return "failed", False, f"PSReadLine Profile verify failed: {error}"

    def _read_profile(self) -> str:
        with self._profile_path.open("r", encoding="utf-8", newline="") as handle:  # type: ignore[union-attr]
            return handle.read()

    def _read(self) -> dict[str, Any]:
        payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Terminal settings must be a JSON object")
        profiles = payload.get("profiles", {})
        if not isinstance(profiles, dict) or not isinstance(profiles.get("defaults", {}), dict):
            raise ValueError("Terminal profiles/defaults must be JSON objects")
        entries = profiles.get("list", [])
        if not isinstance(entries, list) or any(not isinstance(profile, dict) for profile in entries):
            raise ValueError("Terminal Profile list must contain JSON objects")
        return payload

    def detect(self) -> AdapterResult:
        if not self.settings_path.is_file():
            return AdapterResult(self.target, "skipped", False, False, f"Terminal settings not found: {self.settings_path}")
        try:
            self._discover_shell()
            self._discover_native_correction()
            settings = self._read()
            resolved = resolve_default_profile(settings)
            if resolved is None:
                return AdapterResult(self.target, "skipped", False, False, "Terminal default Profile could not be resolved")
            self._profile_index, self._resolution_message = resolved
            shell_status = self._shell_info.get("status", "not-applicable")
            status = "partial" if shell_status == "unsupported" or self._native_info["status"] != "supported" else "ok"
            shell_message = self._shell_info.get("reason") or "PSReadLine prediction capability discovered"
            return AdapterResult(
                self.target, status, False, True,
                f"Terminal Profile detected; {self._resolution_message}; {shell_message}; native correction {self._native_info['status']}; rendering untested",
                status == "partial", metadata=self._metadata(shell_status),
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Terminal detect failed: {error}")

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        if not self.settings_path.is_file():
            return AdapterResult(self.target, "failed", False, False, "Terminal settings not found")
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.settings_path, backup_dir / "terminal-settings.json")
            self._discover_shell()
            if self._profile_path is not None:
                profile_state = {"exists": self._profile_path.is_file()}
                atomic_write_text(backup_dir / "powershell-profile-state.json", json.dumps(profile_state))
                if self._profile_path.is_file():
                    shutil.copy2(self._profile_path, backup_dir / "powershell-profile.ps1")
            return AdapterResult(
                self.target, "ok", False, True, "Terminal settings snapshot saved",
                metadata={"target_instance": self.target_instance()},
            )
        except OSError as error:
            return AdapterResult(self.target, "failed", False, False, f"Terminal snapshot failed: {error}")

    def apply(self, plan: Plan) -> AdapterResult:
        try:
            settings = self._read()
            resolved = resolve_default_profile(settings)
            if resolved is None:
                return AdapterResult(self.target, "failed", False, False, "Terminal default Profile could not be resolved")
            self._profile_index, self._resolution_message = resolved
            self._discover_native_correction()
            profile_color_keys = (*_palette_colors(plan), "cursorColor")
            settings["profiles"].setdefault("defaults", {})
            appearance_capabilities = self._appearance_capabilities()
            profile_scheme = dict(_SCHEME_MAPPING) if appearance_capabilities["profile.colorScheme"] == "supported" else _SCHEME_MAPPING[plan.mode]
            for profile in _profile_appearances(settings):
                if not isinstance(profile, dict):
                    continue
                for key in profile_color_keys:
                    profile.pop(key, None)
                profile["colorScheme"] = profile_scheme
                if appearance_capabilities["profile.tabColor"] == "supported":
                    profile.pop("tabColor", None)
                profile.pop("selectionForeground", None)
                if appearance_capabilities["profile.useAcrylic"] == "supported":
                    profile["useAcrylic"] = False
                if appearance_capabilities["profile.backgroundImage"] == "supported":
                    profile["backgroundImage"] = ""
                if appearance_capabilities["profile.opacity"] == "supported":
                    profile["opacity"] = 100
                    profile.pop("acrylicOpacity", None)
                if self._native_info["status"] == "supported":
                    profile["adjustIndistinguishableColors"] = "always"
            schemes = [item for item in settings.get("schemes", []) if item.get("name") != _SCHEME_NAME]
            schemes = [item for item in schemes if not str(item.get("name", "")).startswith(f"{_SCHEME_NAME} ")]
            schemes.extend(_scheme_colors(plan, mode) for mode in ("light", "dark"))
            settings["schemes"] = schemes
            themes = [item for item in settings.get("themes", []) if isinstance(item, dict) and item.get("name") != _THEME_NAME]
            themes = [item for item in themes if not str(item.get("name", "")).startswith(f"{_THEME_NAME} ")]
            previous_themes = {item.get("name"): item for item in settings.get("themes", []) if isinstance(item, dict)}
            for mode in ("light", "dark"):
                theme = _theme_colors(plan, mode, appearance_capabilities)
                active_name = settings.get("theme")
                if isinstance(active_name, dict):
                    active_name = active_name.get(mode)
                previous = previous_themes.get(theme["name"], previous_themes.get(_THEME_NAME, previous_themes.get(active_name, {})))
                for section in ("window", "tab", "tabRow"):
                    theme[section] = {**previous.get(section, {}), **theme.get(section, {})}
                theme = {**previous, **theme}
                themes.append(theme)
            settings["themes"] = themes
            settings["theme"] = dict(_SCHEME_MAPPING) if appearance_capabilities["theme"] == "supported" else "system"
            atomic_write_text(
                self.settings_path,
                json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            )
            self._discover_shell()
            shell_status, shell_message = self._apply_profile(plan)
            limited = "unsupported" in appearance_capabilities.values()
            overall_status = "partial" if shell_status in {"unsupported", "failed"} or self._native_info["status"] != "supported" or limited else "ok"
            if shell_status == "failed":
                overall_status = "failed"
            shell_capability = "applied" if shell_status == "applied" else shell_status
            return AdapterResult(
                self.target, overall_status, True, False,
                f"Terminal Profile updated; {self._resolution_message}; {shell_message}; native correction {self._native_info['status']}; rendering untested",
                overall_status == "partial", metadata=self._metadata(shell_capability, plan, "applied" if self._native_info["status"] == "supported" else None, stage="applied"),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Terminal apply failed: {error}")

    def verify(self, plan: Plan) -> AdapterResult:
        try:
            settings = self._read()
            resolved = resolve_default_profile(settings)
            if resolved is None:
                return AdapterResult(self.target, "failed", False, False, "Terminal default Profile could not be resolved")
            index, message = resolved
            expected = _palette_colors(plan)
            self._discover_native_correction()
            appearance_capabilities = self._appearance_capabilities()
            profile_scheme = dict(_SCHEME_MAPPING) if appearance_capabilities["profile.colorScheme"] == "supported" else _SCHEME_MAPPING[plan.mode]
            native_supported = self._native_info["status"] == "supported"
            native_verified = not native_supported or all(
                profile.get("adjustIndistinguishableColors") == "always" for profile in _profile_appearances(settings)
            )
            paired_schemes = {
                item.get("name"): item
                for item in settings.get("schemes", [])
                if isinstance(item, dict) and item.get("name") in {"One Tone Light", "One Tone Dark"}
            }
            paired_themes = {
                item.get("name"): item
                for item in settings.get("themes", [])
                if isinstance(item, dict) and item.get("name") in {"One Tone Light", "One Tone Dark"}
            }
            verified = (
                all(
                    isinstance(profile, dict)
                    and profile.get("colorScheme") == profile_scheme
                    and not any(key in profile for key in (*expected, "cursorColor"))
                    and "selectionForeground" not in profile
                    and (appearance_capabilities["profile.tabColor"] != "supported" or "tabColor" not in profile)
                    and (appearance_capabilities["profile.useAcrylic"] != "supported" or profile.get("useAcrylic") is False)
                    and (appearance_capabilities["profile.backgroundImage"] != "supported" or profile.get("backgroundImage") == "")
                    and (appearance_capabilities["profile.opacity"] != "supported" or profile.get("opacity") == 100)
                    and (appearance_capabilities["profile.opacity"] != "supported" or "acrylicOpacity" not in profile)
                    for profile in _profile_appearances(settings)
                )
                and native_verified
                and settings.get("profiles", {}).get("defaults", {}).get("colorScheme") == profile_scheme
                and settings.get("theme") == (dict(_SCHEME_MAPPING) if appearance_capabilities["theme"] == "supported" else "system")
                and all(paired_schemes.get(f"One Tone {mode.title()}") == _scheme_colors(plan, mode) for mode in ("light", "dark"))
                and all(
                    isinstance(paired_themes.get(f"One Tone {mode.title()}"), dict)
                    and all(
                        all(paired_themes[f"One Tone {mode.title()}"].get(section, {}).get(key) == value for key, value in values.items())
                        for section, values in _theme_colors(plan, mode, appearance_capabilities).items() if isinstance(values, dict)
                    ) for mode in ("light", "dark")
                )
            )
            shell_status, shell_verified, shell_message = self._verify_profile(plan)
            shell_capability = "verified" if shell_status == "verified" and shell_verified else shell_status
            overall_verified = verified and (shell_status in {"not-applicable", "unsupported", "failed"} or shell_verified)
            overall_status = "partial" if shell_status in {"unsupported", "failed"} or not native_supported or "unsupported" in appearance_capabilities.values() else "ok"
            if not overall_verified:
                overall_status = "failed"
            return AdapterResult(
                self.target, overall_status, False, overall_verified,
                f"Terminal configuration verified; {message}; {shell_message}; native correction {self._native_info['status']}; rendering untested" if overall_verified else "Terminal Profile colors do not match Plan; rendering untested",
                overall_status == "partial", metadata=self._metadata(shell_capability, plan, ("verified" if native_verified else "failed") if native_supported else None, stage="verified" if overall_verified else "failed"),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Terminal verify failed: {error}")

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        backup = backup_dir / "terminal-settings.json"
        if not backup.is_file():
            return AdapterResult(self.target, "failed", False, False, "Terminal backup not found")
        try:
            with backup.open("r", encoding="utf-8", newline="") as handle:
                atomic_write_text(self.settings_path, handle.read(), newline="")
            profile_state_path = backup_dir / "powershell-profile-state.json"
            if profile_state_path.is_file() and self._profile_path is not None:
                profile_state = json.loads(profile_state_path.read_text(encoding="utf-8"))
                profile_backup = backup_dir / "powershell-profile.ps1"
                if profile_state.get("exists") and profile_backup.is_file():
                    with profile_backup.open("r", encoding="utf-8", newline="") as handle:
                        original_profile = handle.read()
                    current_profile = self._read_profile() if self._profile_path.is_file() else ""
                    restored_profile = _restore_managed_profile_block(current_profile, original_profile)
                    if restored_profile != current_profile:
                        atomic_write_text(self._profile_path, restored_profile, newline="")
                elif not profile_state.get("exists") and self._profile_path.exists():
                    restored_profile = _restore_managed_profile_block(self._read_profile(), "")
                    if restored_profile.strip():
                        atomic_write_text(self._profile_path, restored_profile, newline="")
                    else:
                        self._profile_path.unlink()
            restored = self.settings_path.read_bytes() == backup.read_bytes()
            if profile_state_path.is_file() and self._profile_path is not None:
                profile_state = json.loads(profile_state_path.read_text(encoding="utf-8"))
                if profile_state.get("exists"):
                    with profile_backup.open("r", encoding="utf-8", newline="") as handle:
                        original_profile = handle.read()
                    restored = restored and self._profile_path.is_file() and _managed_profile_matches(self._read_profile(), original_profile)
                elif self._profile_path.is_file():
                    restored = restored and _PROFILE_START not in self._read_profile() and _PROFILE_END not in self._read_profile()
                else:
                    restored = restored and not self._profile_path.exists()
            return AdapterResult(self.target, "ok" if restored else "failed", True, restored, "Terminal settings restored")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Terminal rollback failed: {error}")
