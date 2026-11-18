import json
import zipfile
import pytest

from one_tone.adapters.chrome import ChromeAdapter, build_chrome_theme, build_chrome_theme_directory
from one_tone.palette import parse_hex_color
from one_tone.plan import create_plan
from one_tone.transaction import TransactionStore, apply_plan


@pytest.mark.parametrize("mode,artifact", [("light", "directory"), ("dark", "zip")])
def test_chrome_verifies_complete_public_manifest_and_required_artifacts(tmp_path, mode, artifact):
    # Chromium 77270bd: kOverwritableColorTable and kTintTable, independent of generation.
    colors = set("background_tab background_tab_inactive background_tab_incognito background_tab_incognito_inactive bookmark_text button_background frame frame_inactive frame_incognito frame_incognito_inactive ntp_background ntp_header ntp_link ntp_text omnibox_background omnibox_text tab_background_text tab_background_text_inactive tab_background_text_incognito tab_background_text_incognito_inactive tab_text toolbar toolbar_button_icon toolbar_text".split())
    tints = set("background_tab buttons frame frame_inactive frame_incognito frame_incognito_inactive".split())
    plan = create_plan("#22C55E", ["chrome"])
    adapter = ChromeAdapter(tmp_path)
    adapter.apply(plan)
    directory = tmp_path / f"one-tone-{plan.id}-{mode}"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["theme"]["colors"]) == colors
    assert set(manifest["theme"]["tints"]) == tints
    assert manifest["theme"]["properties"] == {"ntp_logo_alternate": int(mode == "dark")}
    assert adapter.verify(plan).verified
    manifest["theme"]["colors"]["omnibox_text"] = [1, 2, 3]
    if artifact == "directory":
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        path = tmp_path / f"one-tone-{plan.id}-{mode}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
    before = path.read_bytes()
    assert not adapter.verify(plan).verified
    assert path.read_bytes() == before
    adapter.apply(plan)
    path.unlink()
    assert not adapter.verify(plan).verified


def test_chrome_theme_zip_has_manifest_and_palette_colors(tmp_path):
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-001")
    path = build_chrome_theme(plan, tmp_path / "chrome-theme.zip")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["manifest_version"] == 3
    palette = plan.palette_for(plan.mode)
    expected_surface = list(parse_hex_color(palette["surface"]))
    expected_background = list(parse_hex_color(palette["background"]))
    expected_surface_subtle = list(parse_hex_color(palette["surface_subtle"]))
    expected_surface_raised = list(parse_hex_color(palette["surface_raised"]))
    expected_foreground = list(parse_hex_color(palette["foreground"]))
    expected_accent_text = list(parse_hex_color(palette["accent_text"]))
    assert manifest["theme"]["colors"]["frame"] == expected_surface
    assert manifest["theme"]["colors"]["toolbar"] == expected_surface_subtle
    assert manifest["theme"]["colors"]["toolbar_text"] == expected_foreground
    assert manifest["theme"]["colors"]["toolbar_button_icon"] == expected_foreground
    assert manifest["theme"]["colors"]["tab_text"] == expected_foreground
    assert manifest["theme"]["colors"]["ntp_background"] == expected_background
    assert manifest["theme"]["colors"]["omnibox_background"] == expected_surface_raised
    assert manifest["theme"]["colors"]["ntp_header"] == expected_foreground
    assert manifest["theme"]["colors"]["ntp_link"] == expected_accent_text
    assert all(isinstance(value, list) for value in manifest["theme"]["colors"].values())
    assert all(any(value) for value in manifest["theme"]["tints"].values())


def test_chrome_theme_directory_contains_loadable_manifest(tmp_path):
    plan = create_plan("#00A86B", ["chrome"], plan_id="plan-chrome-directory-001")
    directory = build_chrome_theme_directory(plan, tmp_path / "one-tone-theme")

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["theme"]["colors"]["frame"] == list(parse_hex_color(plan.palette_for(plan.mode)["surface"]))


def test_chrome_apply_requires_explicit_user_action(tmp_path):
    adapter = ChromeAdapter(tmp_path / "output")
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-002")

    assert adapter.detect().status == "ok"
    result = adapter.apply(plan)
    assert result.status == "partial"
    assert result.requires_user_action is True
    assert adapter.verify(plan).verified is True
    assert (tmp_path / "output" / "one-tone-plan-chrome-002-dark" / "manifest.json").is_file()
    assert (tmp_path / "output" / "one-tone-plan-chrome-002-light" / "manifest.json").is_file()
    assert sorted(path.name for path in (tmp_path / "output").iterdir() if path.is_dir()) == [
        "one-tone-plan-chrome-002-dark",
        "one-tone-plan-chrome-002-light",
    ]


def test_chrome_mode_artifacts_preserve_plan_palette_roles(tmp_path):
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-coherence-001")
    adapter = ChromeAdapter(tmp_path / "output")

    assert adapter.apply(plan).status == "partial"

    light_manifest = json.loads(
        (tmp_path / "output" / "one-tone-plan-chrome-coherence-001-light" / "manifest.json").read_text(encoding="utf-8")
    )
    dark_manifest = json.loads(
        (tmp_path / "output" / "one-tone-plan-chrome-coherence-001-dark" / "manifest.json").read_text(encoding="utf-8")
    )
    assert light_manifest["theme"]["colors"]["frame"] == list(parse_hex_color(plan.palette_for("light")["surface"]))
    assert dark_manifest["theme"]["colors"]["frame"] == list(parse_hex_color(plan.palette_for("dark")["surface"]))


def test_chrome_rollback_removes_zip_and_unpacked_artifacts(tmp_path):
    adapter = ChromeAdapter(tmp_path / "output")
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-rollback-001")

    assert adapter.apply(plan).status == "partial"
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert not any((tmp_path / "output").iterdir())


def test_chrome_rollback_removes_artifacts_after_new_adapter_instance(tmp_path):
    plan = create_plan("#7C3AED", ["chrome"], plan_id="plan-chrome-cross-process-001")
    store = TransactionStore(tmp_path / "transactions")
    first_adapter = ChromeAdapter(tmp_path / "output")
    record = apply_plan(plan, {"chrome": first_adapter}, store, confirm=True)
    assert record.status.value == "PARTIAL"

    second_adapter = ChromeAdapter(tmp_path / "output")
    result = store.rollback(record.id, {"chrome": second_adapter})

    assert result.status.value == "ROLLED_BACK"
    assert not (tmp_path / "output" / "one-tone-plan-chrome-cross-process-001").exists()
    assert not (tmp_path / "output" / "one-tone-plan-chrome-cross-process-001.zip").exists()
