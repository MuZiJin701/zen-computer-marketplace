import json
import subprocess
import pytest

import one_tone.palette as palette_module
from one_tone.adapters.terminal import TerminalAdapter, resolve_default_profile
from one_tone.palette import contrast_ratio, parse_hex_color
from one_tone.plan import create_plan


def _psreadline_probe_runner(command, **kwargs):
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps({
            "profile": str(kwargs["profile_path"]),
            "version": "2.4.5",
            "host_version": "7.6.2",
            "edition": "Core",
            "fields": ["InlinePrediction", "ListPrediction", "ListPredictionSelected"],
        }),
        stderr="",
    )


@pytest.mark.parametrize("pwsh_available", [True, False])
def test_terminal_prediction_prefers_powershell7_and_never_falls_back_to_windows_powershell(tmp_path, monkeypatch, pwsh_available):
    import shutil

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"profiles": {"list": [{"name": "local"}]}}), encoding="utf-8")
    profile = tmp_path / "PowerShell" / "profile.ps1"
    pwsh = tmp_path / "pwsh.exe"
    legacy = tmp_path / "powershell.exe"
    monkeypatch.delenv("ONE_TONE_POWERSHELL_EXECUTABLE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda command: str(pwsh) if command == "pwsh" and pwsh_available else str(legacy) if command == "powershell" else None)

    def runner(command, **kwargs):
        assert command[0] == str(pwsh)
        return _psreadline_probe_runner(command, profile_path=profile)

    adapter = TerminalAdapter(path, discover_shell=True, command_runner=runner)
    result = adapter.detect()
    instance = adapter.target_instance()
    if pwsh_available:
        assert instance["powershell_executable"] == str(pwsh)
        assert instance["profile_path"] == str(profile)
        assert result.metadata["psreadline"]["status"] == "supported"
    else:
        assert "powershell_executable" not in instance
        assert "profile_path" not in instance
        assert result.metadata["psreadline"]["status"] == "not-applicable"
    assert not profile.exists()


@pytest.mark.parametrize("host_version,edition", [("5.1.0", "Desktop"), ("unknown", "Core")])
def test_explicit_unverified_or_legacy_powershell_does_not_select_a_profile(tmp_path, monkeypatch, host_version, edition):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"profiles": {"list": [{"name": "local"}]}}), encoding="utf-8")
    profile = tmp_path / "legacy-profile.ps1"
    profile.write_text("# keep legacy Profile\n", encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_POWERSHELL_EXECUTABLE", str(tmp_path / "configured-host.exe"))

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            "host_version": host_version, "edition": edition, "profile": str(profile),
            "fields": ["InlinePrediction", "ListPrediction", "ListPredictionSelected"],
        }), stderr="")

    adapter = TerminalAdapter(path, discover_shell=True, command_runner=runner)
    detected = adapter.detect()
    assert detected.metadata["psreadline"]["status"] == "unsupported"
    assert "profile_path" not in adapter.target_instance()
    assert adapter.apply(create_plan("#00C853", ["terminal"])).status == "partial"
    assert profile.read_text(encoding="utf-8") == "# keep legacy Profile\n"


def test_null_default_uses_first_local_profile():
    settings = {"profiles": {"default": None, "list": [
        {"name": "Windows PowerShell", "guid": "{one}"},
        {"name": "Azure", "guid": "{two}", "source": "Windows.Terminal.Azure"},
    ]}}
    assert resolve_default_profile(settings) == (0, "profiles.default is null; first local profile selected")


def test_root_default_profile_is_used_when_profiles_default_is_missing():
    settings = {"defaultProfile": "{two}", "profiles": {"list": [
        {"name": "Windows PowerShell", "guid": "{one}"},
        {"name": "PowerShell", "guid": "{two}"},
    ]}}
    assert resolve_default_profile(settings) == (1, "defaultProfile resolved by GUID/name")


