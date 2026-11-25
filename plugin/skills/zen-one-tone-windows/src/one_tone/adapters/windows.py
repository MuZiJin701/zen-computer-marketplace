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
from ..palette import (
    _oklch_color,
    _oklch_components,
    contrast_ratio,
    mode_independent_inactive_titlebar,
    mode_independent_surface,
    parse_hex_color,
)
from ..plan import Plan
from ..storage import BYTES_MARKER, atomic_write_bytes, atomic_write_text, json_safe
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
        self.refresh_count = 0

    def get_wallpaper(self) -> str:
        if self.monitor_wallpapers:
            return self.monitor_wallpapers[0]
        return self.wallpaper

    def get_wallpapers(self) -> list[str] | None:
        if self.monitor_wallpapers is not None:
            return list(self.monitor_wallpapers)
        return None

    def get_monitor_wallpapers(self) -> dict[str, str] | None:
        if self.monitor_wallpapers is not None:
            return {f"monitor-{idx}": path for idx, path in enumerate(self.monitor_wallpapers)}
        return None

    def set_wallpaper(self, path: str) -> bool:
        self.wallpaper = path
        if self.monitor_wallpapers is not None:
            self.monitor_wallpapers = [path for _ in self.monitor_wallpapers]
        return True

    def set_monitor_wallpapers(self, mapping: Mapping[str, str]) -> bool:
        if self.monitor_wallpapers is None:
            first = next(iter(mapping.values()), "")
            self.wallpaper = first
            return True
        updated = list(self.monitor_wallpapers)
        for idx in range(len(updated)):
            key = f"monitor-{idx}"
            if key in mapping:
                updated[idx] = mapping[key]
        self.monitor_wallpapers = updated
        if updated:
            self.wallpaper = updated[0]
        return True

    def get_background_color(self) -> str | None:
        return self.background_color

    def set_background_color(self, color: str) -> bool:
        self.background_color = color.upper()
        return True

    def refresh_theme(self) -> None:
        self.refresh_count += 1
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

    def get_monitor_wallpapers(self) -> dict[str, str]:
        get_wp = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))(self._vtable[4])
        monitors = self.active_monitor_ids()
        result: dict[str, str] = {}
        for monitor_id in monitors:
            wp_ptr = ctypes.c_void_p()
            hr = get_wp(self._ptr, monitor_id, ctypes.byref(wp_ptr))
            if hr >= 0:
                value = ctypes.wstring_at(wp_ptr.value) if wp_ptr.value else ""
                if wp_ptr.value:
                    self._ole32.CoTaskMemFree(wp_ptr)
                result[monitor_id] = value
        return result

    def set_monitor_wallpapers(self, mapping: Mapping[str, str]) -> bool:
        set_wp = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR)(self._vtable[3])
        enable_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.BOOL)(self._vtable[18])
        if not mapping:
            return self.set_wallpaper("")
        if all(not path for path in mapping.values()):
            return self.set_wallpaper("")
        enable_fn(self._ptr, True)
        active = set(self.active_monitor_ids())
        targets = {mid: path for mid, path in mapping.items() if not active or mid in active}
        if not targets:
            return self.set_wallpaper(next(iter(mapping.values()), ""))
        for monitor_id, path in targets.items():
            if set_wp(self._ptr, monitor_id, path) < 0:
                return False
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            current = self.get_monitor_wallpapers()
            if all(_normalize_wallpaper_path(current.get(mid, "")) == _normalize_wallpaper_path(path) for mid, path in targets.items()):
                return True
            time.sleep(0.05)
        current = self.get_monitor_wallpapers()
        return all(_normalize_wallpaper_path(current.get(mid, "")) == _normalize_wallpaper_path(path) for mid, path in targets.items())

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

    def get_monitor_wallpapers(self) -> dict[str, str] | None:
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None:
                    mapping = com.get_monitor_wallpapers()
                    return mapping or None
        except OSError:
            return None
        return None

    def set_monitor_wallpapers(self, mapping: Mapping[str, str]) -> bool:
        try:
            with _DesktopWallpaperCOM() as com:
                if com is not None and com.set_monitor_wallpapers(mapping):
                    return True
        except OSError:
            pass
        first = next(iter(mapping.values()), "")
        return self.set_wallpaper(first)

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


