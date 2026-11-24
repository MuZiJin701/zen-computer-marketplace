import json

from one_tone.adapters.antigravity import (
    ANTIGRAVITY_CONFIG_SCHEMA_V1,
    AntigravityAdapter,
)
from one_tone.palette import mode_independent_surface
from one_tone.plan import create_plan


def test_antigravity_adapter_applies_verifies_and_restores_preserving_fields(tmp_path):
    config_path = tmp_path / "config.json"
    storage_path = tmp_path / "app_storage.json"
    config_path.write_text(
        json.dumps(
            {
                "userSettings": {
                    "themeMode": "THEME_MODE_DARK",
                    "customThemeSeedsDark": {"extra": "keep"},
                    "unrelated": "keep",
                },
                "topLevel": 1,
            }
        ),
        encoding="utf-8",
    )
    storage_path.write_text(
        json.dumps({"hubSurfaceBackgroundColor": "#000000", "windowBounds": {"width": 1200}}),
        encoding="utf-8",
    )
    original_config = config_path.read_bytes()
    original_storage = storage_path.read_bytes()

    adapter = AntigravityAdapter(config_path=config_path, storage_path=storage_path)
    plan = create_plan("#22C55E", ["antigravity"], plan_id="plan-antigravity-001")

    detected = adapter.detect()
    assert detected.status == "ok"
    assert detected.version == ANTIGRAVITY_CONFIG_SCHEMA_V1

    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    assert adapter.apply(plan).status == "ok"

    updated_config = json.loads(config_path.read_text(encoding="utf-8"))
    updated_storage = json.loads(storage_path.read_text(encoding="utf-8"))
    assert updated_config["topLevel"] == 1
    assert updated_config["userSettings"]["unrelated"] == "keep"
    assert updated_config["userSettings"]["themeMode"] == "THEME_MODE_INHERIT"
    assert updated_config["userSettings"]["customThemeSeedsDark"]["extra"] == "keep"

    for table, mode in (("customThemeSeedsLight", "light"), ("customThemeSeedsDark", "dark")):
        palette = plan.palette_for(mode)
        seeds = updated_config["userSettings"][table]
        assert seeds["background"] == palette["surface"]
        assert seeds["primary"] == palette["accent"]
        assert seeds["foregroundOverride"] == palette["foreground"]
        assert seeds["primaryForegroundOverride"] == palette["accent_foreground"]
        assert seeds["codeForegroundOverride"] == palette["accent_text"]

    assert updated_storage["hubSurfaceBackgroundColor"] == mode_independent_surface(plan.seed_color)
    assert updated_storage["windowBounds"] == {"width": 1200}

    assert adapter.verify(plan).verified is True
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert config_path.read_bytes() == original_config
    assert storage_path.read_bytes() == original_storage


def test_antigravity_adapter_skips_when_both_files_missing(tmp_path):
    adapter = AntigravityAdapter(config_path=tmp_path / "missing-config.json", storage_path=tmp_path / "missing-storage.json")
    assert adapter.detect().status == "skipped"


def test_antigravity_hub_surface_is_mode_independent(tmp_path):
    config_path = tmp_path / "config.json"
    storage_path = tmp_path / "app_storage.json"
    config_path.write_text(json.dumps({"userSettings": {}}), encoding="utf-8")
    storage_path.write_text(json.dumps({"hubSurfaceBackgroundColor": "#000000"}), encoding="utf-8")

    adapter = AntigravityAdapter(config_path=config_path, storage_path=storage_path)
    assert "app_mode" not in adapter.target_instance()

    expected_hub = mode_independent_surface("#22C55E")
    outputs = {}
    for mode in ("light", "dark"):
        plan = create_plan(
            "#22C55E",
            ["antigravity"],
            plan_id=f"plan-antigravity-mode-independent-{mode}",
            mode=mode,
            target_instances={"antigravity": adapter.target_instance()},
        )
        assert adapter.apply(plan).status == "ok"
        updated_storage = json.loads(storage_path.read_text(encoding="utf-8"))
        outputs[mode] = updated_storage["hubSurfaceBackgroundColor"]
        assert updated_storage["hubSurfaceBackgroundColor"] == expected_hub
        assert adapter.verify(plan).verified is True

    assert outputs["light"] == outputs["dark"] == expected_hub
