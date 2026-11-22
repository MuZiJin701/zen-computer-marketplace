from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from one_tone.adapters.antigravity import AntigravityAdapter
from one_tone.adapters.matlab import (
    MATLAB_MLSETTINGS_SCHEMA_V1,
    MatlabAdapter,
    _MANIFEST_ENTRY,
    _MANIFEST_NS,
    discover_matlab_instance,
)
from one_tone.cli import DEFAULT_TARGETS, main
from one_tone.palette import parse_hex_color
from one_tone.plan import create_plan, load_plan, save_plan
from one_tone.transaction import TransactionStatus, TransactionStore, apply_plan


def _make_mlsettings(
    path: Path,
    *,
    release: str = "R2026a",
    schema: str = "com.mathworks/settings/jsonschema/1-1-0",
    extra_groups: dict[str, dict] | None = None,
    manifest_folders: tuple[str, ...] = (
        "/settingstree/matlab/appearance/figure",
        "/settingstree/matlab/colors/commandwindow",
        "/settingstree/matlab/colors/programmingtools",
        "/settingstree/matlab/editor/displaysettings/linelimit",
    ),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    default_groups: dict[str, dict] = {
        "/settingstree/matlab/editor/displaysettings": {
            "attributes": {"groupName": "displaysettings", "readonly": False, "validationFcn": {}, "visible": True},
            "path": "/settingstree/matlab/editor/displaysettings",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": True},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": False,
                    "name": "ShowLineNumbers",
                    "value": "true",
                },
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": True},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": False,
                    "name": "HighlightCurrentLine",
                    "value": "false",
                },
            ],
        },
        "/settingstree/matlab/editor": {
            "attributes": {"groupName": "editor", "readonly": False, "validationFcn": {}, "visible": True},
            "path": "/settingstree/matlab/editor",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": True,
                    "name": "RecentFileList",
                    "value": '{"mwdata":["a.m"],"mwsize":[1,1],"mwtype":"cell"}',
                },
            ],
        },
    }
    if extra_groups:
        default_groups.update(extra_groups)

    manifest_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
        f'<fileEntries xmlns="{_MANIFEST_NS}" createdByEncoding="UTF-8" createdByPlatform="win64" version="2.0">',
        '  <fileEntry content="/fsroot/schema.json" name="/schema.json" type="File"/>',
    ]
    for folder in manifest_folders:
        if folder not in default_groups:
            manifest_lines.append(f'  <fileEntry content="" name="{folder}" type="Folder"/>')
    for group_path in sorted(default_groups):
        manifest_lines.append(
            f'  <fileEntry content="/fsroot{group_path}/settings.json" name="{group_path}/settings.json" type="File"/>'
        )
    manifest_lines.append("</fileEntries>")

    release_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<MathWorks_version_info><version>26.1.0</version><release>{release}</release></MathWorks_version_info>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fsroot/schema.json", schema)
        archive.writestr("metadata/filesystemManifest.xml", "\n".join(manifest_lines))
        archive.writestr("metadata/mwcorePropertiesReleaseInfo.xml", release_xml)
        for group_path, doc in default_groups.items():
            archive.writestr(f"fsroot{group_path}/settings.json", json.dumps(doc, separators=(",", ":")))
    return path


def _read_group(path: Path, group_path: str) -> dict | None:
    entry = f"fsroot{group_path}/settings.json"
    with zipfile.ZipFile(path, "r") as archive:
        if entry not in archive.namelist():
            return None
        return json.loads(archive.read(entry).decode("utf-8"))


def _read_manifest_map(path: Path) -> dict[str, tuple[str, str]]:
    with zipfile.ZipFile(path, "r") as archive:
        root = ET.fromstring(archive.read(_MANIFEST_ENTRY))
    tag = f"{{{_MANIFEST_NS}}}fileEntry"
    return {el.attrib["name"]: (el.attrib["type"], el.attrib["content"]) for el in root.findall(tag)}


