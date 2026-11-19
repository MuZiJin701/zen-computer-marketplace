from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..inventory import inventory_groups, inventory_report
from ..palette import contrast_ratio, parse_hex_color
from ..plan import Plan
from ..storage import BYTES_MARKER, atomic_write_text, json_safe
from .base import AdapterResult

try:
    import winreg
except ImportError:  # pragma: no cover - the production target is Windows.
    winreg = None


PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
CURRENT_VERSION_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
DESKTOP_KEY = r"Control Panel\Desktop"
COLORS_KEY = r"Control Panel\Colors"
EXPLORER_ACCENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
DWM_KEY = r"Software\Microsoft\Windows\DWM"
THEME_VALUES = (
    "EnableTransparency",
    "AutoColorization",
    "AppsUseLightTheme",
    "SystemUsesLightTheme",
    "StartTaskbarColorPrevalence",
    "TitleBarColorPrevalence",
    "AccentColorMenu",
    "StartColorMenu",
    "AccentPalette",
    "AccentColor",
    "AccentColorInactive",
    "ColorizationColor",
    "ColorizationAfterglow",
    "Background",
)
REGISTRY_PATHS = {
    "EnableTransparency": PERSONALIZE_KEY,
    "AutoColorization": DESKTOP_KEY,
    "AppsUseLightTheme": PERSONALIZE_KEY,
    "SystemUsesLightTheme": PERSONALIZE_KEY,
    "StartTaskbarColorPrevalence": PERSONALIZE_KEY,
    "TitleBarColorPrevalence": DWM_KEY,
    "AccentColorMenu": EXPLORER_ACCENT_KEY,
    "StartColorMenu": EXPLORER_ACCENT_KEY,
    "AccentPalette": EXPLORER_ACCENT_KEY,
    "AccentColor": DWM_KEY,
    "AccentColorInactive": DWM_KEY,
    "ColorizationColor": DWM_KEY,
    "ColorizationAfterglow": DWM_KEY,
    "Background": COLORS_KEY,
}
REGISTRY_VALUE_NAMES = {
    "StartTaskbarColorPrevalence": "ColorPrevalence",
    "TitleBarColorPrevalence": "ColorPrevalence",
}


class RegistryBackend(Protocol):
    def get_value(self, name: str, default: Any = None) -> Any: ...

    def set_value(self, name: str, value: Any) -> None: ...

    def delete_value(self, name: str) -> None: ...

    def snapshot_values(self, names: tuple[str, ...]) -> dict[str, Any]: ...

    def restore_values(self, values: Mapping[str, Any]) -> None: ...


class DesktopBackend(Protocol):
    def get_high_contrast(self) -> bool | None: ...
    def get_wallpaper(self) -> str: ...

    def set_wallpaper(self, path: str) -> bool: ...

    def refresh_theme(self) -> None: ...