def test_terminal_apply_registers_and_selects_a_valid_scheme(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings = {
        "defaultProfile": "{two}",
        "profiles": {
            "defaults": {"colorScheme": "Missing Scheme"},
            "list": [
                {"name": "Windows PowerShell", "guid": "{one}"},
                {"name": "PowerShell", "guid": "{two}"},
            ],
        },
        "schemes": [],
    }
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    adapter = TerminalAdapter(settings_path)
    plan = create_plan("#00A86B", ["terminal"], plan_id="plan-terminal-scheme-001")

    applied = adapter.apply(plan)
    assert applied.status == "partial"
    changed = json.loads(settings_path.read_text(encoding="utf-8"))
    scheme = next(item for item in changed["schemes"] if item["name"] == "One Tone")
    theme = next(item for item in changed["themes"] if item["name"] == "One Tone")
    expected_mapping = {"light": "One Tone Light", "dark": "One Tone Dark"}
    assert changed["profiles"]["defaults"]["colorScheme"] == expected_mapping
    assert all(profile["colorScheme"] == expected_mapping for profile in changed["profiles"]["list"])
    assert changed["theme"] == "One Tone"
    palette = plan.palette_for(plan.mode)
    assert all(profile["tabColor"] == palette["accent"] for profile in changed["profiles"]["list"])
    assert scheme["background"] == palette["surface"]
    assert scheme["cursorColor"] == palette["accent_text"]
    assert contrast_ratio(scheme["foreground"], scheme["black"]) >= 7
    assert contrast_ratio(scheme["white"], scheme["black"]) >= 4.5
    assert contrast_ratio(scheme["brightBlack"], scheme["background"]) >= 4.5
    assert scheme["cyan"] == palette["accent_text"]
    assert scheme["green"] == palette["success_text"]
    assert theme["tabRow"]["background"] == palette["surface_subtle"]
    assert theme["window"]["frame"] == palette["accent"]
    assert theme["window"]["applicationTheme"] == "system"
    assert applied.metadata["generated_values"]["window.frame"] == theme["window"]["frame"]
    assert applied.metadata["generated_values"]["profile.tabColor"] == palette["accent"]
    assert adapter.verify(plan).verified is True


@pytest.mark.parametrize("seed", ["#00C853", "#10B981", "#FFD700"])
def test_terminal_functional_text_on_generated_backgrounds(tmp_path, seed):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"profiles": {"list": [{"name": "local"}]}}), encoding="utf-8")
    plan = create_plan(seed, ["terminal"])
    assert TerminalAdapter(path).apply(plan).changed
    settings = json.loads(path.read_text(encoding="utf-8"))
    for mode in ("Light", "Dark"):
        scheme = next(item for item in settings["schemes"] if item["name"] == f"One Tone {mode}")
        assert contrast_ratio(scheme["foreground"], scheme["background"]) >= 7
        assert contrast_ratio(scheme["foreground"], scheme["black"]) >= 7
        assert contrast_ratio(scheme["white"], scheme["black"]) >= 4.5
        assert contrast_ratio(scheme["black"], scheme["white"]) >= 4.5  # reverse
        assert contrast_ratio(scheme["selectionForeground"], scheme["selectionBackground"]) >= 4.5
        for field in ("brightBlack", "red", "green", "yellow", "blue", "purple", "cyan"):
            assert contrast_ratio(scheme[field], scheme["background"]) >= 4.5
        assert len({scheme[field] for field in ("red", "green", "yellow", "blue")}) == 4


@pytest.mark.parametrize("version,supported", [("1.25.2609.30003", True), ("1.15.0.0", False), ("unknown", False)])
def test_terminal_native_correction_is_discovered_bound_verified_and_restored(tmp_path, version, supported):
    from one_tone.cli import build_target_adapters
    from one_tone.plan import load_plan, save_plan
    from one_tone.transaction import TransactionStore, apply_plan

    path = tmp_path / "settings.json"
    original = json.dumps({"profiles": {
        "defaults": {"adjustIndistinguishableColors": "never", "background": "#FF0000", "font": {"face": "custom"},
                     "unfocusedAppearance": {"adjustIndistinguishableColors": "never", "foreground": "#FF0000", "opacity": 90}},
        "list": [{"name": "local", "adjustIndistinguishableColors": "indexed", "custom": 42}, {"name": "ssh"}],
    }})
    path.write_text(original, encoding="utf-8")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=version, stderr="")

    adapter = TerminalAdapter(path, terminal_executable=tmp_path / "wt.exe", command_runner=runner)
    detected = adapter.detect()
    native_field = "profile.adjustIndistinguishableColors"
    assert detected.metadata["field_capabilities"][native_field] == ("supported" if supported else "unsupported")
    assert path.read_text(encoding="utf-8") == original
    plan = create_plan("#00C853", ["terminal"], target_instances={"terminal": adapter.target_instance()})
    save_plan(plan, tmp_path / "plans")
    plan = load_plan(plan.id, tmp_path / "plans")
    bound = build_target_adapters(["terminal"], tmp_path / "state", plan.target_instances)["terminal"]
    assert bound.target_instance() == adapter.target_instance()
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"terminal": bound}, store, confirm=True)
    changed = json.loads(path.read_text(encoding="utf-8"))
    defaults = changed["profiles"]["defaults"]
    assert defaults["font"] == {"face": "custom"}
    assert "background" not in defaults
    assert "foreground" not in defaults["unfocusedAppearance"]
    assert defaults["unfocusedAppearance"]["opacity"] == 90
    assert changed["profiles"]["list"][0]["custom"] == 42
    assert bound.verify(plan).metadata["rendering_verification"] == "untested"
    if supported:
        assert defaults["adjustIndistinguishableColors"] == "always"
        assert defaults["unfocusedAppearance"]["adjustIndistinguishableColors"] == "always"
        assert all(profile["adjustIndistinguishableColors"] == "always" for profile in changed["profiles"]["list"])
        assert bound.verify(plan).verified
        changed["profiles"]["list"][1]["adjustIndistinguishableColors"] = "never"
        path.write_text(json.dumps(changed), encoding="utf-8")
        before = path.read_bytes()
        drift = bound.verify(plan)
        assert not drift.verified
        assert drift.metadata["field_capabilities"][native_field] == "failed"
        assert path.read_bytes() == before
    else:
        assert defaults["adjustIndistinguishableColors"] == "never"
        assert changed["profiles"]["list"][0]["adjustIndistinguishableColors"] == "indexed"
        assert "adjustIndistinguishableColors" not in changed["profiles"]["list"][1]
        assert bound.verify(plan).status == "partial"
    assert store.rollback(record.id, {"terminal": bound}).status.value == "ROLLED_BACK"
    assert path.read_text(encoding="utf-8") == original