def test_matlab_adapter_applies_verifies_and_field_rollbacks_preserving_post_apply_edits(tmp_path):
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-001", target_instances={"matlab": adapter.target_instance()})

    detected = adapter.detect()
    assert detected.status == "partial"
    assert detected.version == MATLAB_MLSETTINGS_SCHEMA_V1
    assert detected.metadata["rendering_verification"] == "untested"
    assert detected.metadata["field_capabilities"]["desktop.chrome"] == "unsupported"
    assert detected.metadata["field_capabilities"]["matlab.appearance.figure.GraphicsTheme"] == "not-applicable"

    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert (backup_dir / "matlab.mlsettings").is_file()
    assert (backup_dir / "matlab-state.json").is_file()

    applied = adapter.apply(plan)
    assert applied.status == "partial"
    assert applied.changed is True

    # Check written settings values
    appearance = _read_group(settings_path, "/settingstree/matlab/appearance")
    assert appearance is not None
    appearance_by_name = {item["name"]: item for item in appearance["settings"]}
    assert json.loads(appearance_by_name["MATLABTheme"]["value"]) == "System"

    colors = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors is not None
    colors_by_name = {item["name"]: item for item in colors["settings"]}
    desktop = json.loads(json.loads(colors_by_name["DesktopColors"]["value"]))
    syntax = json.loads(json.loads(colors_by_name["SyntaxHighlightingColors"]["value"]))
    for mode in ("light", "dark"):
        palette = plan.palette_for(mode)
        assert desktop[mode]["BackgroundColor"] == palette["surface"].lower()
        assert desktop[mode]["ForegroundColor"] == palette["foreground"].lower()
        assert syntax[mode]["CodeColor"] == palette["foreground"].lower()
        assert syntax[mode]["KeywordColor"] == palette["info_text"].lower()
        assert syntax[mode]["HyperlinkColor"] == palette["accent_text"].lower()
        assert syntax[mode]["HighlightCurrentLineColor"] == palette["surface_raised"].lower()
        assert syntax[mode]["LineColor"] == palette["border"].lower()

    light_palette = plan.palette_for("light")
    assert json.loads(colors_by_name["KeywordColor"]["value"])["mwdata"] == list(parse_hex_color(light_palette["info_text"]))

    display = _read_group(settings_path, "/settingstree/matlab/editor/displaysettings")
    assert display is not None
    display_by_name = {item["name"]: item for item in display["settings"]}
    assert display_by_name["ShowLineNumbers"]["value"] == "true"
    assert display_by_name["HighlightCurrentLine"]["value"] == "false"
    assert json.loads(display_by_name["HighlightCurrentLineColor"]["value"])["mwdata"] == list(parse_hex_color(light_palette["surface_raised"]))

    manifest = _read_manifest_map(settings_path)
    assert manifest["/settingstree/matlab/colors/settings.json"] == ("File", "/fsroot/settingstree/matlab/colors/settings.json")
    assert manifest["/settingstree/matlab/colors/commandwindow/settings.json"] == (
        "File",
        "/fsroot/settingstree/matlab/colors/commandwindow/settings.json",
    )
    assert "/settingstree/matlab/colors/commandwindow" not in manifest

    verified = adapter.verify(plan)
    assert verified.status == "partial"
    assert verified.verified is True

    # Simulate unrelated user edits made AFTER Apply (e.g., new RecentFileList & ShowLineNumbers=false)
    with zipfile.ZipFile(settings_path, "r") as zin:
        all_entries = {info.filename: (info, zin.read(info.filename)) for info in zin.infolist()}
    editor_doc = json.loads(all_entries["fsroot/settingstree/matlab/editor/settings.json"][1].decode("utf-8"))
    editor_doc["settings"][0]["value"] = '{"mwdata":["a.m","post_apply_script.m"],"mwsize":[1,2],"mwtype":"cell"}'
    disp_doc = json.loads(all_entries["fsroot/settingstree/matlab/editor/displaysettings/settings.json"][1].decode("utf-8"))
    for item in disp_doc["settings"]:
        if item["name"] == "ShowLineNumbers":
            item["value"] = "false"
    with zipfile.ZipFile(settings_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, (info, data) in all_entries.items():
            if name == "fsroot/settingstree/matlab/editor/settings.json":
                zout.writestr(name, json.dumps(editor_doc, separators=(",", ":")))
            elif name == "fsroot/settingstree/matlab/editor/displaysettings/settings.json":
                zout.writestr(name, json.dumps(disp_doc, separators=(",", ":")))
            else:
                zout.writestr(info, data)

    # Field-level rollback restores managed keys/files AND preserves post-apply user edits
    restored = adapter.rollback(backup_dir)
    assert restored.status == "ok"
    assert restored.verified is True

    assert _read_group(settings_path, "/settingstree/matlab/appearance") is None
    assert _read_group(settings_path, "/settingstree/matlab/colors") is None
    assert _read_group(settings_path, "/settingstree/matlab/colors/commandwindow") is None
    assert _read_group(settings_path, "/settingstree/matlab/editor/displaysettings/linelimit") is None

    disp_after = _read_group(settings_path, "/settingstree/matlab/editor/displaysettings")
    assert disp_after is not None
    disp_after_names = {item["name"]: item["value"] for item in disp_after["settings"]}
    assert "HighlightCurrentLineColor" not in disp_after_names
    assert disp_after_names["ShowLineNumbers"] == "false"

    editor_after = _read_group(settings_path, "/settingstree/matlab/editor")
    assert editor_after is not None
    assert "post_apply_script.m" in editor_after["settings"][0]["value"]

    manifest_after = _read_manifest_map(settings_path)
    assert "/settingstree/matlab/colors/settings.json" not in manifest_after
    assert manifest_after["/settingstree/matlab/colors/commandwindow"] == ("Folder", "")
    assert manifest_after["/settingstree/matlab/editor/displaysettings/linelimit"] == ("Folder", "")


def test_matlab_adapter_field_rollback_restores_preexisting_custom_values(tmp_path):
    preexisting = {
        "/settingstree/matlab/appearance": {
            "attributes": {"groupName": "appearance", "readonly": False, "validationFcn": {}, "visible": False},
            "path": "/settingstree/matlab/appearance",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": False,
                    "name": "MATLABTheme",
                    "value": '"Dark"',
                }
            ],
        },
        "/settingstree/matlab/colors": {
            "attributes": {"groupName": "colors", "readonly": False, "validationFcn": {}, "visible": True},
            "path": "/settingstree/matlab/colors",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": False,
                    "name": "DesktopColors",
                    "value": '"{\\"dark\\":{\\"BackgroundColor\\":\\"#112233\\"}}"',
                }
            ],
        },
    }
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", extra_groups=preexisting)
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#3B82F6", ["matlab"], plan_id="plan-matlab-002", target_instances={"matlab": adapter.target_instance()})

    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply(plan).status == "partial"
    assert adapter.verify(plan).verified is True
    assert adapter.rollback(backup_dir).verified is True

    appearance = _read_group(settings_path, "/settingstree/matlab/appearance")
    assert appearance is not None
    assert appearance["settings"][0]["value"] == '"Dark"'

    colors = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors is not None
    by_name = {item["name"]: item for item in colors["settings"]}
    assert set(by_name) == {"DesktopColors"}
    assert by_name["DesktopColors"]["value"] == '"{\\"dark\\":{\\"BackgroundColor\\":\\"#112233\\"}}"'