def generate_wallpaper(surface: str | Mapping[str, str], path: Path, width: int = 64, height: int = 64) -> Path:
    if width < 1 or height < 1:
        raise ValueError("Wallpaper dimensions must be positive")
    surface_hex = surface if isinstance(surface, str) else surface["surface"]
    surface_rgb = bytes(parse_hex_color(surface_hex))
    row = b"\x00" + surface_rgb * width
    rows = row * height
    raw = b"\x89PNG\r\n\x1a\n"
    raw += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw += _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    raw += _png_chunk(b"IEND", b"")
    atomic_write_bytes(path, raw)
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


def _shell_accent(accent: str, minimum_ratio: float = 3.0) -> str:
    # Keep the Windows Shell accent vibrant in OKLCH while protecting fixed white
    # glyphs on Start, Taskbar, Titlebar, and Quick Settings.
    if contrast_ratio(accent, "#FFFFFF") >= minimum_ratio:
        return accent
    lightness, chroma, hue = _oklch_components(accent)
    start = min(90, max(10, round(lightness * 100)))
    for step in range(start, 4, -1):
        candidate = _oklch_color(hue, step / 100, chroma)
        if contrast_ratio(candidate, "#FFFFFF") >= minimum_ratio:
            return candidate
    raise AssertionError("dark OKLCH candidate must satisfy white glyph contrast")


def generate_accent_palette(accent: str) -> bytes:
    """Build Windows 10/11 8-slot AccentPalette in genuine RGB0 order (Light3..Base..Dark3, Extra)."""
    shell_accent = _shell_accent(accent, 3.0)
    base_l, base_c, hue = _oklch_components(shell_accent)
    dark1 = _shell_accent(_oklch_color(hue, max(0.20, base_l - 0.08), base_c * 0.95), 4.5)
    dark1_l = _oklch_components(dark1)[0]
    colors = [
        _oklch_color(hue, min(0.95, base_l + 0.28), base_c * 0.65),  # Slot 0: Light3
        _oklch_color(hue, min(0.92, base_l + 0.20), base_c * 0.85),  # Slot 1: Light2
        _oklch_color(hue, min(0.88, base_l + 0.11), base_c),         # Slot 2: Light1
        shell_accent,                                                 # Slot 3: Base accent
        dark1,                                                        # Slot 4: Dark1 (>= 4.5:1 on white)
        _oklch_color(hue, max(0.15, dark1_l - 0.08), base_c * 0.85), # Slot 5: Dark2
        _oklch_color(hue, max(0.10, dark1_l - 0.16), base_c * 0.72), # Slot 6: Dark3
        _oklch_color((hue + 0.08) % 1.0, max(0.25, dark1_l), base_c * 0.80),  # Slot 7: Extra
    ]
    return b"".join(bytes((*parse_hex_color(color), 0)) for color in colors)


def _theme_registry_values(plan: Plan) -> dict[str, int | bytes | str]:
    shell_accent = _shell_accent(plan.seed_color)
    accent = windows_color_value(shell_accent)
    backdrop = mode_independent_surface(plan.seed_color)
    inactive_titlebar = mode_independent_inactive_titlebar(plan.seed_color, shell_accent=shell_accent)
    surface_rgb = " ".join(str(channel) for channel in parse_hex_color(backdrop))
    values: dict[str, int | bytes | str] = {
        "EnableTransparency": 0,
        "SystemUsesLightTheme": 0,
        "StartTaskbarColorPrevalence": 1,
        "TitleBarColorPrevalence": 1,
        "AccentColorMenu": accent,
        "StartColorMenu": accent,
        "AccentPalette": generate_accent_palette(plan.seed_color),
        "AccentColor": accent,
        "AccentColorInactive": windows_color_value(inactive_titlebar),
        "ColorizationColor": windows_colorization_value(shell_accent),
        "ColorizationAfterglow": windows_colorization_value(shell_accent),
        "Background": surface_rgb,
    }
    return values


def _field_statuses(plan: Plan, status: str, shell_mode: str = "dark") -> dict[str, str]:
    statuses = {name: status for name in _theme_registry_values(plan)}
    statuses["wallpaper"] = status
    statuses.update({
        "AppsUseLightTheme": "not-applicable",
        "AutoColorization": "not-applicable",
        "highContrast": "not-applicable",
    })
    return statuses


