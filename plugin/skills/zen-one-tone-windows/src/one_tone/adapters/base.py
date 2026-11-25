from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol

from ..plan import Plan
from ..inventory import field_inventory_for

AdapterStatus = Literal["ok", "partial", "failed", "skipped"]
_ERROR_NO_MORE_FILES = 18


def verify_unredirected_path(frozen_path: Path, label: str, *, require_file: bool = False) -> tuple[bool, Path | None, str]:
    """Ensure a frozen absolute path exists and is not redirected via symlink or junction."""
    if not frozen_path.is_absolute():
        return False, None, f"{label} path must be absolute: {frozen_path}"
    expected_norm = os.path.normcase(os.path.normpath(str(frozen_path)))
    if frozen_path.is_symlink():
        return False, None, f"{label} path was redirected by a symlink: {frozen_path}"
    try:
        resolved = frozen_path.resolve(strict=True)
    except OSError as error:
        return False, None, f"{label} path unavailable: {error}"
    if os.path.normcase(os.path.normpath(str(resolved))) != expected_norm:
        return False, None, f"{label} path redirected from frozen path {frozen_path} to {resolved}"
    if require_file and not resolved.is_file():
        return False, None, f"{label} path is not a regular file: {frozen_path}"
    return True, resolved, "ok"


def create_kernel32() -> Any:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def probe_windows_process(
    exe_name: str,
    *,
    kernel32_factory: Callable[[], Any] | None = None,
) -> tuple[str, str]:
    """Probe whether an executable is running via Win32 snapshot (fail-closed -> 'unknown')."""
    try:
        from ctypes import wintypes

        kernel32 = (kernel32_factory or create_kernel32)()
        th32cs_snapprocess = 0x00000002
        invalid_handle = wintypes.HANDLE(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        ctypes.set_last_error(0)
        snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
        if not snapshot or snapshot == invalid_handle:
            return "unknown", f"CreateToolhelp32Snapshot failed (Win32 error {ctypes.get_last_error()})"
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ctypes.set_last_error(0)
            has_entry = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
            if not has_entry:
                error_code = ctypes.get_last_error()
                if error_code == _ERROR_NO_MORE_FILES:
                    return "stopped", "no matching process"
                return "unknown", f"Process32FirstW failed (Win32 error {error_code})"
            target_folded = exe_name.casefold()
            while has_entry:
                if entry.szExeFile.casefold() == target_folded:
                    return "running", f"{exe_name} process is running"
                ctypes.set_last_error(0)
                has_entry = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
            error_code = ctypes.get_last_error()
            if error_code != _ERROR_NO_MORE_FILES:
                return "unknown", f"Process32NextW failed (Win32 error {error_code})"
            return "stopped", f"{exe_name} is not running"
        finally:
            kernel32.CloseHandle(snapshot)
    except (AttributeError, OSError, ValueError) as error:
        return "unknown", f"Windows process enumeration failed: {error}"


def close_windows_process(
    exe_name: str,
    *,
    graceful_timeout: float = 3.0,
    force_timeout: float = 3.0,
    poll_interval: float = 0.2,
    process_probe: Callable[[], tuple[str, str]] | None = None,
    command_runner: Callable[..., Any] | None = None,
) -> tuple[bool, str]:
    """Close a running Windows process (graceful first, then forceful), never killing on 'unknown'."""
    if process_probe is None and sys.platform != "win32":
        return True, "non-windows host"
    probe = process_probe or (lambda: probe_windows_process(exe_name))
    runner = command_runner or subprocess.run

    def _safe_probe() -> tuple[str, str]:
        try:
            return probe()
        except Exception as error:
            return "unknown", f"process probe failed: {error}"

    status, detail = _safe_probe()
    if status == "stopped":
        return True, f"{exe_name} is not running"
    if status != "running":
        return False, detail or f"Unable to verify {exe_name} process state"

    def _poll_until_stopped(timeout: float) -> tuple[str, str]:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            cur_status, cur_detail = _safe_probe()
            if cur_status != "running":
                return cur_status, cur_detail
            if time.monotonic() >= deadline:
                return cur_status, cur_detail
            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

    try:
        runner(["taskkill", "/IM", exe_name, "/T"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"Graceful taskkill failed for {exe_name}: {error}"
    status, detail = _poll_until_stopped(graceful_timeout)
    if status == "stopped":
        return True, f"{exe_name} closed gracefully"
    if status != "running":
        return False, detail or f"Unable to verify {exe_name} after graceful close"

    try:
        runner(["taskkill", "/F", "/IM", exe_name, "/T"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"Force taskkill failed for {exe_name}: {error}"
    status, detail = _poll_until_stopped(force_timeout)
    if status == "stopped":
        return True, f"{exe_name} terminated forcefully"
    return False, detail or f"Failed to terminate {exe_name}"


@dataclass(frozen=True)
class AdapterResult:
    target: str
    status: AdapterStatus
    changed: bool
    verified: bool
    message: str
    requires_user_action: bool = False
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ok", "partial", "failed", "skipped"}:
            raise ValueError(f"Invalid adapter status: {self.status}")


class ThemeAdapter(Protocol):
    target: str

    def detect(self) -> AdapterResult: ...

    def snapshot(self, backup_dir: Path) -> AdapterResult: ...

    def apply(self, plan: Plan) -> AdapterResult: ...

    def verify(self, plan: Plan) -> AdapterResult: ...

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult: ...


class UnsupportedAdapter:
    def __init__(self, target: str) -> None:
        self.target = target

    def _skipped(self, operation: str) -> AdapterResult:
        return AdapterResult(self.target, "skipped", False, False, f"{operation}: target not verified")

    def detect(self) -> AdapterResult:
        return self._skipped("detect")

    def snapshot(self, backup_dir: Path) -> AdapterResult:
        return self._skipped("snapshot")

    def apply(self, plan: Plan) -> AdapterResult:
        return self._skipped("apply")

    def verify(self, plan: Plan) -> AdapterResult:
        return self._skipped("verify")

    def rollback(self, backup_dir: Path, metadata: Mapping[str, Any] | None = None) -> AdapterResult:
        return self._skipped("rollback")


def field_capabilities(
    target: str,
    unsupported: set[str] | None = None,
    statuses: Mapping[str, str] | None = None,
) -> dict[str, str]:
    unsupported = unsupported or set()
    statuses = statuses or {}
    return {
        entry["technical_field"]: statuses.get(entry["technical_field"], "unsupported" if entry["technical_field"] in unsupported else entry["capability_status"])
        for entry in field_inventory_for(target)
    }
