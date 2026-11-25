import json

import pytest

from one_tone.palette import generate_palette
from one_tone.plan import PlanIntegrityError, compute_plan_hash, create_plan, load_plan, save_plan


def _chrome_instance(tmp_path):
    pref = tmp_path / "Google" / "Chrome" / "User Data" / "Default" / "Preferences"
    pref.parent.mkdir(parents=True, exist_ok=True)
    pref.write_text(json.dumps({"browser": {"theme": {}}}), encoding="utf-8")
    return pref, {"status": "ok", "preferences_path": str(pref), "profile": "Default", "source": "explicit"}


def test_old_plan_requires_preview_without_blocking_historical_rollback(tmp_path):
    from one_tone.transaction import TransactionStore, apply_plan
    from one_tone.adapters.chrome import ChromeAdapter
    pref, instance = _chrome_instance(tmp_path)
    plan = create_plan("#22C55E", ["chrome"], target_instances={"chrome": instance})
    adapter = ChromeAdapter(preferences_path=pref, process_probe=lambda: ("stopped", "test"))
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"chrome": adapter}, store, confirm=True)
    payload = plan.to_dict()
    payload.pop("appearance_policy", None)
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / f"{plan.id}.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanIntegrityError, match="Preview"):
        load_plan(plan.id, tmp_path)
    assert store.rollback(record.id, {"chrome": ChromeAdapter(process_probe=lambda: ("stopped", "test"))}).status.value == "ROLLED_BACK"


def test_plan_round_trips_with_stable_hash(tmp_path):
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#7C3AED", ["chrome", "windows"], plan_id="plan-test-001", target_instances={"chrome": instance})
    path = save_plan(plan, tmp_path)
    loaded = load_plan("plan-test-001", tmp_path)

    assert loaded == plan
    assert len(plan.hash) == 64
    assert path.name == "plan-test-001.json"


def test_plan_hash_rejects_tampering(tmp_path):
    save_plan(create_plan("#7C3AED", ["windows"], plan_id="plan-test-002"), tmp_path)
    path = tmp_path / "plan-test-002.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["targets"] = ["chrome"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="Hash"):
        load_plan("plan-test-002", tmp_path)


def test_plan_rejects_legacy_codex_target(tmp_path):
    payload = create_plan("#7C3AED", ["chatgpt-app"], plan_id="plan-legacy-codex-001").to_dict()
    payload["targets"] = ["codex"]
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-legacy-codex-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="legacy target codex"):
        load_plan("plan-legacy-codex-001", tmp_path)


def test_plan_rejects_path_like_targets_and_plan_ids(tmp_path):
    with pytest.raises(ValueError, match="safe"):
        create_plan("#7C3AED", ["../../escaped"], plan_id="plan-safe-001")

    with pytest.raises(ValueError, match="safe"):
        create_plan("#7C3AED", ["windows"], plan_id="../escaped")

    with pytest.raises(ValueError, match="safe"):
        load_plan("../escaped", tmp_path)


def test_plan_rejects_filename_and_payload_id_mismatch(tmp_path):
    plan = create_plan("#7C3AED", ["windows"], plan_id="plan-file-id-001")
    payload = plan.to_dict()
    payload["id"] = "plan-payload-id-002"
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-file-id-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="ID mismatch"):
        load_plan("plan-file-id-001", tmp_path)


def test_plan_persists_both_mode_palettes_and_capabilities(tmp_path):
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-modes-001", target_instances={"chrome": instance})
    save_plan(plan, tmp_path)
    loaded = load_plan("plan-modes-001", tmp_path)

    assert set(loaded.palettes) == {"light", "dark"}
    assert loaded.palettes["light"]["surface"] != loaded.seed_color
    assert loaded.palettes["dark"]["surface"] != loaded.seed_color
    assert loaded.field_capabilities["chrome"]["browser.theme.user_color2"] == "supported"


def test_plan_includes_public_list_selection_backgrounds_for_trae():
    plan = create_plan("#10B981", ["trae"], plan_id="plan-trae-list-selection-001", target_instances={"trae": {"color_baseline": "1.107.1"}})

    assert plan.field_capabilities["trae"]["list.inactiveSelectionBackground"] == "supported"
    assert plan.field_capabilities["trae"]["list.focusBackground"] == "supported"