def test_terminal_profile_write_failure_compensates_the_target(tmp_path, monkeypatch):
    import os
    from one_tone.transaction import TransactionStore, apply_plan

    path = tmp_path / "settings.json"
    profile = tmp_path / "profile.ps1"
    original = json.dumps({"profiles": {"list": [{"name": "local"}]}})
    path.write_text(original, encoding="utf-8")
    profile.write_text("# original\n", encoding="utf-8")
    instance = {"status": "ok", "settings_path": str(path), "profile_path": str(profile),
                "psreadline": {"status": "supported"},
                "native_correction": {"status": "supported", "executable": str(tmp_path / "wt.exe"), "version": "1.25.0.0"}}
    plan = create_plan("#00C853", ["terminal"], target_instances={"terminal": instance})
    adapter = TerminalAdapter(path, target_instance=instance)
    replace = os.replace

    def fail_profile_replace(source, destination):
        if destination == profile:
            raise OSError("simulated Profile disk failure")
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_profile_replace)
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"terminal": adapter}, store, confirm=True)
    assert record.status.value == "FAILED"
    assert path.read_text(encoding="utf-8") == original
    assert profile.read_text(encoding="utf-8") == "# original\n"
    assert any(item["operation"] == "auto_rollback" for item in record.results["terminal"])


def test_terminal_adapter_applies_theme_to_all_profiles_and_restores(tmp_path):
    settings_path = tmp_path / "settings.json"
    original = {"profiles": {"default": "{two}", "list": [
        {"name": "PowerShell", "guid": "{one}", "background": "#000000"},
        {"name": "Ubuntu", "guid": "{two}", "background": "#111111"},
    ]}}
    original_text = json.dumps(original)
    settings_path.write_text(original_text, encoding="utf-8")
    adapter = TerminalAdapter(settings_path)
    plan = create_plan("#7C3AED", ["terminal"], plan_id="plan-terminal-001")

    assert adapter.detect().status == "partial"
    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    assert adapter.apply(plan).status == "partial"
    assert adapter.verify(plan).verified is True
    changed = json.loads(settings_path.read_text(encoding="utf-8"))
    assert all(profile["colorScheme"] == {"light": "One Tone Light", "dark": "One Tone Dark"} for profile in changed["profiles"]["list"])
    assert all(profile["tabColor"] == plan.palette_for(plan.mode)["accent"] for profile in changed["profiles"]["list"])
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert settings_path.read_text(encoding="utf-8") == original_text