def test_matlab_live_process_write_guard_protects_apply_and_rollback(tmp_path):
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    original_bytes = settings_path.read_bytes()

    running = True
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: running)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-guard-001", target_instances={"matlab": adapter.target_instance()})

    # Read-only detect works while running
    assert adapter.detect().status == "partial"
    # Snapshot and Apply skip without writing while running
    snap_blocked = adapter.snapshot(tmp_path / "b1")
    assert snap_blocked.status == "skipped"
    assert "close MATLAB" in snap_blocked.message
    apply_blocked = adapter.apply(plan)
    assert apply_blocked.status == "skipped"
    assert settings_path.read_bytes() == original_bytes

    # Close MATLAB -> apply succeeds
    running = False
    backup_dir = tmp_path / "b2"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply(plan).status == "partial"
    applied_bytes = settings_path.read_bytes()

    # Re-open MATLAB -> Verify still works (read-only), Rollback fails closed without writing
    running = True
    assert adapter.verify(plan).verified is True
    rb_blocked = adapter.rollback(backup_dir)
    assert rb_blocked.status == "failed"
    assert rb_blocked.verified is False
    assert "close MATLAB" in rb_blocked.message
    assert settings_path.read_bytes() == applied_bytes


def test_matlab_running_during_multi_target_transaction_yields_partial_not_compensation_failure(tmp_path):
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    ag_config = tmp_path / "config.json"
    ag_storage = tmp_path / "app_storage.json"
    ag_config.write_text(json.dumps({"userSettings": {}}), encoding="utf-8")
    ag_storage.write_text(json.dumps({"hubSurfaceBackgroundColor": "#000000"}), encoding="utf-8")

    matlab_adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: True)
    ag_adapter = AntigravityAdapter(config_path=ag_config, storage_path=ag_storage)
    plan = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-matlab-tx-001",
        target_instances={
            "antigravity": ag_adapter.target_instance(),
            "matlab": matlab_adapter.target_instance(),
        },
    )
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"antigravity": ag_adapter, "matlab": matlab_adapter}, store, confirm=True)

    assert record.status == TransactionStatus.PARTIAL
    assert record.results["matlab"][-1]["operation"] == "snapshot"
    assert record.results["matlab"][-1]["status"] == "skipped"