class InMemoryRegistryBackend:
    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        self.values = dict(values or {})

    def get_value(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def set_value(self, name: str, value: Any) -> None:
        self.values[name] = value

    def delete_value(self, name: str) -> None:
        self.values.pop(name, None)

    def snapshot_values(self, names: tuple[str, ...]) -> dict[str, Any]:
        return {name: self.values.get(name) for name in names}

    def restore_values(self, values: Mapping[str, Any]) -> None:
        for name, value in values.items():
            if value is None:
                self.values.pop(name, None)
            else:
                self.values[name] = value


class InMemoryDesktopBackend:
    def get_high_contrast(self) -> bool | None:
        return False

    def __init__(self, wallpaper: str = "", background_color: str | None = None, monitor_count: int = 1) -> None:
        self.wallpaper = wallpaper
        self.background_color = background_color
        self.monitor_wallpapers: list[str] | None = [wallpaper] * monitor_count if monitor_count > 1 else None

    def get_wallpaper(self) -> str:
        return self.wallpaper

    def get_wallpapers(self) -> list[str] | None:
        if self.monitor_wallpapers is not None:
            return list(self.monitor_wallpapers)
        return None

    def set_wallpaper(self, path: str) -> bool:
        self.wallpaper = path
        if self.monitor_wallpapers is not None:
            self.monitor_wallpapers = [path for _ in self.monitor_wallpapers]
        return True

    def get_background_color(self) -> str | None:
        return self.background_color

    def set_background_color(self, color: str) -> bool:
        self.background_color = color.upper()
        return True

    def refresh_theme(self) -> None:
        return None


class WindowsRegistryBackend:
    @staticmethod
    def _registry_value_name(name: str) -> str:
        return REGISTRY_VALUE_NAMES.get(name, name)

    def _key_for(self, name: str):
        if winreg is None:
            raise OSError("Windows registry is only available on Windows")
        path = CURRENT_VERSION_KEY if name in {"CurrentBuild", "ProductName"} else REGISTRY_PATHS.get(name, PERSONALIZE_KEY)
        return winreg.HKEY_LOCAL_MACHINE if path == CURRENT_VERSION_KEY else winreg.HKEY_CURRENT_USER, path

    def get_value(self, name: str, default: Any = None) -> Any:
        root, path = self._key_for(name)
        registry_name = self._registry_value_name(name)
        try:
            with winreg.OpenKey(root, path) as key:
                return winreg.QueryValueEx(key, registry_name)[0]
        except FileNotFoundError:
            return default

    def set_value(self, name: str, value: Any) -> None:
        if winreg is None:
            raise OSError("Windows registry is only available on Windows")
        root, path = self._key_for(name)
        registry_name = self._registry_value_name(name)
        with winreg.CreateKey(root, path) as key:
            if isinstance(value, (bytes, bytearray)):
                value_type, normalized = winreg.REG_BINARY, value
            elif isinstance(value, str):
                value_type, normalized = getattr(winreg, "REG_SZ", "REG_SZ"), value
            else:
                value_type, normalized = winreg.REG_DWORD, int(value)
            winreg.SetValueEx(key, registry_name, 0, value_type, normalized)

    def snapshot_values(self, names: tuple[str, ...]) -> dict[str, Any]:
        return {name: self.get_value(name) for name in names}

    def restore_values(self, values: Mapping[str, Any]) -> None:
        for name, value in values.items():
            if value is None:
                self.delete_value(name)
            else:
                self.set_value(name, value)

    def delete_value(self, name: str) -> None:
        if winreg is None:
            raise OSError("Windows registry is only available on Windows")
        root, path = self._key_for(name)
        registry_name = self._registry_value_name(name)
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, registry_name)
        except FileNotFoundError:
            return


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


_CLSID_DESKTOP_WALLPAPER = _GUID(
    0xC2CF3110,
    0x460E,
    0x4FC1,
    (ctypes.c_ubyte * 8)(0xB9, 0xD0, 0x8A, 0x1C, 0x0C, 0x9C, 0xC4, 0xBD),
)
_IID_IDESKTOP_WALLPAPER = _GUID(
    0xB92B56A9,
    0x8B55,
    0x4E14,
    (ctypes.c_ubyte * 8)(0x9A, 0x89, 0x01, 0x99, 0xBB, 0xB6, 0xF9, 0x3B),
)
_DWPOS_FILL = 4


def _hex_to_colorref(color: str) -> int:
    red, green, blue = parse_hex_color(color)
    return (blue << 16) | (green << 8) | red


def _colorref_to_hex(colorref: int) -> str:
    red = colorref & 0xFF
    green = (colorref >> 8) & 0xFF
    blue = (colorref >> 16) & 0xFF
    return f"#{red:02X}{green:02X}{blue:02X}"


def _rgb_string_to_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split()
    if len(parts) != 3:
        return None
    try:
        red, green, blue = (int(part) for part in parts)
    except ValueError:
        return None
    if not all(0 <= channel <= 255 for channel in (red, green, blue)):
        return None
    return f"#{red:02X}{green:02X}{blue:02X}"


def _normalize_wallpaper_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