def test_plan_persists_target_instance_paths_and_hashes_them(tmp_path):
    instances = {
        "vscode": {
            "status": "ok",
            "executable": str(tmp_path / "bin" / "code.cmd"),
            "settings_path": str(tmp_path / "data" / "user-data" / "User" / "settings.json"),
            "extensions_dir": str(tmp_path / "data" / "extensions"),
            "source": "portable",
        }
    }
    plan = create_plan("#7C3AED", ["vscode"], plan_id="plan-instance-001", target_instances=instances)
    save_plan(plan, tmp_path / "plans")

    loaded = load_plan("plan-instance-001", tmp_path / "plans")

    assert loaded.target_instances == instances
    payload = json.loads((tmp_path / "plans" / "plan-instance-001.json").read_text(encoding="utf-8"))
    payload["target_instances"]["vscode"]["extensions_dir"] = str(tmp_path / "other")
    (tmp_path / "plans" / "plan-instance-001.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PlanIntegrityError, match="Hash"):
        load_plan("plan-instance-001", tmp_path / "plans")


def test_plan_persists_terminal_profile_discovery_inputs(tmp_path):
    instances = {
        "terminal": {
            "status": "ok",
            "settings_path": str(tmp_path / "settings.json"),
            "powershell_executable": str(tmp_path / "pwsh.exe"),
            "profile_path": str(tmp_path / "profile.ps1"),
            "psreadline": {
                "status": "supported",
                "version": "2.4.5",
                "fields": ["InlinePrediction", "ListPrediction", "ListPredictionSelected"],
            },
        },
    }
    plan = create_plan("#10B981", ["terminal"], plan_id="plan-terminal-instance-001", target_instances=instances)
    save_plan(plan, tmp_path / "plans")

    assert load_plan("plan-terminal-instance-001", tmp_path / "plans").target_instances == instances


def test_plan_persists_only_canonical_palettes_and_reads_a_copy(tmp_path):
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-canonical-001", target_instances={"chrome": instance})
    payload = plan.to_dict()

    assert "palette" not in payload
    assert set(payload["palettes"]) == {"light", "dark"}

    selected = plan.palette_for("light")
    original_surface = selected["surface"]
    selected["surface"] = "#000000"
    assert plan.palette_for("light")["surface"] == original_surface


def test_plan_rejects_legacy_and_incomplete_palettes(tmp_path):
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-invalid-001", target_instances={"chrome": instance})
    payload = plan.to_dict()
    payload["palette"] = payload["palettes"]["dark"]
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-invalid-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="legacy"):
        load_plan("plan-invalid-001", tmp_path)

    payload = plan.to_dict()
    payload["palettes"].pop("light")
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-invalid-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="light"):
        load_plan("plan-invalid-001", tmp_path)

    payload = plan.to_dict()
    payload["palettes"]["sepia"] = payload["palettes"]["dark"]
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-invalid-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="exactly"):
        load_plan("plan-invalid-001", tmp_path)


def test_plan_rejects_incoherent_mode_palettes(tmp_path):
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-incoherent-001", target_instances={"chrome": instance})
    payload = plan.to_dict()
    payload["palettes"]["dark"] = generate_palette("#00A86B", "dark")
    payload["hash"] = compute_plan_hash(payload)
    (tmp_path / "plan-incoherent-001.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="incoherent"):
        load_plan("plan-incoherent-001", tmp_path)


def test_old_v8_plan_is_rejected_for_v9_appearance_policy(tmp_path):
    """Old v8 plans must be recreated through Preview after single-value surface policy bump."""
    plan = create_plan("#22C55E", ["windows", "antigravity"], plan_id="plan-v8-001")
    path = save_plan(plan, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["appearance_policy"]["revision"] = "2026-11-22.v8"
    payload["appearance_policy"].pop("windows.single_value_surfaces", None)
    payload["appearance_policy"].pop("antigravity.hub_surface", None)
    payload["appearance_policy"]["windows.wallpaper_mode_matching"] = "app_mode_with_idesktopwallpaper"
    payload["appearance_policy"]["antigravity.hub_mode_matching"] = "app_mode"
    payload["hash"] = compute_plan_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="appearance policy"):
        load_plan("plan-v8-001", tmp_path)


def test_old_v9_plan_is_rejected_for_v10_appearance_policy(tmp_path):
    """Old v9 plans must be recreated through Preview after Chrome native Preferences policy bump."""
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-v9-001", target_instances={"chrome": instance})
    path = save_plan(plan, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["appearance_policy"]["revision"] = "2026-11-24.v9"
    payload["appearance_policy"].pop("chrome", None)
    payload["appearance_policy"]["chrome_activation"] = "manual"
    payload["hash"] = compute_plan_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="appearance policy"):
        load_plan("plan-v9-001", tmp_path)


def test_old_v10_plan_is_rejected_for_v11_appearance_policy(tmp_path):
    """Old v10 plans must be recreated through Preview after v11 policy bump."""
    _, instance = _chrome_instance(tmp_path)
    plan = create_plan("#22C55E", ["chrome"], plan_id="plan-v10-001", target_instances={"chrome": instance})
    path = save_plan(plan, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["appearance_policy"]["revision"] = "2026-11-24.v10"
    payload["appearance_policy"].pop("live_process_shutdown", None)
    payload["appearance_policy"]["chrome"] = "native_preferences_system_following_tonal_spot"
    payload["hash"] = compute_plan_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="appearance policy"):
        load_plan("plan-v10-001", tmp_path)


def test_plan_rejects_relative_chatgpt_app_target_instance(tmp_path):
    relative_plan = create_plan(
        "#22C55E",
        ["chatgpt-app"],
        plan_id="plan-codex-rel-inst-001",
        target_instances={"chatgpt-app": {"status": "ok", "config_path": "relative/config.toml"}},
    )
    save_plan(relative_plan, tmp_path)
    with pytest.raises(PlanIntegrityError, match="absolute"):
        load_plan("plan-codex-rel-inst-001", tmp_path)


def test_plan_rejects_missing_or_relative_chrome_target_instance(tmp_path):
    missing_plan = create_plan("#22C55E", ["chrome"], plan_id="plan-chrome-missing-inst-001")
    save_plan(missing_plan, tmp_path)
    with pytest.raises(PlanIntegrityError, match="frozen chrome target instance"):
        load_plan("plan-chrome-missing-inst-001", tmp_path)

    relative_plan = create_plan(
        "#22C55E",
        ["chrome"],
        plan_id="plan-chrome-rel-inst-001",
        target_instances={"chrome": {"status": "ok", "preferences_path": "Default/Preferences", "profile": "Default"}},
    )
    save_plan(relative_plan, tmp_path)
    with pytest.raises(PlanIntegrityError, match="absolute"):
        load_plan("plan-chrome-rel-inst-001", tmp_path)