def test_matlab_verify_fails_on_tampered_color_or_manifest(tmp_path):
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-tamper-001", target_instances={"matlab": adapter.target_instance()})
    assert adapter.apply(plan).status == "partial"
    assert adapter.verify(plan).verified is True

    # Tamper MATLABTheme -> Light
    with zipfile.ZipFile(settings_path, "r") as zin:
        entries = {info.filename: (info, zin.read(info.filename)) for info in zin.infolist()}
    doc = json.loads(entries["fsroot/settingstree/matlab/appearance/settings.json"][1].decode("utf-8"))
    doc["settings"][0]["value"] = '"Light"'
    with zipfile.ZipFile(settings_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, (info, data) in entries.items():
            if name == "fsroot/settingstree/matlab/appearance/settings.json":
                zout.writestr(name, json.dumps(doc))
            else:
                zout.writestr(info, data)

    result = adapter.verify(plan)
    assert result.status == "failed"
    assert result.verified is False
    assert "MATLABTheme" in result.message


def test_matlab_discovery_precedence_and_version_gating(tmp_path):
    appdata = tmp_path / "Roaming"
    r2024b = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2024b" / "matlab.mlsettings", release="R2024b")
    assert discover_matlab_instance(appdata=appdata, registry_roots=[])["status"] == "skipped"

    r2025b = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2025b" / "matlab.mlsettings", release="R2025b")
    r2026a = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2026a" / "matlab.mlsettings", release="R2026a")
    newest = discover_matlab_instance(appdata=appdata, registry_roots=[])
    assert newest["status"] == "ok"
    assert newest["release"] == "R2026a"
    assert Path(newest["settings_path"]) == r2026a

    # Explicit prefdir overrides appdata newest
    prefdir_inst = discover_matlab_instance(appdata=appdata, prefdir=r2025b.parent, registry_roots=[])
    assert prefdir_inst["status"] == "ok"
    assert prefdir_inst["release"] == "R2025b"
    assert prefdir_inst["source"] == "prefdir"

    # Explicit settings path overrides prefdir
    explicit_inst = discover_matlab_instance(appdata=appdata, explicit_settings=r2026a, prefdir=r2025b.parent, registry_roots=[])
    assert explicit_inst["status"] == "ok"
    assert explicit_inst["source"] == "explicit"

    # Legacy explicit file skipped
    assert discover_matlab_instance(explicit_settings=r2024b)["status"] == "skipped"

    # Wrong schema skipped
    bad_schema = _make_mlsettings(tmp_path / "bad" / "matlab.mlsettings", release="R2026a", schema="com.mathworks/settings/jsonschema/2-0-0")
    assert discover_matlab_instance(explicit_settings=bad_schema)["status"] == "skipped"

    # Uninitialized registry install skipped
    empty_appdata = tmp_path / "EmptyRoaming"
    uninit = discover_matlab_instance(appdata=empty_appdata, registry_roots=[("R2026a", tmp_path / "MATLAB")])
    assert uninit["status"] == "skipped"
    assert "not been initialized" in uninit["reason"]


def test_matlab_cli_round_trip_and_default_targets(tmp_path, capsys, monkeypatch):
    assert "matlab" in DEFAULT_TARGETS

    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    monkeypatch.setenv("ONE_TONE_MATLAB_SETTINGS", str(settings_path))
    monkeypatch.setattr("one_tone.adapters.matlab.is_matlab_running", lambda: False)

    plans_dir = tmp_path / "plans"
    tx_dir = tmp_path / "transactions"
    state_dir = tmp_path / "state"

    assert main([
        "preview", "#22C55E", "--targets", "matlab",
        "--plans-dir", str(plans_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ]) == 0
    preview = json.loads(capsys.readouterr().out)
    plan_id = preview["plan_id"]
    assert preview["target_instances"]["matlab"]["release"] == "R2026a"
    assert preview["targets"][0]["status"] == "partial"

    loaded_plan = load_plan(plan_id, plans_dir)
    assert loaded_plan.target_instances["matlab"]["settings_path"] == str(settings_path)

    assert main([
        "apply", plan_id, "--confirm",
        "--plans-dir", str(plans_dir),
        "--transactions-dir", str(tx_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ]) == 0
    apply_out = json.loads(capsys.readouterr().out)
    assert apply_out["status"] == "PARTIAL"

    assert main([
        "verify", plan_id,
        "--plans-dir", str(plans_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ]) == 0
    verify_out = json.loads(capsys.readouterr().out)
    assert verify_out["status"] == "partial"
    assert verify_out["targets"][0]["verified"] is True

    assert main([
        "rollback", "--latest",
        "--transactions-dir", str(tx_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ]) == 0
    rb_out = json.loads(capsys.readouterr().out)
    assert rb_out["status"] == "ROLLED_BACK"
    assert _read_group(settings_path, "/settingstree/matlab/colors") is None