class _DesktopWallpaperCOM:
    """Minimal stdlib ctypes wrapper for Windows IDesktopWallpaper."""

    def __init__(self) -> None:
        self._ole32 = None
        self._ptr = ctypes.c_void_p()
        self._vtable = None
        self._should_uninit = False

    def __enter__(self) -> _DesktopWallpaperCOM | None:
        if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "ole32"):
            return None
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        hr_init = ole32.CoInitializeEx(None, 0x2)
        if hr_init in (0, 1):
            self._should_uninit = True
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(_CLSID_DESKTOP_WALLPAPER),
            None,
            4,  # CLSCTX_LOCAL_SERVER
            ctypes.byref(_IID_IDESKTOP_WALLPAPER),
            ctypes.byref(ptr),
        )
        if hr < 0 or not ptr.value:
            if self._should_uninit:
                ole32.CoUninitialize()
                self._should_uninit = False
            return None
        self._ole32 = ole32
        self._ptr = ptr
        self._vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return self

    def __exit__(self, *args: Any) -> None:
        if self._vtable is not None and self._ptr.value:
            release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(self._vtable[2])
            release(self._ptr)
            self._ptr = ctypes.c_void_p()
            self._vtable = None
        if self._should_uninit and self._ole32 is not None:
            self._ole32.CoUninitialize()
            self._should_uninit = False

    def active_monitor_ids(self) -> list[str]:
        get_count = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT))(self._vtable[6])
        get_at = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(self._vtable[5])
        get_rect = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(_RECT))(self._vtable[7])
        count = wintypes.UINT()
        if get_count(self._ptr, ctypes.byref(count)) < 0:
            return []
        monitors: list[str] = []
        for index in range(count.value):
            mid_ptr = ctypes.c_void_p()
            if get_at(self._ptr, index, ctypes.byref(mid_ptr)) >= 0 and mid_ptr.value:
                mid = ctypes.wstring_at(mid_ptr.value)
                self._ole32.CoTaskMemFree(mid_ptr)
                rect = _RECT()
                if get_rect(self._ptr, mid, ctypes.byref(rect)) == 0:
                    monitors.append(mid)
        return monitors

    def get_wallpapers(self) -> list[str]:
        get_wp = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))(self._vtable[4])
        monitors = self.active_monitor_ids()
        targets: list[str | None] = monitors if monitors else [None]
        wallpapers: list[str] = []
        for monitor_id in targets:
            wp_ptr = ctypes.c_void_p()
            hr = get_wp(self._ptr, monitor_id, ctypes.byref(wp_ptr))
            if hr >= 0:
                value = ctypes.wstring_at(wp_ptr.value) if wp_ptr.value else ""
                if wp_ptr.value:
                    self._ole32.CoTaskMemFree(wp_ptr)
                wallpapers.append(value)
        return wallpapers

    def set_wallpaper(self, path: str) -> bool:
        set_wp = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR)(self._vtable[3])
        enable_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.BOOL)(self._vtable[18])
        set_pos = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int)(self._vtable[10])
        expected_norm = _normalize_wallpaper_path(path)
        if path:
            enable_fn(self._ptr, True)
            set_pos(self._ptr, _DWPOS_FILL)
            hr = set_wp(self._ptr, None, path)
            if hr < 0:
                return False
            monitors = self.active_monitor_ids()
            for monitor_id in monitors:
                set_wp(self._ptr, monitor_id, path)
        else:
            hr = set_wp(self._ptr, None, "")
            if hr < 0:
                enable_fn(self._ptr, False)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            current = self.get_wallpapers()
            if current and all(_normalize_wallpaper_path(item) == expected_norm for item in current):
                return True
            time.sleep(0.05)
        current = self.get_wallpapers()
        return bool(current) and all(_normalize_wallpaper_path(item) == expected_norm for item in current)

    def get_background_color(self) -> str | None:
        get_bg = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))(self._vtable[9])
        colorref = wintypes.DWORD()
        if get_bg(self._ptr, ctypes.byref(colorref)) >= 0:
            return _colorref_to_hex(colorref.value)
        return None

    def set_background_color(self, color: str) -> bool:
        set_bg = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD)(self._vtable[8])
        hr = set_bg(self._ptr, _hex_to_colorref(color))
        return hr >= 0