def test_terminal_adapter_discovers_and_rolls_back_psreadline_profile(tmp_path):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")
    original_profile = "Set-Alias ll Get-ChildItem\n"
    profile_path.write_text(original_profile, encoding="utf-8")

    def runner(command, **kwargs):
        return _psreadline_probe_runner(command, profile_path=profile_path)

    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], plan_id="plan-terminal-psreadline-001")

    assert adapter.detect().status == "partial"
    instance = adapter.target_instance()
    assert instance["profile_path"] == str(profile_path)
    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    assert adapter.apply(plan).status == "partial"
    changed_profile = profile_path.read_text(encoding="utf-8")
    assert "Set-Alias ll Get-ChildItem" in changed_profile
    assert "if ($env:WT_SESSION)" in changed_profile
    assert "InlinePrediction = $oneToneInlinePrediction" in changed_profile
    assert "ListPredictionSelected = $oneToneListPredictionSelected" in changed_profile
    red, green, blue = parse_hex_color(plan.palette_for("light")["prediction_foreground"])
    assert f"[38;2;{red};{green};{blue}m" in changed_profile
    assert adapter.apply(plan).status == "partial"
    assert profile_path.read_text(encoding="utf-8") == changed_profile
    assert adapter.verify(plan).verified is True
    with profile_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write("Set-Location C:\\Users\n")
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert profile_path.read_text(encoding="utf-8") == original_profile + "\nSet-Location C:\\Users\n"


def test_terminal_adapter_upgrades_existing_prediction_block_in_place(tmp_path):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")
    profile_path.write_text(
        "before\n"
        "# >>> one-tone windows-terminal prediction colors >>>\n"
        "old prediction settings\n"
        "# <<< one-tone windows-terminal prediction colors <<<\n"
        "after\n",
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        return _psreadline_probe_runner(command, profile_path=profile_path)

    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], mode="light")

    assert adapter.apply(plan).status == "partial"
    changed_profile = profile_path.read_text(encoding="utf-8")
    assert changed_profile.count("# >>> one-tone windows-terminal prediction colors >>>") == 1
    assert "old prediction settings" not in changed_profile
    assert changed_profile.startswith("before\n")
    assert changed_profile.endswith("after\n")


def test_terminal_adapter_reports_missing_prediction_role_without_writing_profile(tmp_path):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")
    profile_path.write_text("Set-Alias ll Get-ChildItem\n", encoding="utf-8")

    def runner(command, **kwargs):
        return _psreadline_probe_runner(command, profile_path=profile_path)

    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], mode="light")
    plan.palettes["light"].pop("prediction_foreground")

    result = adapter.apply(plan)

    assert result.status == "partial"
    assert "prediction colors unavailable" in result.message
    assert "one-tone windows-terminal prediction colors" not in profile_path.read_text(encoding="utf-8")


def test_terminal_adapter_reports_no_valid_prediction_candidate_without_writing_profile(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")
    profile_path.write_text("Set-Alias ll Get-ChildItem\n", encoding="utf-8")

    def runner(command, **kwargs):
        return _psreadline_probe_runner(command, profile_path=profile_path)

    monkeypatch.setattr(palette_module, "_prediction_foreground", lambda *args, **kwargs: None)
    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], mode="light")

    result = adapter.apply(plan)

    assert result.status == "partial"
    assert "prediction colors unavailable" in result.message
    assert profile_path.read_text(encoding="utf-8") == "Set-Alias ll Get-ChildItem\n"


def test_terminal_rollback_removes_only_managed_profile_block(tmp_path):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "new-profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")

    def runner(command, **kwargs):
        return _psreadline_probe_runner(command, profile_path=profile_path)

    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], plan_id="plan-terminal-profile-preserve-001")
    assert adapter.detect().status == "partial"
    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    assert adapter.apply(plan).status == "partial"
    with profile_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write("Set-Alias ll Get-ChildItem\n")

    assert adapter.rollback(tmp_path / "backup").verified is True
    assert profile_path.read_text(encoding="utf-8") == "\nSet-Alias ll Get-ChildItem\n"


def test_terminal_adapter_reports_unsupported_prediction_fields_without_guessing(tmp_path):
    settings_path = tmp_path / "settings.json"
    profile_path = tmp_path / "profile.ps1"
    settings_path.write_text(json.dumps({
        "profiles": {"default": "{one}", "list": [{"name": "PowerShell", "guid": "{one}"}]},
    }), encoding="utf-8")
    profile_path.write_text("Write-Host ready\n", encoding="utf-8")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"profile": str(profile_path), "version": "2.0.0", "fields": ["InlinePrediction"]}),
            stderr="",
        )

    adapter = TerminalAdapter(settings_path, powershell_executable=tmp_path / "pwsh", command_runner=runner)
    plan = create_plan("#10B981", ["terminal"], plan_id="plan-terminal-psreadline-unsupported-001")
    assert adapter.detect().status == "partial"
    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    result = adapter.apply(plan)
    assert result.status == "partial"
    assert profile_path.read_text(encoding="utf-8") == "Write-Host ready\n"