def _field_metadata(
    plan: Plan,
    status: str,
    shell_mode: str,
    generated_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    statuses = _field_statuses(plan, status, shell_mode)
    return {
        "field_capabilities": statuses,
        "field_inventory": inventory_report("windows", statuses, generated_values),
        "field_groups": inventory_groups("windows", statuses, generated_values),
        "shell_mode": shell_mode,
        "rendering_verification": "untested",
    }


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

    def _wallpaper_matches(
        self,
        expected_path: str,
        expected_background_color: str | None = None,
        expected_monitor_wallpapers: Mapping[str, str] | None = None,
    ) -> bool:
        if expected_monitor_wallpapers:
            get_mon = getattr(self.desktop, "get_monitor_wallpapers", None)
            actual_mon = get_mon() if callable(get_mon) else None
            if actual_mon is not None:
                if not all(
                    _normalize_wallpaper_path(actual_mon.get(mid, "")) == _normalize_wallpaper_path(path)
                    for mid, path in expected_monitor_wallpapers.items()
                    if mid in actual_mon
                ):
                    return False
            else:
                expected_norm = _normalize_wallpaper_path(expected_path)
                if _normalize_wallpaper_path(self.desktop.get_wallpaper()) != expected_norm:
                    return False
        else:
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
            import shutil

            backup_dir.mkdir(parents=True, exist_ok=True)
            old_path = self.desktop.get_wallpaper()
            get_mon = getattr(self.desktop, "get_monitor_wallpapers", None)
            monitor_wallpapers = get_mon() if callable(get_mon) else None
            registry_values = self.registry.snapshot_values(THEME_VALUES)
            get_bg = getattr(self.desktop, "get_background_color", None)
            background_color = get_bg() if callable(get_bg) else None
            if background_color is None:
                background_color = _rgb_string_to_hex(registry_values.get("Background"))
            wallpaper_backups: dict[str, str] = {}
            if old_path and Path(old_path).is_file():
                shutil.copy2(old_path, backup_dir / "original-wallpaper")
                wallpaper_backups[old_path] = "original-wallpaper"
            if isinstance(monitor_wallpapers, dict):
                for idx, path in enumerate(monitor_wallpapers.values()):
                    if path and path not in wallpaper_backups and Path(path).is_file():
                        backup_name = f"original-wallpaper-{idx}"
                        shutil.copy2(path, backup_dir / backup_name)
                        wallpaper_backups[path] = backup_name
            metadata: dict[str, Any] = {
                "registry": {name: _json_safe_registry_value(value) for name, value in registry_values.items()},
                "wallpaper": old_path,
                "background_color": background_color,
            }
            if isinstance(monitor_wallpapers, dict) and monitor_wallpapers:
                metadata["monitor_wallpapers"] = dict(monitor_wallpapers)
                metadata["wallpaper_backups"] = wallpaper_backups
            atomic_write_text(backup_dir / "windows.json", json.dumps(metadata, sort_keys=True))
            return AdapterResult(self.target, "ok", False, True, "Windows theme and wallpaper snapshot saved", version=self._version)
        except (OSError, TypeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Windows snapshot failed: {error}")

    def apply(self, plan: Plan) -> AdapterResult:
        changed = False
        try:
            if self.desktop.get_high_contrast() is not False:
                return AdapterResult(self.target, "skipped", False, False, "High contrast is active or unknown; configuration preserved")
            backdrop = mode_independent_surface(plan.seed_color)
            self.config.wallpaper_dir.mkdir(parents=True, exist_ok=True)
            wallpaper_path = (self.config.wallpaper_dir / f"{plan.id}.png").resolve()
            self._wallpaper_path = generate_wallpaper(backdrop, wallpaper_path)
            if not self.desktop.set_wallpaper(str(self._wallpaper_path)):
                return AdapterResult(self.target, "failed", True, False, "Windows wallpaper API rejected the generated wallpaper")
            changed = True
            set_bg = getattr(self.desktop, "set_background_color", None)
            if callable(set_bg):
                set_bg(backdrop)
            registry_values = _theme_registry_values(plan)
            for name, value in registry_values.items():
                self.registry.set_value(name, value)
            self.desktop.refresh_theme()
            auto_colorization = self._auto_colorization_active()
            metadata = _field_metadata(
                plan,
                "applied",
                self._mode("SystemUsesLightTheme"),
                {**registry_values, "wallpaper": str(self._wallpaper_path)},
            )
            if auto_colorization:
                return AdapterResult(
                    self.target,
                    "partial",
                    True,
                    False,
                    "theme colors and generated wallpaper applied; turn off Windows automatic accent color to keep the selected accent",
                    True,
                    version=self._version,
                    metadata=metadata,
                )
            return AdapterResult(
                self.target, "ok", True, False, "theme colors and generated wallpaper applied", version=self._version,
                metadata=metadata,
            )
        except (OSError, KeyError, ValueError) as error:
            return AdapterResult(self.target, "failed", changed, False, f"Windows apply failed: {error}")

    def verify(self, plan: Plan) -> AdapterResult:
        if self.desktop.get_high_contrast() is not False:
            return AdapterResult(self.target, "skipped", False, False, "High contrast is active or unknown; configuration rendering cannot be accepted")
        backdrop = mode_independent_surface(plan.seed_color)
        expected_path = self._wallpaper_path or (self.config.wallpaper_dir / f"{plan.id}.png").resolve()
        expected_registry = _theme_registry_values(plan)
        colors_ok = all(self.registry.get_value(name) == value for name, value in expected_registry.items())
        wallpaper_ok = (
            expected_path is not None
            and Path(expected_path).is_file()
            and self._wallpaper_matches(str(expected_path), expected_background_color=backdrop)
        )
        verified = colors_ok and wallpaper_ok
        auto_colorization = self._auto_colorization_active()
        metadata = _field_metadata(
            plan,
            "verified" if verified else "failed",
            self._mode("SystemUsesLightTheme"),
            {**expected_registry, "wallpaper": str(expected_path)},
        )
        if verified and auto_colorization:
            return AdapterResult(
                self.target,
                "partial",
                False,
                True,
                "Windows theme and wallpaper verified; automatic accent color is still enabled and may overwrite the accent later",
                True,
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
            import shutil

            metadata = json.loads((backup_dir / "windows.json").read_text(encoding="utf-8"))
            registry_values = {name: _registry_value_from_json(value) for name, value in metadata["registry"].items()}
            auto_colorization = registry_values.pop("AutoColorization", None)
            if auto_colorization:
                self.registry.set_value("AutoColorization", 0)
            self.registry.restore_values(registry_values)
            old_path = str(metadata.get("wallpaper", ""))
            old_bg_color = metadata.get("background_color") or _rgb_string_to_hex(registry_values.get("Background"))
            monitor_wallpapers = metadata.get("monitor_wallpapers")
            wallpaper_backups = metadata.get("wallpaper_backups") or {}
            original_backup = backup_dir / "original-wallpaper"
            if old_path and original_backup.is_file() and not Path(old_path).is_file():
                atomic_write_bytes(Path(old_path), original_backup.read_bytes())
            if isinstance(wallpaper_backups, dict):
                for dest_path, backup_name in wallpaper_backups.items():
                    backup_file = backup_dir / str(backup_name)
                    if dest_path and backup_file.is_file() and not Path(dest_path).is_file():
                        atomic_write_bytes(Path(dest_path), backup_file.read_bytes())
            try:
                if isinstance(monitor_wallpapers, dict) and monitor_wallpapers and callable(getattr(self.desktop, "set_monitor_wallpapers", None)):
                    if not self.desktop.set_monitor_wallpapers(monitor_wallpapers):
                        return AdapterResult(self.target, "failed", True, False, "Windows wallpaper restore was rejected")
                elif not self.desktop.set_wallpaper(old_path):
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
            self.desktop.refresh_theme()
            restored = all(
                self.registry.get_value(name) == registry_values.get(name)
                for name in registry_values
                if name != "AutoColorization"
            )
            restored = restored and self.registry.get_value("AutoColorization") == auto_colorization
            restored = restored and self._wallpaper_matches(
                old_path,
                expected_background_color=old_bg_color if isinstance(old_bg_color, str) else None,
                expected_monitor_wallpapers=monitor_wallpapers if isinstance(monitor_wallpapers, dict) else None,
            )
            return AdapterResult(self.target, "ok" if restored else "failed", True, restored, "Windows theme and wallpaper restored" if restored else "Windows restore verification failed", version=self._version)
        except (OSError, KeyError, json.JSONDecodeError) as error:
            return AdapterResult(self.target, "failed", False, False, f"Windows rollback failed: {error}")