class WindowsDesktopBackend:
    def get_high_contrast(self) -> bool | None:
        if not hasattr(ctypes, "windll"):
            return None

        class HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD), ("lpszDefaultScheme", wintypes.LPWSTR)]

        state = HIGHCONTRASTW()
        state.cbSize = ctypes.sizeof(state)
        if not ctypes.windll.user32.SystemParametersInfoW(0x0042, state.cbSize, ctypes.byref(state), 0):
            return None
        return bool(state.dwFlags & 0x00000001)

    def get_wallpapers(self) -> list[str] | None:
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None:
                    return com.get_wallpapers()
        except OSError:
            return None
        return None

    def get_wallpaper(self) -> str:
        wallpapers = self.get_wallpapers()
        if wallpapers:
            return wallpapers[0]
        if winreg is None:
            raise OSError("Windows registry is only available on Windows")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
                return str(winreg.QueryValueEx(key, "Wallpaper")[0])
        except FileNotFoundError:
            return ""

    def set_wallpaper(self, path: str) -> bool:
        if not hasattr(ctypes, "windll"):
            raise OSError("System wallpaper API is only available on Windows")
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None and com.set_wallpaper(path):
                    return True
        except OSError:
            pass
        return bool(ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3))

    def get_background_color(self) -> str | None:
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None:
                    return com.get_background_color()
        except OSError:
            return None
        return None

    def set_background_color(self, color: str) -> bool:
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None:
                    return com.set_background_color(color)
        except OSError:
            return False
        return False

    def refresh_theme(self) -> None:
        if not hasattr(ctypes, "windll"):
            raise OSError("Windows theme API is only available on Windows")
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF,
            0x001A,
            0,
            "ImmersiveColorSet",
            0x0002,
            1000,
            ctypes.byref(result),
        )


def _json_safe_registry_value(value: Any) -> Any:
    return json_safe(value)


