import json
from pathlib import Path

from one_tone.adapters import AdapterResult, UnsupportedAdapter
from one_tone.cli import build_target_adapters, main
from one_tone.plan import create_plan, save_plan
from one_tone.transaction import TransactionRecord, TransactionStatus


def test_editor_version_discovery_handles_forwarded_and_versioned_launchers(tmp_path):
    from one_tone.editor_instance import discover_editor_color_baseline
    for target, version, commit in (("trae", "1.107.1", ""), ("code", "1.140.0", "commit/")):
        root = tmp_path / target
        launcher = root / "bin" / f"{target}.cmd"
        launcher.parent.mkdir(parents=True)
        package = root / commit / "resources/app/package.json"
        package.parent.mkdir(parents=True)
        package.write_text(json.dumps({"version": version}), encoding="utf-8")
        launcher.write_text(f'"%~dp0..\\{commit.replace("/", chr(92))}resources\\app\\out\\cli.js" %*', encoding="utf-8")
        shim = tmp_path / f"{target}.cmd"
        shim.write_text(f'@"{launcher}" %*', encoding="utf-8")
        assert discover_editor_color_baseline(shim) == version
        assert discover_editor_color_baseline(launcher) == version


def test_preview_inventory_uses_actual_windows_and_unknown_editor_capabilities(tmp_path, capsys, monkeypatch):
    from one_tone.adapters.windows import WindowsAdapter, WindowsConfig, InMemoryRegistryBackend, InMemoryDesktopBackend
    from one_tone.adapters.vscode_family import EditorSpec, VSCodeFamilyAdapter
    windows = WindowsAdapter(WindowsConfig(tmp_path / "wallpapers"), InMemoryRegistryBackend({"CurrentBuild": "26200", "AppsUseLightTheme": 0, "SystemUsesLightTheme": 1}), InMemoryDesktopBackend())
    editor = VSCodeFamilyAdapter(EditorSpec("vscode", "code", tmp_path / "settings.json", tmp_path / "extensions"))
    monkeypatch.setattr("one_tone.cli.build_target_adapters", lambda *args: {"windows": windows, "vscode": editor})
    assert main(["preview", "#22C55E", "--targets", "windows,vscode", "--plans-dir", str(tmp_path / "plans"), "--output", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    fields = {target: {entry["technical_field"]: entry for group in groups.values() for entry in group} for target, groups in payload["field_inventory"].items()}
    assert fields["windows"]["StartTaskbarColorPrevalence"]["capability_status"] == "unsupported"
    assert fields["windows"]["EnableTransparency"]["generated_value"] == {"light": 0, "dark": 0}
    assert fields["vscode"]["editor.foreground"]["capability_status"] == "unsupported"
    assert fields["vscode"]["editor.foreground"]["generated_value"] is None
    assert not (tmp_path / "wallpapers").exists()


def test_preview_json_output_contains_plan_id_and_targets(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ONE_TONE_CHATGPT_APP_THEME_CONFIG", str(tmp_path / "missing-config.toml"))
    code = main([
        "preview", "#7C3AED", "--targets", "chatgpt-app",
        "--plans-dir", str(tmp_path / "plans"),
        "--state-dir", str(tmp_path / "state"),
        "--output", "json",
    ])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "preview"
    assert payload["plan_id"].startswith("plan-")
    assert payload["targets"][0]["target"] == "chatgpt-app"


def test_apply_json_error_is_machine_readable(capsys):
    assert main(["apply", "missing-plan", "--confirm", "--output", "json"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["command"] == "apply"
    assert error["error"] == "Plan not found: missing-plan"


def test_apply_json_output_encodes_nested_binary_report_value(tmp_path, capsys, monkeypatch):
    plan = create_plan("#7C3AED", ["windows"], plan_id="plan-cli-binary-apply-001")
    save_plan(plan, tmp_path / "plans")
    record = TransactionRecord(
        id="tx-cli-binary-apply-001",
        plan_id=plan.id,
        status=TransactionStatus.APPLIED,
        created_at="2026-07-26T00:00:00+00:00",
        targets=("windows",),
        results={"windows": [{
            "target": "windows",
            "status": "ok",
            "changed": True,
            "verified": True,
            "message": "applied",
            "requires_user_action": False,
            "metadata": {"field_inventory": [{"generated_value": b"\x00\xff"}]},
        }]},
    )
    monkeypatch.setattr("one_tone.cli.apply_plan", lambda *args, **kwargs: record)

    assert main([
        "apply", plan.id, "--confirm", "--output", "json",
        "--plans-dir", str(tmp_path / "plans"),
        "--transactions-dir", str(tmp_path / "transactions"),
        "--state-dir", str(tmp_path / "state"),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    value = payload["targets"][0]["metadata"]["field_inventory"][0]["generated_value"]
    assert value == {"__one_tone_bytes__": "AP8="}


def test_verify_json_output_encodes_nested_binary_report_value(tmp_path, capsys, monkeypatch):
    plan = create_plan("#7C3AED", ["windows"], plan_id="plan-cli-binary-verify-001")
    save_plan(plan, tmp_path / "plans")
    result = AdapterResult(
        "windows", "ok", False, True, "verified",
        metadata={"field_inventory": [{"generated_value": b"\x00\xff"}]},
    )
    monkeypatch.setattr("one_tone.cli.build_target_adapters", lambda *args: {})
    monkeypatch.setattr("one_tone.cli.verify_plan", lambda *args: {"windows": result})

    assert main([
        "verify", plan.id, "--output", "json",
        "--plans-dir", str(tmp_path / "plans"),
        "--state-dir", str(tmp_path / "state"),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    value = payload["targets"][0]["metadata"]["field_inventory"][0]["generated_value"]
    assert value == {"__one_tone_bytes__": "AP8="}


def test_preview_writes_plan_without_creating_transaction(tmp_path, capsys):
    plans = tmp_path / "plans"
    transactions = tmp_path / "transactions"

    assert main([
        "preview", "#7C3AED", "--targets", "chatgpt-app,chrome",
        "--plans-dir", str(plans), "--transactions-dir", str(transactions),
    ]) == 0
    assert list(plans.glob("*.json"))
    assert not transactions.exists()
    assert "Plan ID:" in capsys.readouterr().out


def test_apply_requires_plan_id_and_confirmation(capsys):
    assert main(["apply"]) == 2
    assert "plan_id" in capsys.readouterr().err

    assert main(["apply", "plan-test-007"]) == 2
    assert "--confirm" in capsys.readouterr().err


def test_undocumented_file_demo_target_is_skipped_without_writing(tmp_path):
    adapter = build_target_adapters(("file-demo",), tmp_path / "state")["file-demo"]

    assert isinstance(adapter, UnsupportedAdapter)
    assert adapter.detect().status == "skipped"
    assert not (tmp_path / "state").exists()


def test_verify_cli_reports_missing_plan(capsys):
    assert main(["verify", "plan-cycle-002"]) != 0
    assert "Plan not found" in capsys.readouterr().err


def test_verify_cli_rejects_confirmation_flag(capsys):
    assert main(["verify", "plan-cycle-002", "--confirm"]) == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_vscode_family_adapter_resolves_path_cli_fallback(monkeypatch, tmp_path):
    from one_tone.adapters.vscode_family import EditorSpec, VSCodeFamilyAdapter

    settings_path = tmp_path / 'settings.json'
    settings_path.write_text('{}', encoding='utf-8')
    extensions_dir = tmp_path / 'extensions'
    spec = EditorSpec('vscode', Path('code'), settings_path, extensions_dir, color_baseline="1.140.0")

    monkeypatch.setattr(
        'one_tone.adapters.vscode_family.shutil.which',
        lambda command: r'C:\bin\code.cmd' if command == 'code' else None,
    )

    assert VSCodeFamilyAdapter(spec).detect().status == 'ok'


def test_vscode_adapter_accepts_environment_path_overrides(tmp_path, monkeypatch):
    executable = tmp_path / "bin" / "code.cmd"
    settings = tmp_path / "portable" / "settings.json"
    extensions = tmp_path / "portable" / "extensions"
    monkeypatch.setenv("ONE_TONE_VSCODE_EXECUTABLE", str(executable))
    monkeypatch.setenv("ONE_TONE_VSCODE_SETTINGS", str(settings))
    monkeypatch.setenv("ONE_TONE_VSCODE_EXTENSIONS", str(extensions))

    adapter = build_target_adapters(("vscode",), tmp_path / "state")["vscode"]

    assert adapter.spec.executable == executable
    assert adapter.spec.settings_path == settings
    assert adapter.spec.extensions_dir == extensions


def test_vscode_adapter_prefers_generic_portable_layout_over_default_user_paths(tmp_path, monkeypatch):
    executable = tmp_path / "portable" / "bin" / "code.cmd"
    executable.parent.mkdir(parents=True)
    executable.write_text("@echo off", encoding="utf-8")
    package = executable.parent.parent / "resources/app/package.json"
    package.parent.mkdir(parents=True)
    package.write_text('{"version":"1.140.0"}', encoding="utf-8")
    portable_settings = tmp_path / "portable" / "data" / "user-data" / "User" / "settings.json"
    portable_extensions = tmp_path / "portable" / "data" / "extensions"
    portable_settings.parent.mkdir(parents=True)
    portable_settings.write_text("{}", encoding="utf-8")
    portable_extensions.mkdir(parents=True)

    userprofile = tmp_path / "user"
    appdata = userprofile / "AppData" / "Roaming"
    (appdata / "Code/User").mkdir(parents=True)
    (appdata / "Code/User/settings.json").write_text("{}", encoding="utf-8")
    (userprofile / ".vscode/extensions").mkdir(parents=True)
    monkeypatch.setenv("ONE_TONE_VSCODE_EXECUTABLE", str(executable))
    monkeypatch.delenv("ONE_TONE_VSCODE_SETTINGS", raising=False)
    monkeypatch.delenv("ONE_TONE_VSCODE_EXTENSIONS", raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("USERPROFILE", str(userprofile))

    adapter = build_target_adapters(("vscode",), tmp_path / "state")["vscode"]

    assert adapter.detect().status == "ok"
    assert adapter.spec.settings_path == portable_settings
    assert adapter.spec.extensions_dir == portable_extensions
    assert adapter.target_instance()["source"] == "portable"


def test_vscode_adapter_skips_ambiguous_portable_instances_without_creating_paths(tmp_path, monkeypatch):
    executable = tmp_path / "install" / "bin" / "code.cmd"
    executable.parent.mkdir(parents=True)
    executable.write_text("@echo off", encoding="utf-8")
    for root in (tmp_path / "install", tmp_path):
        settings = root / "data" / "user-data" / "User" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{}", encoding="utf-8")
        (root / "data" / "extensions").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ONE_TONE_VSCODE_EXECUTABLE", str(executable))
    monkeypatch.delenv("ONE_TONE_VSCODE_SETTINGS", raising=False)
    monkeypatch.delenv("ONE_TONE_VSCODE_EXTENSIONS", raising=False)

    adapter = build_target_adapters(("vscode",), tmp_path / "state")["vscode"]

    assert adapter.detect().status == "skipped"
    assert adapter.target_instance()["status"] == "skipped"
    assert not (tmp_path / "state").exists()


def test_editor_adapter_uses_plan_instance_paths_over_current_discovery(tmp_path, monkeypatch):
    current_settings = tmp_path / "current-settings.json"
    current_extensions = tmp_path / "current-extensions"
    planned_settings = tmp_path / "planned-settings.json"
    planned_extensions = tmp_path / "planned-extensions"
    current_settings.write_text("{}", encoding="utf-8")
    planned_settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_VSCODE_SETTINGS", str(current_settings))
    monkeypatch.setenv("ONE_TONE_VSCODE_EXTENSIONS", str(current_extensions))

    adapter = build_target_adapters(("vscode",), tmp_path / "state", {
        "vscode": {
            "status": "ok",
            "executable": str(tmp_path / "planned-code.cmd"),
            "settings_path": str(planned_settings),
            "extensions_dir": str(planned_extensions),
            "source": "portable",
        }
    })["vscode"]

    assert adapter.spec.settings_path == planned_settings
    assert adapter.spec.extensions_dir == planned_extensions


def test_editor_adapter_skips_incomplete_plan_instance_without_environment_fallback(tmp_path, monkeypatch):
    current_settings = tmp_path / "current-settings.json"
    current_extensions = tmp_path / "current-extensions"
    current_settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_VSCODE_SETTINGS", str(current_settings))
    monkeypatch.setenv("ONE_TONE_VSCODE_EXTENSIONS", str(current_extensions))

    adapter = build_target_adapters(("vscode",), tmp_path / "state", {
        "vscode": {"status": "ok", "settings_path": str(current_settings)},
    })["vscode"]

    assert adapter.detect().status == "skipped"
    assert "incomplete" in adapter.target_instance()["reason"]


def test_cli_defaults_runtime_data_to_single_project_directory():
    from one_tone.cli import _build_parser

    args = _build_parser().parse_args(["preview", "#FFD700", "--targets", "windows"])

    from one_tone.cli import _default_runtime_dir

    runtime_dir = _default_runtime_dir()
    assert args.plans_dir == runtime_dir / "plans"
    assert args.transactions_dir == runtime_dir / "transactions"
    assert args.state_dir == runtime_dir / "state"


def test_apply_parser_defaults_transaction_retention_to_five():
    from one_tone.cli import _build_parser

    args = _build_parser().parse_args(["apply", "plan-001", "--confirm"])

    assert args.keep_transactions == 5


def test_preview_defaults_to_all_supported_targets():
    from one_tone.cli import DEFAULT_TARGETS, _build_parser

    args = _build_parser().parse_args(["preview", "#10B981"])

    assert args.targets == ",".join(DEFAULT_TARGETS)
    assert "cursor" not in DEFAULT_TARGETS


def test_terminal_adapter_derives_scoop_persist_settings_from_shim(tmp_path, monkeypatch):
    scoop_root = tmp_path / "scoop"
    executable = scoop_root / "shims" / "wt.exe"
    settings = scoop_root / "persist" / "windows-terminal" / "settings" / "settings.json"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"shim")
    settings.parent.mkdir(parents=True)
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ONE_TONE_TERMINAL_EXECUTABLE", str(executable))

    adapter = build_target_adapters(("terminal",), tmp_path / "state")["terminal"]

    assert adapter.settings_path == settings
