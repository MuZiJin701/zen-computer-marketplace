from __future__ import annotations

import ctypes
import json
import subprocess
from pathlib import Path

import pytest

from one_tone.adapters.base import close_windows_process
from one_tone.adapters.chrome import (
    CHROME_COLOR_SCHEME_SYSTEM,
    CHROME_COLOR_VARIANT_TONAL_SPOT,
    CHROME_PREFERENCES_SCHEMA_V1,
    CHROME_USER_COLOR_THEME_ID,
    ChromeAdapter,
    discover_chrome_instance,
    probe_chrome_process,
    seed_color_to_skcolor_int,
)
from one_tone.plan import create_plan
from one_tone.transaction import TransactionStatus, TransactionStore, apply_plan


def _write_preferences(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _stopped_probe() -> tuple[str, str]:
    return ("stopped", "test")


def _running_probe() -> tuple[str, str]:
    return ("running", "chrome.exe process is running")


def test_seed_color_to_skcolor_int_matches_chrome_158_signed_argb():
    assert seed_color_to_skcolor_int("#22C55E") == -14498466
    assert seed_color_to_skcolor_int("#7C3AED") == -8635667
    assert seed_color_to_skcolor_int("#FE5722") == -108766


def test_chrome_instance_discovery_precedence_and_safe_profile_fallback(tmp_path, monkeypatch):
    user_data = tmp_path / "LocalAppData" / "Google" / "Chrome" / "User Data"
    default_pref = _write_preferences(user_data / "Default" / "Preferences", {"browser": {"theme": {}}})
    profile1_pref = _write_preferences(user_data / "Profile 1" / "Preferences", {"browser": {"theme": {}}})
    override_pref = _write_preferences(tmp_path / "custom" / "Work" / "Preferences", {"browser": {"theme": {}}})
    local_state = user_data / "Local State"
    local_state.write_text(json.dumps({"profile": {"last_used": "Profile 1"}}), encoding="utf-8")

    # Local State last_used takes priority over Default (even with space in "Profile 1")
    monkeypatch.delenv("ONE_TONE_CHROME_PREFERENCES", raising=False)
    discovered = discover_chrome_instance(tmp_path / "LocalAppData")
    assert discovered["status"] == "ok"
    assert discovered["preferences_path"] == str(profile1_pref)
    assert discovered["profile"] == "Profile 1"
    assert discovered["source"] == "local_state"

    # Unsafe last_used falls back safely to Default
    local_state.write_text(json.dumps({"profile": {"last_used": "../escape"}}), encoding="utf-8")
    fallback = discover_chrome_instance(tmp_path / "LocalAppData")
    assert fallback["status"] == "ok"
    assert fallback["preferences_path"] == str(default_pref)
    assert fallback["profile"] == "Default"
    assert fallback["source"] == "default"

    # Explicit environment variable overrides Local State and Default
    monkeypatch.setenv("ONE_TONE_CHROME_PREFERENCES", str(override_pref))
    env_discovered = discover_chrome_instance(tmp_path / "LocalAppData")
    assert env_discovered["status"] == "ok"
    assert env_discovered["preferences_path"] == str(override_pref)
    assert env_discovered["profile"] == "Work"
    assert env_discovered["source"] == "env"


def test_chrome_discovery_skips_missing_or_corrupt_preferences(tmp_path, monkeypatch):
    monkeypatch.delenv("ONE_TONE_CHROME_PREFERENCES", raising=False)
    assert discover_chrome_instance(tmp_path / "Missing")["status"] == "skipped"

    bad_pref = tmp_path / "Bad" / "Preferences"
    bad_pref.parent.mkdir(parents=True)
    bad_pref.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_CHROME_PREFERENCES", str(bad_pref))
    assert discover_chrome_instance()["status"] == "skipped"

    bad_section = tmp_path / "BadSection" / "Preferences"
    bad_section.parent.mkdir(parents=True)
    bad_section.write_text(json.dumps({"browser": "not-an-object"}), encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_CHROME_PREFERENCES", str(bad_section))
    assert discover_chrome_instance()["status"] == "skipped"

    bad_sync = tmp_path / "BadSync" / "Preferences"
    bad_sync.parent.mkdir(parents=True)
    bad_sync.write_text(json.dumps({"sync": "not-an-object"}), encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_CHROME_PREFERENCES", str(bad_sync))
    assert discover_chrome_instance()["status"] == "skipped"

    bad_dts = tmp_path / "BadDts" / "Preferences"
    bad_dts.parent.mkdir(parents=True)
    bad_dts.write_text(json.dumps({"sync": {"data_type_status_for_sync_to_signin": "not-an-object"}}), encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_CHROME_PREFERENCES", str(bad_dts))
    assert discover_chrome_instance()["status"] == "skipped"


def test_chrome_full_cycle_applies_verifies_and_detects_drift_without_writes(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "bookmark_bar": {"show_on_all_tabs": True},
            "browser": {
                "show_home_button": True,
                "theme": {
                    "color_scheme2": 2,
                    "follows_system_colors": True,
                    "is_grayscale2": True,
                },
            },
            "extensions": {
                "theme": {
                    "id": "oldextensionid123456789012345678",
                    "pack": "C:\\old\\theme-pack",
                },
            },
            "autogenerated": {"theme": {"color": 12345}},
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-ok-001", target_instances={"chrome": adapter.target_instance()})

    detected = adapter.detect()
    assert detected.status == "ok"
    assert detected.version == CHROME_PREFERENCES_SCHEMA_V1
    assert detected.metadata["sync_caveat"] is False

    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    applied = adapter.apply_with_backup(plan, backup_dir)
    assert applied.status == "ok"
    assert applied.changed is True
    assert applied.requires_user_action is False
    assert applied.metadata["rendering_verification"] == "untested"

    written = json.loads(pref_path.read_text(encoding="utf-8"))
    assert written["bookmark_bar"] == {"show_on_all_tabs": True}
    assert written["browser"]["show_home_button"] is True
    assert written["browser"]["theme"] == {
        "color_scheme2": CHROME_COLOR_SCHEME_SYSTEM,
        "color_variant2": CHROME_COLOR_VARIANT_TONAL_SPOT,
        "follows_system_colors": False,
        "user_color2": -14498466,
    }
    assert written["extensions"]["theme"] == {"id": CHROME_USER_COLOR_THEME_ID}
    assert "color" not in written["autogenerated"]["theme"]
    assert "sync" not in written  # pure local non-synced profile never gets a fabricated sync block

    verified = adapter.verify(plan)
    assert verified.status == "ok"
    assert verified.verified is True
    assert verified.requires_user_action is False
    assert verified.metadata["rendering_verification"] == "untested"

    # Boolean masquerading as int must fail verify without touching file
    drifted = dict(written)
    drifted["browser"]["theme"] = dict(written["browser"]["theme"], color_variant2=True)
    _write_preferences(pref_path, drifted)
    before_bytes = pref_path.read_bytes()
    drift_res = adapter.verify(plan)
    assert drift_res.status == "failed"
    assert drift_res.verified is False
    assert pref_path.read_bytes() == before_bytes

    # Corrupted JSON after locking instance must report failed in verify
    pref_path.write_text("{broken", encoding="utf-8")
    corrupt_bytes = pref_path.read_bytes()
    corrupt_res = adapter.verify(plan)
    assert corrupt_res.status == "failed"
    assert corrupt_res.verified is False
    assert pref_path.read_bytes() == corrupt_bytes


def test_chrome_theme_sync_isolation_custom_sync_verify_drift_and_rollback(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "browser": {"theme": {"saved_local_theme": "CAAQAEgB", "user_color2": -8635667}},
            "account_values": {"browser": {"theme": {"color_scheme": 0}}},
            "extensions": {"theme": {"id": CHROME_USER_COLOR_THEME_ID}},
            "sync": {
                "has_setup_completed": True,
                "keep_everything_synced": False,
                "themes": True,
                "bookmarks": True,
                "passwords": True,
                "data_type_status_for_sync_to_signin": {"themes": True, "bookmarks": True},
            },
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-sync-iso-001", target_instances={"chrome": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    detected = adapter.detect()
    assert detected.status == "ok"
    assert detected.metadata["sync_caveat"] is True
    assert "isolate theme sync" in detected.message

    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.APPLIED

    written = json.loads(pref_path.read_text(encoding="utf-8"))
    assert "saved_local_theme" not in written["browser"]["theme"]
    assert written["sync"]["keep_everything_synced"] is False
    assert written["sync"]["themes"] is False
    assert written["sync"]["data_type_status_for_sync_to_signin"]["themes"] is False
    assert written["sync"]["bookmarks"] is True
    assert written["sync"]["passwords"] is True
    assert written["sync"]["data_type_status_for_sync_to_signin"]["bookmarks"] is True
    assert written["account_values"] == {"browser": {"theme": {"color_scheme": 0}}}

    verified = adapter.verify(plan)
    assert verified.status == "ok"
    assert verified.verified is True
    assert verified.metadata["sync_caveat"] is False

    # User re-enabling any theme sync switch or restoring saved_local_theme fails verify read-only
    for mutate_label, mutator in (
        ("sync.themes", lambda d: d["sync"].__setitem__("themes", True)),
        ("sync.keep_everything_synced", lambda d: d["sync"].__setitem__("keep_everything_synced", True)),
        ("sync.data_type_status_for_sync_to_signin.themes", lambda d: d["sync"]["data_type_status_for_sync_to_signin"].__setitem__("themes", True)),
        ("browser.theme.saved_local_theme", lambda d: d["browser"]["theme"].__setitem__("saved_local_theme", "CAAQAEgB")),
    ):
        drifted = json.loads(json.dumps(written))
        mutator(drifted)
        _write_preferences(pref_path, drifted)
        before_bytes = pref_path.read_bytes()
        drift_res = adapter.verify(plan)
        assert drift_res.status == "failed", f"expected verify failure when mutating {mutate_label}"
        assert drift_res.verified is False
        assert drift_res.metadata["sync_caveat"] is True
        assert pref_path.read_bytes() == before_bytes

    # Restore clean post-Apply state and mutate an unrelated setting before Rollback
    post_apply = json.loads(json.dumps(written))
    post_apply["bookmark_bar"] = {"show_on_all_tabs": True}
    _write_preferences(pref_path, post_apply)

    rb = store.rollback(record.id, {"chrome": adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK
    after_rb = json.loads(pref_path.read_text(encoding="utf-8"))
    assert after_rb["bookmark_bar"] == {"show_on_all_tabs": True}
    assert after_rb["browser"]["theme"]["saved_local_theme"] == "CAAQAEgB"
    assert after_rb["sync"]["themes"] is True
    assert after_rb["sync"]["keep_everything_synced"] is False
    assert after_rb["sync"]["data_type_status_for_sync_to_signin"]["themes"] is True


def test_chrome_theme_sync_isolation_expands_keep_everything_synced_and_rolls_back(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "browser": {"theme": {"saved_local_theme": "CAAQAEgB"}},
            "sync": {
                "has_setup_completed": True,
                "keep_everything_synced": True,
                "passwords": False,
            },
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-keepall-001", target_instances={"chrome": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.APPLIED
    written = json.loads(pref_path.read_text(encoding="utf-8"))
    assert written["sync"]["keep_everything_synced"] is False
    assert written["sync"]["themes"] is False
    assert written["sync"]["bookmarks"] is True
    assert written["sync"]["extensions"] is True
    assert written["sync"]["passwords"] is False  # explicit False preserved
    assert "saved_local_theme" not in written["browser"]["theme"]

    verified = adapter.verify(plan)
    assert verified.status == "ok"
    assert verified.metadata["sync_caveat"] is False

    rb = store.rollback(record.id, {"chrome": adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK
    after_rb = json.loads(pref_path.read_text(encoding="utf-8"))
    assert after_rb["sync"]["keep_everything_synced"] is True
    assert after_rb["sync"]["passwords"] is False
    assert "themes" not in after_rb["sync"]
    assert "bookmarks" not in after_rb["sync"]
    assert after_rb["browser"]["theme"]["saved_local_theme"] == "CAAQAEgB"


def test_chrome_unmanaged_account_values_conflict_retains_sync_caveat_after_isolation(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "browser": {"theme": {"saved_local_theme": "CAAQAEgB"}},
            "account_values": {"browser": {"theme": {"user_color2": -8635667}}},
            "sync": {"has_setup_completed": True, "keep_everything_synced": False, "themes": True},
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-acct-001", target_instances={"chrome": adapter.target_instance()})
    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    applied = adapter.apply_with_backup(plan, backup_dir)
    assert applied.status == "ok"
    assert applied.metadata["sync_caveat"] is True
    assert "Customize Chrome" in applied.message
    verified = adapter.verify(plan)
    assert verified.status == "ok"
    assert verified.metadata["sync_caveat"] is True


def test_chrome_legacy_v10_snapshot_rolls_back_cleanly(tmp_path):
    import hashlib

    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "browser": {"theme": {"color_scheme2": 0, "color_variant2": 1, "follows_system_colors": False, "user_color2": -14498466}},
            "extensions": {"theme": {"id": CHROME_USER_COLOR_THEME_ID}},
            "autogenerated": {"theme": {}},
        },
    )
    raw = pref_path.read_bytes()
    backup_dir = tmp_path / "legacy-v10-backup"
    backup_dir.mkdir(parents=True)
    legacy_state = {
        "schema": CHROME_PREFERENCES_SCHEMA_V1,
        "preferences_path": str(pref_path),
        "profile": "Default",
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "containers": {"browser": True, "browser.theme": True, "extensions": True, "extensions.theme": True},
        "entries": {
            "browser.theme.color_scheme2": {"existed": False},
            "browser.theme.color_variant2": {"existed": False},
            "browser.theme.follows_system_colors": {"existed": False},
            "browser.theme.user_color2": {"existed": False},
            "browser.theme.is_grayscale2": {"existed": False},
            "extensions.theme.id": {"existed": True, "value": "old-id"},
            "extensions.theme.pack": {"existed": False},
            "autogenerated.theme.color": {"existed": False},
        },
    }
    (backup_dir / "chrome-state.json").write_text(json.dumps(legacy_state), encoding="utf-8")

    rb = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe).rollback(backup_dir)
    assert rb.status == "ok"
    assert rb.verified is True
    restored = json.loads(pref_path.read_text(encoding="utf-8"))
    assert restored["extensions"]["theme"] == {"id": "old-id"}
    assert "user_color2" not in restored["browser"]["theme"]


def test_chrome_live_process_guard_blocks_running_and_win32_enumeration_failures(tmp_path, monkeypatch):
    pref_path = _write_preferences(tmp_path / "Default" / "Preferences", {"browser": {"theme": {}}})
    original = pref_path.read_bytes()

    running_adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_running_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-guard-001", target_instances={"chrome": running_adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    # Detect remains read-only ok, while Snapshot/Apply skip without touching Preferences
    assert running_adapter.detect().status == "ok"
    record = apply_plan(plan, {"chrome": running_adapter}, store, confirm=True)
    assert record.status == TransactionStatus.FAILED
    assert pref_path.read_bytes() == original

    # Pre-replace second process check blocks if Chrome launches after entry check
    calls = 0

    def _race_probe() -> tuple[str, str]:
        nonlocal calls
        calls += 1
        return ("stopped", "ok") if calls == 1 else ("running", "launched before replace")

    clean_adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    backup_dir = tmp_path / "backup"
    assert clean_adapter.snapshot(backup_dir).status == "ok"
    race_adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_race_probe)
    race_result = race_adapter.apply_with_backup(plan, backup_dir)
    assert race_result.status == "skipped"
    assert race_result.changed is False
    assert pref_path.read_bytes() == original

    # Rollback fails closed when Chrome is running
    assert clean_adapter.apply_with_backup(plan, backup_dir).status == "ok"
    rb_blocked = running_adapter.rollback(backup_dir)
    assert rb_blocked.status == "failed"
    assert rb_blocked.changed is False
    assert rb_blocked.verified is False

    # Win32 Process32NextW returning FALSE with error 0 must fail closed as 'unknown'
    monkeypatch.setattr("one_tone.adapters.chrome.sys.platform", "win32")

    class _ZeroErrorNextKernel32:
        def CreateToolhelp32Snapshot(self, flags, pid):
            return 123

        def Process32FirstW(self, snapshot, entry_ptr):
            return 1

        def Process32NextW(self, snapshot, entry_ptr):
            ctypes.set_last_error(0)
            return 0

        def CloseHandle(self, handle):
            return 1

    monkeypatch.setattr("one_tone.adapters.chrome._create_kernel32", lambda: _ZeroErrorNextKernel32())
    status, _ = probe_chrome_process()
    assert status == "unknown"


def test_chrome_concurrent_tamper_aborts_before_write_without_overwriting(tmp_path):
    pref_path = _write_preferences(tmp_path / "Default" / "Preferences", {"browser": {"theme": {}}, "keep": "v1"})
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-tamper-001", target_instances={"chrome": adapter.target_instance()})
    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"

    # Concurrent edit happens after snapshot before apply
    _write_preferences(pref_path, {"browser": {"theme": {}}, "keep": "concurrent_user_edit"})
    res = adapter.apply_with_backup(plan, backup_dir)
    assert res.status == "failed"
    assert res.changed is False
    assert res.metadata.get("aborted_before_write") is True
    assert json.loads(pref_path.read_text(encoding="utf-8"))["keep"] == "concurrent_user_edit"


def test_chrome_field_level_rollback_preserves_post_apply_edits_and_rejects_redirects(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Profile 1" / "Preferences",
        {
            "bookmark_bar": {"show_on_all_tabs": False},
            "extensions": {"theme": {"id": "oldext", "pack": "C:\\old"}},
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-rb-001", target_instances={"chrome": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.APPLIED

    # User adds bookmarks/settings AFTER Apply
    post_apply = json.loads(pref_path.read_text(encoding="utf-8"))
    post_apply["bookmark_bar"]["show_on_all_tabs"] = True
    post_apply["new_user_setting"] = {"preserved": True}
    _write_preferences(pref_path, post_apply)

    # Cross-process new ChromeAdapter instance rolls back cleanly via TransactionStore
    second_adapter = ChromeAdapter(process_probe=_stopped_probe)
    rb = store.rollback(record.id, {"chrome": second_adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK

    after_rb = json.loads(pref_path.read_text(encoding="utf-8"))
    assert after_rb["bookmark_bar"]["show_on_all_tabs"] is True
    assert after_rb["new_user_setting"] == {"preserved": True}
    assert after_rb["extensions"]["theme"] == {"id": "oldext", "pack": "C:\\old"}
    assert "browser" not in after_rb  # newly created container cleaned up when empty

    # Legacy snapshot without chrome-state.json is rejected
    legacy_backup = tmp_path / "legacy-backup"
    legacy_backup.mkdir()
    legacy_rb = second_adapter.rollback(legacy_backup, {"artifacts": ["old.zip"], "unpacked_dirs": ["old"]})
    assert legacy_rb.status == "failed"
    assert legacy_rb.verified is False


def test_chrome_rollback_rejects_symlink_or_junction_redirected_path(tmp_path):
    pref_a = _write_preferences(tmp_path / "a" / "Default" / "Preferences", {"browser": {"theme": {}}})
    pref_b = _write_preferences(tmp_path / "b" / "Default" / "Preferences", {"browser": {"theme": {}}, "other": "keep_b"})
    original_b = pref_b.read_bytes()

    adapter = ChromeAdapter(preferences_path=pref_a, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-symlink-001", target_instances={"chrome": adapter.target_instance()})
    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply_with_backup(plan, backup_dir).status == "ok"

    pref_a.unlink()
    try:
        pref_a.symlink_to(pref_b)
    except OSError:
        import shutil
        shutil.rmtree(pref_a.parent)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(pref_a.parent), str(pref_b.parent)], check=True, capture_output=True)

    rb = ChromeAdapter(process_probe=_stopped_probe).rollback(backup_dir)
    assert rb.status == "failed"
    assert rb.verified is False
    assert pref_b.read_bytes() == original_b


def test_chrome_removes_ntp_custom_background_and_restores_on_rollback(tmp_path):
    pref_path = _write_preferences(
        tmp_path / "Default" / "Preferences",
        {
            "browser": {"theme": {}},
            "ntp": {
                "custom_background_dict": {"background_url": "https://example.com/bg.jpg"},
                "custom_background_local_to_device": True,
                "shortcuts_auto_removal_disabled": True,
            },
        },
    )
    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=_stopped_probe)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-ntp-001", target_instances={"chrome": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.APPLIED
    after_apply = json.loads(pref_path.read_text(encoding="utf-8"))
    assert "custom_background_dict" not in after_apply["ntp"]
    assert "custom_background_local_to_device" not in after_apply["ntp"]
    assert after_apply["ntp"]["shortcuts_auto_removal_disabled"] is True

    rb = store.rollback(record.id, {"chrome": adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK
    after_rb = json.loads(pref_path.read_text(encoding="utf-8"))
    assert after_rb["ntp"]["custom_background_dict"] == {"background_url": "https://example.com/bg.jpg"}
    assert after_rb["ntp"]["custom_background_local_to_device"] is True


def test_chrome_managed_process_shutdown_graceful_force_and_fail_closed(tmp_path):
    # 1) close_windows_process tries graceful close first, then force-kills on timeout, never kills 'unknown'
    commands: list[list[str]] = []
    probe_seq = iter([("running", "alive"), ("running", "still closing"), ("stopped", "exited")])

    def fake_runner(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ok, detail = close_windows_process(
        "chrome.exe",
        graceful_timeout=0.05,
        force_timeout=0.05,
        poll_interval=0.01,
        process_probe=lambda: next(probe_seq, ("stopped", "exited")),
        command_runner=fake_runner,
    )
    assert ok is True
    assert "gracefully" in detail
    assert commands == [["taskkill", "/IM", "chrome.exe", "/T"]]

    # Force kill path when graceful times out
    commands.clear()
    force_seq = iter([("running", "1"), ("running", "2"), ("running", "3"), ("stopped", "killed")])
    ok_force, detail_force = close_windows_process(
        "chrome.exe",
        graceful_timeout=0.0,
        force_timeout=0.05,
        poll_interval=0.01,
        process_probe=lambda: next(force_seq, ("stopped", "killed")),
        command_runner=fake_runner,
    )
    assert ok_force is True
    assert "forcefully" in detail_force
    assert commands == [
        ["taskkill", "/IM", "chrome.exe", "/T"],
        ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
    ]

    # Unknown probe never invokes taskkill
    commands.clear()
    ok_unknown, _ = close_windows_process(
        "chrome.exe",
        process_probe=lambda: ("unknown", "enumeration error"),
        command_runner=fake_runner,
    )
    assert ok_unknown is False
    assert commands == []

    # 2) ChromeAdapter uses process_closer during snapshot/apply/rollback, never during detect/verify
    pref_path = _write_preferences(tmp_path / "Default" / "Preferences", {"browser": {"theme": {}}})
    state = {"running": True, "close_calls": 0}

    def probe():
        return ("running", "chrome alive") if state["running"] else ("stopped", "chrome exited")

    def closer():
        state["close_calls"] += 1
        state["running"] = False
        return (True, "closed")

    adapter = ChromeAdapter(preferences_path=pref_path, process_probe=probe, process_closer=closer)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-close-001", target_instances={"chrome": adapter.target_instance()})
    assert adapter.detect().status == "ok"
    assert state["close_calls"] == 0

    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.APPLIED
    assert state["close_calls"] == 1  # closed at snapshot; stopped at apply

    state["running"] = True
    rb = store.rollback(record.id, {"chrome": adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK
    assert state["close_calls"] == 2

    # Persistent failure to exit blocks write fail-closed
    stubborn = ChromeAdapter(
        preferences_path=pref_path,
        process_probe=lambda: ("running", "stuck"),
        process_closer=lambda: (False, "cannot kill"),
    )
    assert stubborn.rollback(store.backup_path_for(record.id, "chrome")).status == "failed"