def _registry_value_from_json(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {BYTES_MARKER}:
        return base64.b64decode(value[BYTES_MARKER])
    return value


@dataclass(frozen=True)
class WindowsConfig:
    wallpaper_dir: Path
    min_windows_10_build: int = 19045
    min_windows_11_build: int = 22621


def detect_windows_version(registry: RegistryBackend) -> tuple[str, int] | None:
    raw_build = registry.get_value("CurrentBuild")
    try:
        build = int(str(raw_build))
    except (TypeError, ValueError):
        return None
    if build >= 22621:
        return "windows-11", build
    if 19045 <= build < 22000:
        return "windows-10", build
    return None


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def generate_wallpaper(palette: Mapping[str, str], path: Path, width: int = 1920, height: int = 1080) -> Path:
    if width < 1 or height < 1:
        raise ValueError("Wallpaper dimensions must be positive")
    surface = bytes(parse_hex_color(palette["surface"]))
    row = b"\x00" + surface * width
    rows = row * height
    raw = b"\x89PNG\r\n\x1a\n"
    raw += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw += _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    raw += _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def windows_color_value(color: str, alpha: int = 0xFF) -> int:
    red, green, blue = parse_hex_color(color)
    return (alpha << 24) | (blue << 16) | (green << 8) | red


def windows_colorization_value(color: str, alpha: int = 0xC4) -> int:
    red, green, blue = parse_hex_color(color)
    return (alpha << 24) | (red << 16) | (green << 8) | blue


def _blend_color(first: str, second: str, second_weight: float) -> str:
    first_rgb = parse_hex_color(first)
    second_rgb = parse_hex_color(second)
    return "#" + "".join(
        f"{round(left * (1 - second_weight) + right * second_weight):02X}"
        for left, right in zip(first_rgb, second_rgb)
    )


def _shell_accent(accent: str) -> str:
    # ponytail: AccentPalette slot semantics are not publicly stable; keep the
    # complete Shell ramp safe for its fixed white glyphs.
    for darkening in range(101):
        candidate = _blend_color(accent, "#000000", darkening / 100)
        if contrast_ratio(_blend_color(candidate, "#FFFFFF", 0.2), "#FFFFFF") >= 4.5:
            return candidate
    raise AssertionError("black must satisfy white foreground contrast")


def generate_accent_palette(accent: str) -> bytes:
    shell_accent = _shell_accent(accent)
    colors = [
        shell_accent,
        _blend_color(shell_accent, "#FFFFFF", 0.05),
        _blend_color(shell_accent, "#FFFFFF", 0.10),
        _blend_color(shell_accent, "#FFFFFF", 0.15),
        _blend_color(shell_accent, "#FFFFFF", 0.20),
        _blend_color(shell_accent, "#000000", 0.2),
        _blend_color(shell_accent, "#000000", 0.4),
        _blend_color(shell_accent, "#000000", 0.6),
    ]
    return b"".join(bytes((*reversed(parse_hex_color(color)), 0)) for color in colors)


def effective_windows_mode(
    plan_mode: str,
    shell_mode: str | None = None,
    app_mode: str | None = None,
) -> str:
    if shell_mode in {"light", "dark"}:
        return shell_mode
    if app_mode in {"light", "dark"}:
        return app_mode
    return plan_mode


def _theme_registry_values(plan: Plan, mode: str | None = None) -> dict[str, int | bytes | str]:
    palette = plan.palette_for(mode or plan.mode)
    shell_accent = _shell_accent(palette["accent"])
    inactive_accent = _shell_accent(palette["surface_subtle"])
    accent = windows_color_value(shell_accent)
    surface_rgb = " ".join(str(channel) for channel in parse_hex_color(palette["surface"]))
    values: dict[str, int | bytes | str] = {
        "EnableTransparency": 0,
        "TitleBarColorPrevalence": 1,
        "AccentColorMenu": accent,
        "StartColorMenu": accent,
        "AccentPalette": generate_accent_palette(palette["accent"]),
        "AccentColor": accent,
        "AccentColorInactive": windows_color_value(inactive_accent),
        "ColorizationColor": windows_colorization_value(shell_accent),
        "ColorizationAfterglow": windows_colorization_value(shell_accent),
        "Background": surface_rgb,
    }
    values["StartTaskbarColorPrevalence"] = 1
    return values


def _field_statuses(plan: Plan, status: str, shell_mode: str, mode: str | None = None) -> dict[str, str]:
    statuses = {name: status for name in _theme_registry_values(plan, mode=mode)}
    statuses["wallpaper"] = status
    if shell_mode != "dark":
        statuses["StartTaskbarColorPrevalence"] = "unsupported"
    statuses.update({
        "AppsUseLightTheme": "not-applicable",
        "SystemUsesLightTheme": "not-applicable",
        "AutoColorization": "not-applicable",
        "highContrast": "not-applicable",
    })
    return statuses


def _field_metadata(
    plan: Plan,
    status: str,
    shell_mode: str,
    generated_values: dict[str, Any] | None = None,
    effective_mode: str | None = None,
) -> dict[str, Any]:
    statuses = _field_statuses(plan, status, shell_mode, mode=effective_mode)
    metadata = {
        "field_capabilities": statuses,
        "field_inventory": inventory_report("windows", statuses, generated_values),
        "field_groups": inventory_groups("windows", statuses, generated_values),
        "shell_mode": shell_mode,
        "rendering_verification": "untested",
    }
    if effective_mode is not None:
        metadata["effective_mode"] = effective_mode
    return metadata


class WindowsAdapter:
    target = "windows"

    def __init__(
        self,
        config: WindowsConfig,
        registry: RegistryBackend | None = None,
        desktop: DesktopBackend | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or WindowsRegistryBackend()
        self.desktop = desktop or WindowsDesktopBackend()
        self._wallpaper_path: Path | None = None
        self._version: str | None = None
        self._instance: dict[str, Any] = {"status": "skipped"}

    def target_instance(self) -> dict[str, Any]:
        return dict(self._instance)

    def _auto_colorization_active(self) -> bool:
        return bool(self.registry.get_value("AutoColorization", 0))

    def _mode(self, name: str) -> str:
        value = self.registry.get_value(name)
        return "light" if value == 1 else "dark" if value == 0 else "unknown"

    def _effective_mode(self, plan: Plan) -> str:
        shell_mode = self._mode("SystemUsesLightTheme")
        app_mode = self._mode("AppsUseLightTheme")
        if shell_mode == "unknown" and app_mode == "unknown":
            instance = plan.target_instances.get("windows", {})
            shell_mode = str(instance.get("shell_mode", "unknown"))
            app_mode = str(instance.get("app_mode", "unknown"))
        return effective_windows_mode(plan.mode, shell_mode, app_mode)

    def _wallpaper_matches(self, expected_path: str, expected_background_color: str | None = None) -> bool:
        expected_norm = _normalize_wallpaper_path(expected_path)
        get_wallpapers = getattr(self.desktop, "get_wallpapers", None)
        wallpapers = get_wallpapers() if callable(get_wallpapers) else None
        if wallpapers is not None:
            if not wallpapers:
                return False
            if not all(_normalize_wallpaper_path(item) == expected_norm for item in wallpapers):
                return False
        elif _normalize_wallpaper_path(self.desktop.get_wallpaper()) != expected_norm:
            return False
        if expected_background_color is not None:
            get_bg = getattr(self.desktop, "get_background_color", None)
            actual_bg = get_bg() if callable(get_bg) else None
            if actual_bg is not None and actual_bg.upper() != expected_background_color.upper():
                return False
        return True

    def detect(self) -> AdapterResult:
        detected = detect_windows_version(self.registry)
        if detected is None:
            return AdapterResult(self.target, "skipped", False, False, "Windows 10 22H2+ or Windows 11 22H2+ not detected")
        family, build = detected
        self._version = f"{family} build {build}"
        high_contrast = self.desktop.get_high_contrast()
        app_mode = self._mode("AppsUseLightTheme")
        shell_mode = self._mode("SystemUsesLightTheme")
        metadata = {
            "system_mode": app_mode,
            "app_mode": app_mode,
            "shell_mode": shell_mode,
            "effective_mode": effective_windows_mode("dark", shell_mode, app_mode),
            "selected_mode_is_independent": True,
            "automatic_accent_enabled": self._auto_colorization_active(),
            "high_contrast": high_contrast,
            "high_contrast_evidence": "SystemParametersInfoW(SPI_GETHIGHCONTRAST)",
        }
        self._instance = {"status": "ok" if high_contrast is False else "skipped", **metadata, "windows_build": build}
        if high_contrast is not False:
            return AdapterResult(self.target, "skipped", False, False,
                                 "High contrast is active or could not be determined; system appearance preserved", metadata=metadata)
        if self._auto_colorization_active():
            return AdapterResult(
                self.target,
                "partial",
                False,
                True,
                "detected " + self._version + "; Windows automatic accent color is enabled and may overwrite the selected accent",
                True,
                version=self._version,
                metadata=metadata,
            )
        return AdapterResult(self.target, "ok", False, True, f"detected {self._version}", version=self._version, metadata=metadata)

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            old_path = self.desktop.get_wallpaper()
            registry_values = self.registry.snapshot_values(THEME_VALUES)
            get_bg = getattr(self.desktop, "get_background_color", None)
            background_color = get_bg() if callable(get_bg) else None
            if background_color is None:
                background_color = _rgb_string_to_hex(registry_values.get("Background"))
            metadata = {
                "registry": {name: _json_safe_registry_value(value) for name, value in registry_values.items()},
                "wallpaper": old_path,
                "background_color": background_color,
            }
            atomic_write_text(backup_dir / "windows.json", json.dumps(metadata, sort_keys=True))
            if old_path and Path(old_path).is_file():
                import shutil

                shutil.copy2(old_path, backup_dir / "original-wallpaper")
            return AdapterResult(self.target, "ok", False, True, "Windows theme and wallpaper snapshot saved", version=self._version)
        except (OSError, TypeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Windows snapshot failed: {error}")

    def apply(self, plan: Plan) -> AdapterResult:
        try:
            if self.desktop.get_high_contrast() is not False:
                return AdapterResult(self.target, "skipped", False, False, "High contrast is active or unknown; configuration preserved")
            effective_mode = self._effective_mode(plan)
            palette = plan.palette_for(effective_mode)
            self.config.wallpaper_dir.mkdir(parents=True, exist_ok=True)
            wallpaper_path = (self.config.wallpaper_dir / f"{plan.id}.png").resolve()
            self._wallpaper_path = generate_wallpaper(palette, wallpaper_path)
            if not self.desktop.set_wallpaper(str(self._wallpaper_path)):
                return AdapterResult(self.target, "failed", True, False, "Windows wallpaper API rejected the generated wallpaper")
            set_bg = getattr(self.desktop, "set_background_color", None)
            if callable(set_bg):
                set_bg(palette["surface"])
            registry_values = _theme_registry_values(plan, mode=effective_mode)
            for name, value in registry_values.items():
                self.registry.set_value(name, value)
            self.desktop.refresh_theme()
            auto_colorization = self._auto_colorization_active()
            metadata = _field_metadata(
                plan,
                "applied",
                self._mode("SystemUsesLightTheme"),
                {**registry_values, "wallpaper": str(self._wallpaper_path)},
                effective_mode=effective_mode,
            )
            if auto_colorization or self._mode("SystemUsesLightTheme") != "dark":
                message = "theme colors and generated wallpaper applied"
                if self._mode("SystemUsesLightTheme") != "dark":
                    message += "; actual Shell mode limits taskbar accent display; rendering untested"
                if auto_colorization:
                    message += "; turn off Windows automatic accent color to keep the selected accent"
                return AdapterResult(
                    self.target,
                    "partial",
                    True,
                    False,
                    message,
                    auto_colorization,
                    version=self._version,
                    metadata=metadata,
                )
            return AdapterResult(
                self.target, "ok", True, False, "theme colors and generated wallpaper applied", version=self._version,
                metadata=metadata,
            )
        except (OSError, KeyError, ValueError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Windows apply failed: {error}")

    def verify(self, plan: Plan) -> AdapterResult:
        if self.desktop.get_high_contrast() is not False:
            return AdapterResult(self.target, "skipped", False, False, "High contrast is active or unknown; configuration rendering cannot be accepted")
        effective_mode = self._effective_mode(plan)
        palette = plan.palette_for(effective_mode)
        expected_path = self._wallpaper_path or (self.config.wallpaper_dir / f"{plan.id}.png").resolve()
        expected_registry = _theme_registry_values(plan, mode=effective_mode)
        colors_ok = all(self.registry.get_value(name) == value for name, value in expected_registry.items())
        wallpaper_ok = (
            expected_path is not None
            and Path(expected_path).is_file()
            and self._wallpaper_matches(str(expected_path), expected_background_color=palette["surface"])
        )
        verified = colors_ok and wallpaper_ok
        auto_colorization = self._auto_colorization_active()
        metadata = _field_metadata(
            plan,
            "verified" if verified else "failed",
            self._mode("SystemUsesLightTheme"),
            {**expected_registry, "wallpaper": str(expected_path)},
            effective_mode=effective_mode,
        )
        if verified and (auto_colorization or self._mode("SystemUsesLightTheme") != "dark"):
            message = "Windows theme and wallpaper verified"
            if self._mode("SystemUsesLightTheme") != "dark":
                message += "; actual Shell mode limits taskbar accent display; rendering untested"
            if auto_colorization:
                message += "; automatic accent color is still enabled and may overwrite the accent later"
            return AdapterResult(
                self.target,
                "partial",
                False,
                True,
                message,
                auto_colorization,
                version=self._version,
                metadata=metadata,
            )
        return AdapterResult(
            self.target, "ok" if verified else "failed", False, verified,
            "Windows theme and wallpaper verified" if verified else "Windows theme or wallpaper mismatch", version=self._version,
            metadata=metadata,
        )

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        try:
            metadata = json.loads((backup_dir / "windows.json").read_text(encoding="utf-8"))
            registry_values = {name: _registry_value_from_json(value) for name, value in metadata["registry"].items()}
            auto_colorization = registry_values.pop("AutoColorization", None)
            if auto_colorization:
                self.registry.set_value("AutoColorization", 0)
            self.registry.restore_values(registry_values)
            old_path = str(metadata.get("wallpaper", ""))
            old_bg_color = metadata.get("background_color") or _rgb_string_to_hex(registry_values.get("Background"))
            original_backup = backup_dir / "original-wallpaper"
            if old_path and original_backup.is_file():
                import shutil

                shutil.copy2(original_backup, old_path)
            try:
                if not self.desktop.set_wallpaper(old_path):
                    return AdapterResult(self.target, "failed", True, False, "Windows wallpaper restore was rejected")
                if isinstance(old_bg_color, str):
                    set_bg = getattr(self.desktop, "set_background_color", None)
                    if callable(set_bg):
                        set_bg(old_bg_color)
                self.registry.restore_values(registry_values)
            finally:
                if auto_colorization is None:
                    self.registry.delete_value("AutoColorization")
                else:
                    self.registry.set_value("AutoColorization", auto_colorization)
            restored = all(
                self.registry.get_value(name) == registry_values.get(name)
                for name in registry_values
                if name != "AutoColorization"
            )
            restored = restored and self.registry.get_value("AutoColorization") == auto_colorization
            restored = restored and self._wallpaper_matches(old_path, expected_background_color=old_bg_color if isinstance(old_bg_color, str) else None)
            return AdapterResult(self.target, "ok" if restored else "failed", True, restored, "Windows theme and wallpaper restored" if restored else "Windows restore verification failed", version=self._version)
        except (OSError, KeyError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Windows rollback failed: {error}")
