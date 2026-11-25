from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from one_tone.adapters.antigravity import AntigravityAdapter
from one_tone.adapters.matlab import (
    MATLAB_MLSETTINGS_SCHEMA_V1,
    MatlabAdapter,
    _MANIFEST_ENTRY,
    _MANIFEST_NS,
    _SYNTAX_NON_TEXT_KEYS,
    _matlab_mode_colors,
    discover_matlab_instance,
    is_matlab_running,
    probe_matlab_process,
)
from one_tone.cli import DEFAULT_TARGETS, build_target_adapters, main
from one_tone.palette import contrast_ratio, parse_hex_color
from one_tone.plan import PlanIntegrityError, create_plan, load_plan, save_plan
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


def _replace_zip_entry(path: Path, entry_name: str, new_data: bytes | str) -> None:
    raw = new_data.encode("utf-8") if isinstance(new_data, str) else new_data
    with zipfile.ZipFile(path, "r") as zin:
        all_entries = {info.filename: (info, zin.read(info.filename)) for info in zin.infolist()}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        written = False
        for name, (info, data) in all_entries.items():
            if name == entry_name:
                zout.writestr(name, raw)
                written = True
            else:
                zout.writestr(info, data)
        if not written:
            zout.writestr(entry_name, raw)


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
        expected_desktop, expected_syntax = _matlab_mode_colors(plan.palette_for(mode), mode)
        assert desktop[mode] == expected_desktop
        assert syntax[mode] == expected_syntax

    _, light_syntax = _matlab_mode_colors(plan.palette_for("light"), "light")
    assert json.loads(colors_by_name["KeywordColor"]["value"])["mwdata"] == list(parse_hex_color(light_syntax["KeywordColor"]))

    display = _read_group(settings_path, "/settingstree/matlab/editor/displaysettings")
    assert display is not None
    display_by_name = {item["name"]: item for item in display["settings"]}
    assert display_by_name["ShowLineNumbers"]["value"] == "true"
    assert display_by_name["HighlightCurrentLine"]["value"] == "false"
    assert json.loads(display_by_name["HighlightCurrentLineColor"]["value"])["mwdata"] == list(
        parse_hex_color(light_syntax["HighlightCurrentLineColor"])
    )

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

    # Simulate unrelated user edits made AFTER Apply
    editor_doc = _read_group(settings_path, "/settingstree/matlab/editor")
    assert editor_doc is not None
    editor_doc["settings"][0]["value"] = '{"mwdata":["a.m","post_apply_script.m"],"mwsize":[1,2],"mwtype":"cell"}'
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/editor/settings.json", json.dumps(editor_doc, separators=(",", ":")))

    disp_doc = _read_group(settings_path, "/settingstree/matlab/editor/displaysettings")
    assert disp_doc is not None
    for item in disp_doc["settings"]:
        if item["name"] == "ShowLineNumbers":
            item["value"] = "false"
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/editor/displaysettings/settings.json", json.dumps(disp_doc, separators=(",", ":")))

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


def test_matlab_adapter_field_rollback_preserves_post_apply_unmanaged_subkeys_in_color_maps(tmp_path):
    """Issue #4: Rollback must only restore managed subkeys inside DesktopColors/SyntaxHighlightingColors."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-subkey-001", target_instances={"matlab": adapter.target_instance()})

    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply(plan).status == "partial"

    # Simulate user adding unmanaged colors inside DesktopColors & SyntaxHighlightingColors AFTER Apply
    colors_doc = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors_doc is not None
    for item in colors_doc["settings"]:
        if item["name"] == "SyntaxHighlightingColors":
            smap = json.loads(json.loads(item["value"]))
            smap["light"]["CustomCppKeywordColor"] = "#123456"
            item["value"] = json.dumps(json.dumps(smap, separators=(",", ":")), separators=(",", ":"))
        elif item["name"] == "DesktopColors":
            dmap = json.loads(json.loads(item["value"]))
            dmap["dark"]["CustomBannerBackground"] = "#654321"
            item["value"] = json.dumps(json.dumps(dmap, separators=(",", ":")), separators=(",", ":"))
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/colors/settings.json", json.dumps(colors_doc, separators=(",", ":")))

    restored = adapter.rollback(backup_dir)
    assert restored.status == "ok"
    assert restored.verified is True

    colors_after = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors_after is not None
    by_name = {item["name"]: item for item in colors_after["settings"]}
    syntax_after = json.loads(json.loads(by_name["SyntaxHighlightingColors"]["value"]))
    desktop_after = json.loads(json.loads(by_name["DesktopColors"]["value"]))
    assert syntax_after == {"light": {"CustomCppKeywordColor": "#123456"}}
    assert desktop_after == {"dark": {"CustomBannerBackground": "#654321"}}


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
    assert json.loads(json.loads(by_name["DesktopColors"]["value"])) == {"dark": {"BackgroundColor": "#112233"}}


def test_matlab_relative_path_preview_is_frozen_absolute_and_release_pinned(tmp_path, capsys, monkeypatch):
    """Issue #1: Preview with relative path must freeze absolute path and pin release across cwd changes."""
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    settings_a = _make_mlsettings(dir_a / "rel" / "matlab.mlsettings", release="R2026a")
    settings_b = _make_mlsettings(dir_b / "rel" / "matlab.mlsettings", release="R2025b")
    original_b = settings_b.read_bytes()

    monkeypatch.chdir(dir_a)
    monkeypatch.setenv("ONE_TONE_MATLAB_SETTINGS", str(Path("rel") / "matlab.mlsettings"))
    monkeypatch.setattr("one_tone.adapters.matlab.is_matlab_running", lambda: False)

    plans_dir = tmp_path / "plans"
    tx_dir = tmp_path / "transactions"
    state_dir = tmp_path / "state"

    assert main(["preview", "#22C55E", "--targets", "matlab", "--plans-dir", str(plans_dir), "--state-dir", str(state_dir), "--output", "json"]) == 0
    preview = json.loads(capsys.readouterr().out)
    plan_id = preview["plan_id"]
    assert Path(preview["target_instances"]["matlab"]["settings_path"]) == settings_a.resolve()

    # Change working directory to dir_b (which has a different MATLAB release at the same relative path!)
    monkeypatch.chdir(dir_b)
    assert main(["apply", plan_id, "--confirm", "--plans-dir", str(plans_dir), "--transactions-dir", str(tx_dir), "--state-dir", str(state_dir), "--output", "json"]) == 0
    capsys.readouterr()

    assert _read_group(settings_a, "/settingstree/matlab/colors") is not None
    assert settings_b.read_bytes() == original_b

    # Release mismatch at the exact path must be rejected (never overwrite wrong release)
    mismatched_adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_b.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    assert mismatched_adapter.detect().status == "skipped"
    assert "release mismatch" in mismatched_adapter.detect().message

    # Plan loader rejects relative matlab settings_path
    plan = create_plan(
        "#22C55E",
        ["matlab"],
        plan_id="plan-matlab-rel-001",
        target_instances={"matlab": {"status": "ok", "settings_path": "rel/matlab.mlsettings", "release": "R2026a"}},
    )
    save_plan(plan, plans_dir)
    with pytest.raises(PlanIntegrityError, match="absolute"):
        load_plan("plan-matlab-rel-001", plans_dir)


def test_matlab_process_probe_fails_closed_on_enumeration_error(tmp_path, monkeypatch):
    """Issue #2: Win32 process enumeration failures must fail closed and block writes."""
    class FailingKernel32:
        def CreateToolhelp32Snapshot(self, flags, pid):
            return ctypes.c_void_p(-1).value

    monkeypatch.setattr("one_tone.adapters.matlab.sys.platform", "win32")
    monkeypatch.setattr("one_tone.adapters.matlab._create_kernel32", lambda: FailingKernel32())
    status, reason = probe_matlab_process()
    assert status == "unknown"
    assert "CreateToolhelp32Snapshot" in reason
    assert is_matlab_running() is True

    def raising_kernel32():
        raise OSError("access denied")

    monkeypatch.setattr("one_tone.adapters.matlab._create_kernel32", raising_kernel32)
    assert is_matlab_running() is True

    # Adapter also fails closed if injected detector raises
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    original = settings_path.read_bytes()
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-failclosed-001", target_instances={"matlab": adapter.target_instance()})
    assert adapter.snapshot(tmp_path / "b").status == "skipped"
    assert adapter.apply(plan).status == "skipped"
    assert adapter.rollback(tmp_path / "b").status == "failed"
    assert settings_path.read_bytes() == original


def test_matlab_corrupted_manifest_or_group_is_never_overwritten_or_verified(tmp_path):
    """Issue #3: Corrupted manifest or managed settings group must fail closed and preserve original bytes."""
    # Case A: Corrupted settings.json in colors group
    corrupt_group = _make_mlsettings(tmp_path / "corrupt_group" / "R2026a" / "matlab.mlsettings")
    _replace_zip_entry(corrupt_group, "fsroot/settingstree/matlab/colors/settings.json", "{not valid json")
    original_group_bytes = corrupt_group.read_bytes()

    adapter_a = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(corrupt_group.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-corrupt-001")
    assert adapter_a.detect().status == "skipped"
    assert adapter_a.apply(plan).status == "skipped"
    assert adapter_a.verify(plan).status == "failed"
    assert corrupt_group.read_bytes() == original_group_bytes

    # Case B: Invalid manifest root tag
    corrupt_manifest = _make_mlsettings(tmp_path / "corrupt_manifest" / "R2026a" / "matlab.mlsettings")
    _replace_zip_entry(corrupt_manifest, _MANIFEST_ENTRY, "<wrongRoot/>")
    original_manifest_bytes = corrupt_manifest.read_bytes()

    adapter_b = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(corrupt_manifest.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    assert adapter_b.detect().status == "skipped"
    assert adapter_b.apply(plan).status == "skipped"
    assert adapter_b.verify(plan).status == "failed"
    assert corrupt_manifest.read_bytes() == original_manifest_bytes

    # Case C: Archive becomes corrupted after snapshot -> rollback refuses without overwriting
    valid_path = _make_mlsettings(tmp_path / "corrupt_later" / "R2026a" / "matlab.mlsettings")
    adapter_c = MatlabAdapter(settings_path=valid_path, is_running_fn=lambda: False)
    backup_dir = tmp_path / "backup_c"
    assert adapter_c.snapshot(backup_dir).status == "ok"
    _replace_zip_entry(valid_path, "fsroot/settingstree/matlab/editor/displaysettings/settings.json", '{"settings":"not-a-list"}')
    corrupted_bytes = valid_path.read_bytes()
    rb = adapter_c.rollback(backup_dir)
    assert rb.status == "failed"
    assert rb.verified is False
    assert valid_path.read_bytes() == corrupted_bytes

    # Case D: Duplicate ZIP member names rejected without overwriting, and verify reports failed
    import warnings
    dup_path = _make_mlsettings(tmp_path / "dup_zip" / "R2026a" / "matlab.mlsettings")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(dup_path, "a", compression=zipfile.ZIP_DEFLATED) as zapp:
            zapp.writestr("fsroot/schema.json", "com.mathworks/settings/jsonschema/1-1-0")
    dup_bytes = dup_path.read_bytes()
    adapter_d = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(dup_path.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    assert adapter_d.detect().status == "skipped"
    assert adapter_d.apply(plan).status == "skipped"
    assert adapter_d.verify(plan).status == "failed"
    assert dup_path.read_bytes() == dup_bytes


def test_matlab_legacy_snapshot_without_kind_still_preserves_post_apply_unmanaged_colors(tmp_path):
    """Legacy df75da8 snapshots (without kind/modes) must still roll back at subkey level."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-legacy-snap-001", target_instances={"matlab": adapter.target_instance()})

    backup_dir = tmp_path / "backup"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply(plan).status == "partial"

    # Strip kind/modes from saved matlab-state.json to match legacy df75da8 snapshot layout
    state_path = backup_dir / "matlab-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for key in ("DesktopColors", "SyntaxHighlightingColors"):
        state["groups"]["/settingstree/matlab/colors"]["entries"][key] = {"existed": False}
    state_path.write_text(json.dumps(state), encoding="utf-8")

    # Add unmanaged color after Apply
    colors_doc = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors_doc is not None
    for item in colors_doc["settings"]:
        if item["name"] == "SyntaxHighlightingColors":
            smap = json.loads(json.loads(item["value"]))
            smap["light"]["CustomUnmanagedColor"] = "#abcdef"
            item["value"] = json.dumps(json.dumps(smap, separators=(",", ":")), separators=(",", ":"))
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/colors/settings.json", json.dumps(colors_doc, separators=(",", ":")))

    rb = adapter.rollback(backup_dir)
    assert rb.status == "ok"
    assert rb.verified is True

    colors_after = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors_after is not None
    by_name = {item["name"]: item for item in colors_after["settings"]}
    assert json.loads(json.loads(by_name["SyntaxHighlightingColors"]["value"])) == {"light": {"CustomUnmanagedColor": "#abcdef"}}


def test_matlab_pre_replace_guard_aborts_if_matlab_starts_during_zip_build(tmp_path):
    """If MATLAB starts between entry check and os.replace, neither apply nor rollback replaces the file."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    original_bytes = settings_path.read_bytes()

    # Apply race: 1st check (entry) False, 2nd check (pre-replace) True
    apply_calls = {"n": 0}

    def starts_mid_apply() -> bool:
        apply_calls["n"] += 1
        return apply_calls["n"] >= 2

    adapter_apply = MatlabAdapter(settings_path=settings_path, is_running_fn=starts_mid_apply)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-toctou-001", target_instances={"matlab": adapter_apply.target_instance()})
    res_apply = adapter_apply.apply(plan)
    assert res_apply.status == "skipped"
    assert res_apply.changed is False
    assert settings_path.read_bytes() == original_bytes
    assert not list(settings_path.parent.glob("*.tmp"))

    # Perform clean snapshot & apply, then trigger race during rollback
    clean_adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    backup_dir = tmp_path / "backup"
    assert clean_adapter.snapshot(backup_dir).status == "ok"
    assert clean_adapter.apply(plan).status == "partial"
    applied_bytes = settings_path.read_bytes()

    rb_calls = {"n": 0}

    def starts_mid_rollback() -> bool:
        rb_calls["n"] += 1
        return rb_calls["n"] >= 2

    adapter_rb = MatlabAdapter(settings_path=settings_path, is_running_fn=starts_mid_rollback)
    res_rb = adapter_rb.rollback(backup_dir)
    assert res_rb.status == "failed"
    assert res_rb.changed is False
    assert settings_path.read_bytes() == applied_bytes
    assert not list(settings_path.parent.glob("*.tmp"))


def test_rollback_latest_skips_unmodified_failed_transaction(tmp_path):
    """A zero-modification failed transaction (e.g. MATLAB running) must not block rollback --latest."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    running = False
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: running)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-latest-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")

    tx1 = apply_plan(plan, {"matlab": adapter}, store, confirm=True)
    assert tx1.status == TransactionStatus.PARTIAL

    running = True
    tx2 = apply_plan(plan, {"matlab": adapter}, store, confirm=True)
    assert tx2.status == TransactionStatus.FAILED

    assert store.latest_transaction_id() == tx1.id
    running = False
    restored = store.rollback(store.latest_transaction_id(), {"matlab": adapter})
    assert restored.id == tx1.id
    assert restored.status == TransactionStatus.ROLLED_BACK


def test_old_v7_plan_is_rejected_for_v8_appearance_policy(tmp_path):
    """Old v7 plans must be recreated through Preview after MATLAB contrast policy bump."""
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-v7-001")
    path = save_plan(plan, tmp_path / "plans")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["appearance_policy"]["revision"] = "2026-11-22.v7"
    payload["appearance_policy"].pop("matlab.contrast_guard", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlanIntegrityError, match="appearance policy"):
        load_plan("plan-matlab-v7-001", tmp_path / "plans")


def test_matlab_discovery_skips_mismatched_release_in_newer_folder_and_picks_valid_release(tmp_path):
    """An R2025a archive inside R2026a/ must not pair with R2026a root or shadow valid R2025b."""
    appdata = tmp_path / "Roaming"
    _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2026a" / "matlab.mlsettings", release="R2025a")
    valid_r2025b = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2025b" / "matlab.mlsettings", release="R2025b")

    discovered = discover_matlab_instance(
        appdata=appdata,
        registry_roots=[("R2026a", tmp_path / "MATLAB_R2026a"), ("R2025b", tmp_path / "MATLAB_R2025b")],
    )
    assert discovered["status"] == "ok"
    assert discovered["release"] == "R2025b"
    assert Path(discovered["settings_path"]) == valid_r2025b.resolve()
    assert Path(discovered["matlab_root"]) == (tmp_path / "MATLAB_R2025b").resolve()


def test_rollback_skips_already_restored_targets_on_retry_and_excludes_auto_compensated_tx(tmp_path):
    """P1: Retry rollback must not re-rollback already-restored targets, and --latest skips auto-compensated tx."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    ag_config = tmp_path / "ag_config.json"
    ag_storage = tmp_path / "ag_storage.json"
    ag_config.write_text(json.dumps({"userSettings": {"themeMode": "THEME_MODE_DARK"}}), encoding="utf-8")
    ag_storage.write_text(json.dumps({"hubSurfaceBackgroundColor": "#000000"}), encoding="utf-8")

    running = False
    matlab_adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: running)
    ag_adapter = AntigravityAdapter(config_path=ag_config, storage_path=ag_storage)
    plan = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-retry-rb-001",
        target_instances={"antigravity": ag_adapter.target_instance(), "matlab": matlab_adapter.target_instance()},
    )
    store = TransactionStore(tmp_path / "transactions")
    tx1 = apply_plan(plan, {"antigravity": ag_adapter, "matlab": matlab_adapter}, store, confirm=True)
    assert tx1.status == TransactionStatus.PARTIAL

    # First rollback attempt: Antigravity restores OK, MATLAB blocked by live process -> FAILED
    running = True
    rb1 = store.rollback(tx1.id, {"antigravity": ag_adapter, "matlab": matlab_adapter})
    assert rb1.status == TransactionStatus.FAILED
    assert store.latest_transaction_id() == tx1.id

    # User edits Antigravity between rollback attempts
    ag_data = json.loads(ag_config.read_text(encoding="utf-8"))
    ag_data["userSettings"]["postRollbackEdit"] = "keep-me"
    ag_config.write_text(json.dumps(ag_data), encoding="utf-8")

    # Second rollback attempt after closing MATLAB: Antigravity must NOT be overwritten; MATLAB restores cleanly
    running = False
    rb2 = store.rollback(tx1.id, {"antigravity": ag_adapter, "matlab": matlab_adapter})
    assert rb2.status == TransactionStatus.ROLLED_BACK
    assert rb2.results["antigravity"][-1]["status"] == "skipped"
    assert json.loads(ag_config.read_text(encoding="utf-8"))["userSettings"]["postRollbackEdit"] == "keep-me"
    assert _read_group(settings_path, "/settingstree/matlab/colors") is None

    # Auto-compensated failed transaction must NOT be selected by latest_transaction_id()
    tx_good = apply_plan(plan, {"antigravity": ag_adapter, "matlab": matlab_adapter}, store, confirm=True)

    class FailingVerifyMatlab(MatlabAdapter):
        def verify(self, plan):
            return super().verify(plan).__class__(self.target, "failed", False, False, "forced verify failure")

    tx_auto_rb = apply_plan(
        create_plan("#3B82F6", ["matlab"], plan_id="plan-autorb-001", target_instances={"matlab": matlab_adapter.target_instance()}),
        {"matlab": FailingVerifyMatlab(settings_path=settings_path, is_running_fn=lambda: False)},
        store,
        confirm=True,
    )
    assert tx_auto_rb.status == TransactionStatus.FAILED
    assert store.latest_transaction_id() == tx_good.id


def test_matlab_rollback_rejects_mismatched_adapter_path_for_same_release(tmp_path):
    """P2: Rollback must use snapshot path and reject an adapter bound to a different archive."""
    path_a = _make_mlsettings(tmp_path / "a" / "R2026a" / "matlab.mlsettings", release="R2026a")
    path_b = _make_mlsettings(tmp_path / "b" / "R2026a" / "matlab.mlsettings", release="R2026a")
    original_b = path_b.read_bytes()

    adapter_a = MatlabAdapter(settings_path=path_a, is_running_fn=lambda: False)
    adapter_b = MatlabAdapter(settings_path=path_b, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-rb-mismatch-001", target_instances={"matlab": adapter_a.target_instance()})
    store = TransactionStore(tmp_path / "transactions")
    tx = apply_plan(plan, {"matlab": adapter_a}, store, confirm=True)
    assert tx.status == TransactionStatus.PARTIAL

    rb = store.rollback(tx.id, {"matlab": adapter_b})
    assert rb.status == TransactionStatus.FAILED
    assert "does not match snapshot path" in rb.results["matlab"][-1]["message"]
    assert path_b.read_bytes() == original_b


def test_matlab_rejects_is_vector_true_color_map_without_overwriting(tmp_path):
    """P1: DesktopColors with isVector=true must fail validation and never be wiped by apply."""
    bad_group = {
        "/settingstree/matlab/colors": {
            "attributes": {"groupName": "colors", "readonly": False, "validationFcn": {}, "visible": True},
            "path": "/settingstree/matlab/colors",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                    "hasValue": True,
                    "isUserDefined": False,
                    "isVector": True,
                    "name": "DesktopColors",
                    "value": '"{\\"dark\\":{\\"CustomKey\\":\\"#123456\\"}}"',
                }
            ],
        }
    }
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", extra_groups=bad_group)
    original_bytes = settings_path.read_bytes()

    adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_path.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-bad-vec-001")
    assert adapter.detect().status == "skipped"
    assert "isVector" in adapter.detect().message
    assert adapter.apply(plan).status == "skipped"
    assert adapter.verify(plan).status == "failed"
    assert settings_path.read_bytes() == original_bytes


def test_matlab_rejects_invalid_release_in_archive_xml_and_in_plan(tmp_path):
    """P2: Invalid <release> in XML must not fall back to folder name, and invalid release in Plan must be rejected."""
    bad_rel_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", release="INVALID_REL")
    assert discover_matlab_instance(explicit_settings=bad_rel_path)["status"] == "skipped"
    assert "Invalid MATLAB release" in discover_matlab_instance(explicit_settings=bad_rel_path)["reason"]

    empty_rel_path = _make_mlsettings(tmp_path / "empty" / "R2026a" / "matlab.mlsettings", release="")
    assert discover_matlab_instance(explicit_settings=empty_rel_path)["status"] == "skipped"

    valid_path = _make_mlsettings(tmp_path / "valid" / "R2026a" / "matlab.mlsettings", release="R2026a")
    plans_dir = tmp_path / "plans"
    bad_plan = create_plan(
        "#22C55E",
        ["matlab"],
        plan_id="plan-bad-rel-001",
        target_instances={"matlab": {"status": "ok", "settings_path": str(valid_path.resolve()), "release": "INVALID"}},
    )
    save_plan(bad_plan, plans_dir)
    with pytest.raises(PlanIntegrityError, match="release"):
        load_plan("plan-bad-rel-001", plans_dir)

    bad_adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(valid_path.resolve()), "release": "INVALID"},
        is_running_fn=lambda: False,
    )
    assert bad_adapter.detect().status == "skipped"
    assert bad_adapter.apply(bad_plan).status == "skipped"


def test_matlab_process_probe_fails_closed_when_process32next_returns_false_with_error_zero(monkeypatch):
    """P2: Process32NextW returning FALSE with GetLastError()==0 (not ERROR_NO_MORE_FILES) must fail closed."""
    class ZeroErrorNextKernel32:
        def CreateToolhelp32Snapshot(self, flags, pid):
            return 1234

        def Process32FirstW(self, snapshot, entry_ptr):
            ctypes.set_last_error(0)
            return 1

        def Process32NextW(self, snapshot, entry_ptr):
            ctypes.set_last_error(0)
            return 0

        def CloseHandle(self, handle):
            return 1

    monkeypatch.setattr("one_tone.adapters.matlab.sys.platform", "win32")
    monkeypatch.setattr("one_tone.adapters.matlab._create_kernel32", lambda: ZeroErrorNextKernel32())
    status, reason = probe_matlab_process()
    assert status == "unknown"
    assert "Process32NextW" in reason
    assert is_matlab_running() is True


def test_matlab_live_process_write_guard_protects_apply_and_rollback(tmp_path):
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    original_bytes = settings_path.read_bytes()

    running = True
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: running)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-guard-001", target_instances={"matlab": adapter.target_instance()})

    assert adapter.detect().status == "partial"
    snap_blocked = adapter.snapshot(tmp_path / "b1")
    assert snap_blocked.status == "skipped"
    assert "close MATLAB" in snap_blocked.message
    apply_blocked = adapter.apply(plan)
    assert apply_blocked.status == "skipped"
    assert settings_path.read_bytes() == original_bytes

    running = False
    backup_dir = tmp_path / "b2"
    assert adapter.snapshot(backup_dir).status == "ok"
    assert adapter.apply(plan).status == "partial"
    applied_bytes = settings_path.read_bytes()

    running = True
    assert adapter.verify(plan).verified is True
    rb_blocked = adapter.rollback(backup_dir)
    assert rb_blocked.status == "failed"
    assert rb_blocked.verified is False
    assert "close MATLAB" in rb_blocked.message
    assert settings_path.read_bytes() == applied_bytes


def test_matlab_skipped_after_snapshot_or_uninstalled_does_not_fail_multi_target_tx_or_rollback(tmp_path):
    """Issue #5: MATLAB starting after snapshot or missing entirely must not fail multi-target apply or rollback."""
    # Case A: MATLAB starts AFTER snapshot() and BEFORE apply()
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    ag_config = tmp_path / "a_config.json"
    ag_storage = tmp_path / "a_storage.json"
    ag_config.write_text(json.dumps({"userSettings": {}}), encoding="utf-8")
    ag_storage.write_text(json.dumps({"hubSurfaceBackgroundColor": "#000000"}), encoding="utf-8")

    calls = {"count": 0}

    def starts_after_snapshot() -> bool:
        calls["count"] += 1
        return calls["count"] >= 2  # False during snapshot, True during apply & rollback

    matlab_adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=starts_after_snapshot)
    ag_adapter = AntigravityAdapter(config_path=ag_config, storage_path=ag_storage)
    plan_a = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-matlab-race-001",
        target_instances={"antigravity": ag_adapter.target_instance(), "matlab": matlab_adapter.target_instance()},
    )
    store = TransactionStore(tmp_path / "transactions_a")
    record_a = apply_plan(plan_a, {"antigravity": ag_adapter, "matlab": matlab_adapter}, store, confirm=True)
    assert record_a.status == TransactionStatus.PARTIAL
    assert [op["operation"] for op in record_a.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert record_a.results["matlab"][-1]["status"] == "skipped"

    rb_a = store.rollback(record_a.id, {"antigravity": ag_adapter, "matlab": matlab_adapter})
    assert rb_a.status == TransactionStatus.ROLLED_BACK
    assert rb_a.results["matlab"][-1]["status"] == "skipped"

    # Case B: MATLAB not installed on machine
    missing_matlab = MatlabAdapter(settings_path=tmp_path / "missing" / "matlab.mlsettings", is_running_fn=lambda: False)
    plan_b = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-matlab-missing-001",
        target_instances={"antigravity": ag_adapter.target_instance(), "matlab": missing_matlab.target_instance()},
    )
    store_b = TransactionStore(tmp_path / "transactions_b")
    record_b = apply_plan(plan_b, {"antigravity": ag_adapter, "matlab": missing_matlab}, store_b, confirm=True)
    assert record_b.status == TransactionStatus.PARTIAL

    rb_b = store_b.rollback(record_b.id, {"antigravity": ag_adapter, "matlab": missing_matlab})
    assert rb_b.status == TransactionStatus.ROLLED_BACK
    assert rb_b.results["matlab"][-1]["status"] == "skipped"


def test_matlab_verify_rejects_has_value_false_and_tampered_values(tmp_path):
    """Issue #6: Verify must fail when hasValue is False even if the value string still matches."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-hasval-001", target_instances={"matlab": adapter.target_instance()})
    assert adapter.apply(plan).status == "partial"
    assert adapter.verify(plan).verified is True

    # Mark MATLABTheme hasValue=False while keeping value="System"
    app_doc = _read_group(settings_path, "/settingstree/matlab/appearance")
    assert app_doc is not None
    app_doc["settings"][0]["hasValue"] = False
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/appearance/settings.json", json.dumps(app_doc, separators=(",", ":")))

    result = adapter.verify(plan)
    assert result.status == "failed"
    assert result.verified is False
    assert "MATLABTheme" in result.message

    # Restore MATLABTheme, then mark KeywordColor hasValue=False
    app_doc["settings"][0]["hasValue"] = True
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/appearance/settings.json", json.dumps(app_doc, separators=(",", ":")))
    colors_doc = _read_group(settings_path, "/settingstree/matlab/colors")
    assert colors_doc is not None
    for item in colors_doc["settings"]:
        if item["name"] == "KeywordColor":
            item["hasValue"] = False
    _replace_zip_entry(settings_path, "fsroot/settingstree/matlab/colors/settings.json", json.dumps(colors_doc, separators=(",", ":")))

    result2 = adapter.verify(plan)
    assert result2.status == "failed"
    assert result2.verified is False
    assert "KeywordColor" in result2.message


def test_matlab_generated_colors_meet_wcag_contrast_on_all_managed_backgrounds():
    """Issue #7: Every syntax text color must achieve >=4.5:1 (and body >=7:1) on surface and highlight backgrounds."""
    for seed in ("#22C55E", "#3B82F6", "#7C3AED", "#EF4444", "#FFD700", "#06B6D4", "#111827"):
        plan = create_plan(seed, ["matlab"], plan_id=f"plan-matlab-wcag-{seed.lstrip('#').lower()}")
        for mode in ("light", "dark"):
            desktop, syntax = _matlab_mode_colors(plan.palette_for(mode), mode)
            bg_surface = desktop["BackgroundColor"]
            bg_cur = syntax["HighlightCurrentLineColor"]
            bg_auto = syntax["AutofixHighlightColor"]
            bg_var = syntax["VariableHighlightColor"]

            assert contrast_ratio(desktop["ForegroundColor"], bg_surface) >= 7.0
            assert contrast_ratio(desktop["ForegroundColor"], bg_cur) >= 7.0
            assert contrast_ratio(desktop["ForegroundColor"], bg_auto) >= 4.5
            assert contrast_ratio(desktop["ForegroundColor"], bg_var) >= 4.5

            for key, color in syntax.items():
                if key in _SYNTAX_NON_TEXT_KEYS:
                    continue
                for bg in (bg_surface, bg_cur, bg_auto, bg_var):
                    assert contrast_ratio(color, bg) >= 4.5, f"{seed} {mode} {key}={color} on {bg}"


def test_matlab_discovery_precedence_and_version_gating(tmp_path):
    appdata = tmp_path / "Roaming"
    r2024b = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2024b" / "matlab.mlsettings", release="R2024b")
    assert discover_matlab_instance(appdata=appdata, registry_roots=[])["status"] == "skipped"

    r2025b = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2025b" / "matlab.mlsettings", release="R2025b")
    r2026a = _make_mlsettings(appdata / "MathWorks" / "MATLAB" / "R2026a" / "matlab.mlsettings", release="R2026a")
    newest = discover_matlab_instance(appdata=appdata, registry_roots=[])
    assert newest["status"] == "ok"
    assert newest["release"] == "R2026a"
    assert Path(newest["settings_path"]) == r2026a.resolve()

    prefdir_inst = discover_matlab_instance(appdata=appdata, prefdir=r2025b.parent, registry_roots=[])
    assert prefdir_inst["status"] == "ok"
    assert prefdir_inst["release"] == "R2025b"
    assert prefdir_inst["source"] == "prefdir"

    explicit_inst = discover_matlab_instance(appdata=appdata, explicit_settings=r2026a, prefdir=r2025b.parent, registry_roots=[])
    assert explicit_inst["status"] == "ok"
    assert explicit_inst["source"] == "explicit"

    assert discover_matlab_instance(explicit_settings=r2024b)["status"] == "skipped"

    bad_schema = _make_mlsettings(tmp_path / "bad" / "matlab.mlsettings", release="R2026a", schema="com.mathworks/settings/jsonschema/2-0-0")
    assert discover_matlab_instance(explicit_settings=bad_schema)["status"] == "skipped"

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
    assert loaded_plan.target_instances["matlab"]["settings_path"] == str(settings_path.resolve())

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


def test_matlab_rollback_rejects_symlink_or_junction_redirected_snapshot_path(tmp_path, capsys, monkeypatch):
    """Round 4 P1: Replacing A's frozen path with a symlink/junction to same-release B must abort rollback."""
    path_a = _make_mlsettings(tmp_path / "a" / "R2026a" / "matlab.mlsettings", release="R2026a")
    path_b = _make_mlsettings(tmp_path / "b" / "R2026a" / "matlab.mlsettings", release="R2026a")
    original_b = path_b.read_bytes()

    monkeypatch.setenv("ONE_TONE_MATLAB_SETTINGS", str(path_a))
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
    plan_id = json.loads(capsys.readouterr().out)["plan_id"]

    assert main([
        "apply", plan_id, "--confirm",
        "--plans-dir", str(plans_dir),
        "--transactions-dir", str(tx_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PARTIAL"

    # Redirect path_a to path_b via a file symlink (or NTFS directory junction if file symlink privilege is unavailable)
    path_a.unlink()
    try:
        path_a.symlink_to(path_b)
    except OSError:
        shutil.rmtree(path_a.parent)
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(path_a.parent), str(path_b.parent)],
            check=True,
            capture_output=True,
        )

    rc = main([
        "rollback", "--latest",
        "--transactions-dir", str(tx_dir),
        "--state-dir", str(state_dir),
        "--output", "json",
    ])
    rb_out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert rb_out["status"] == "FAILED"
    assert "redirected" in rb_out["targets"][0]["message"]
    assert path_b.read_bytes() == original_b


def test_matlab_rejects_non_boolean_has_value_without_wiping_custom_colors(tmp_path):
    """Round 4 P1: Non-boolean hasValue (e.g. 'true') must fail validation and never wipe unmanaged colors."""
    bad_group = {
        "/settingstree/matlab/colors": {
            "attributes": {"groupName": "colors", "readonly": False, "validationFcn": {}, "visible": True},
            "path": "/settingstree/matlab/colors",
            "settings": [
                {
                    "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                    "hasValue": "true",
                    "isUserDefined": False,
                    "isVector": False,
                    "name": "DesktopColors",
                    "value": '"{\\"dark\\":{\\"CustomKey\\":\\"#123456\\"}}"',
                }
            ],
        }
    }
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", extra_groups=bad_group)
    original_bytes = settings_path.read_bytes()

    adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_path.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-bad-hasval-001")
    detect_res = adapter.detect()
    assert detect_res.status == "skipped"
    assert "hasValue" in detect_res.message
    assert adapter.snapshot(tmp_path / "snap").status == "skipped"
    apply_res = adapter.apply(plan)
    assert apply_res.status == "skipped"
    assert apply_res.changed is False
    assert adapter.verify(plan).status == "failed"
    assert settings_path.read_bytes() == original_bytes


def test_matlab_plan_missing_frozen_instance_is_rejected_by_load_plan_and_cli_builder(tmp_path, monkeypatch):
    """Round 4 P2: Valid-hash Plan omitting target_instances['matlab'] must fail load_plan and never fall back to live discovery."""
    valid_settings = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", release="R2026a")
    original_bytes = valid_settings.read_bytes()
    monkeypatch.setenv("ONE_TONE_MATLAB_SETTINGS", str(valid_settings))
    monkeypatch.setattr("one_tone.adapters.matlab.is_matlab_running", lambda: False)

    plans_dir = tmp_path / "plans"
    missing_inst_plan = create_plan("#22C55E", ["matlab"], plan_id="plan-missing-inst-001", target_instances={})
    save_plan(missing_inst_plan, plans_dir)

    with pytest.raises(PlanIntegrityError, match="missing frozen matlab"):
        load_plan("plan-missing-inst-001", plans_dir)

    adapters = build_target_adapters(("matlab",), tmp_path / "state", target_instances={})
    matlab_adapter = adapters["matlab"]
    assert matlab_adapter.detect().status == "skipped"
    assert "missing from Plan" in matlab_adapter.detect().message
    assert matlab_adapter.apply(missing_inst_plan).status == "skipped"
    assert valid_settings.read_bytes() == original_bytes


def test_matlab_apply_uses_single_read_and_aborts_if_archive_swapped_before_replace(tmp_path):
    """Round 4 P2: Apply must validate and build from one read and abort if the archive is swapped before replace."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", release="R2026a")
    r2025b_source = _make_mlsettings(tmp_path / "other" / "R2025b" / "matlab.mlsettings", release="R2025b")
    r2025b_bytes = r2025b_source.read_bytes()

    swapped = {"done": False}

    def swap_after_initial_read() -> bool:
        if not swapped["done"]:
            swapped["done"] = True
            # Simulate concurrent replacement of R2026a archive with R2025b right after initial read/validation
            settings_path.write_bytes(r2025b_bytes)
        return False

    adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_path.resolve()), "release": "R2026a"},
        is_running_fn=swap_after_initial_read,
    )
    plan = create_plan(
        "#22C55E",
        ["matlab"],
        plan_id="plan-single-read-001",
        target_instances={"matlab": {"status": "ok", "settings_path": str(settings_path.resolve()), "release": "R2026a"}},
    )

    result = adapter.apply(plan)
    assert result.status == "failed"
    assert result.changed is False
    assert "changed concurrently" in result.message
    assert settings_path.read_bytes() == r2025b_bytes
    assert not list(settings_path.parent.glob("*.tmp"))


def _make_theme_mlsettings(path: Path, theme: str) -> Path:
    return _make_mlsettings(
        path,
        release="R2026a",
        extra_groups={
            "/settingstree/matlab/appearance": {
                "attributes": {"groupName": "appearance", "readonly": False, "validationFcn": {}, "visible": True},
                "path": "/settingstree/matlab/appearance",
                "settings": [
                    {
                        "attributes": {"readonly": False, "runtimeDefaultFcn": {}, "settingValueValidator": {}, "validationFcn": {}, "visible": False},
                        "hasValue": True,
                        "isUserDefined": False,
                        "isVector": False,
                        "name": "MATLABTheme",
                        "value": json.dumps(theme),
                    }
                ],
            }
        },
    )


def test_matlab_apply_pre_write_abort_skips_auto_rollback_and_preserves_concurrent_edit(tmp_path):
    """Round 5 P1: Pre-write apply abort must NOT run auto_rollback or clobber concurrent edits."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    light_bytes = _make_theme_mlsettings(tmp_path / "other" / "R2026a" / "matlab.mlsettings", "Light").read_bytes()

    # Case A: Single-target tx where file changes from Dark -> Light after apply's initial read
    calls = {"count": 0}

    def edit_during_apply_entry() -> bool:
        calls["count"] += 1
        if calls["count"] == 2:  # 1=snapshot, 2=apply entry (after initial read)
            settings_path.write_bytes(light_bytes)
        return False

    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=edit_during_apply_entry)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-prewrite-abort-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions_single")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)

    assert record.status == TransactionStatus.FAILED
    assert [op["operation"] for op in record.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert record.results["matlab"][-1]["status"] == "failed"
    assert record.results["matlab"][-1]["changed"] is False
    assert record.results["matlab"][-1]["metadata"]["aborted_before_write"] is True
    assert settings_path.read_bytes() == light_bytes
    with pytest.raises(FileNotFoundError):
        store.latest_transaction_id()

    # Case B: Multi-target tx (Antigravity succeeds, MATLAB aborts before write) -> manual rollback skips MATLAB
    settings_b = _make_theme_mlsettings(tmp_path / "multi" / "R2026a" / "matlab.mlsettings", "Dark")
    ag_config = tmp_path / "ag_config.json"
    ag_storage = tmp_path / "ag_storage.json"
    ag_config.write_text(json.dumps({"userSettings": {"themeMode": "THEME_MODE_DARK"}}), encoding="utf-8")
    ag_storage.write_text(json.dumps({"hubSurfaceBackgroundColor": "#000000"}), encoding="utf-8")

    calls_b = {"count": 0}

    def edit_during_apply_b() -> bool:
        calls_b["count"] += 1
        if calls_b["count"] == 2:
            settings_b.write_bytes(light_bytes)
        return False

    ag_adapter = AntigravityAdapter(config_path=ag_config, storage_path=ag_storage)
    matlab_b = MatlabAdapter(settings_path=settings_b, is_running_fn=edit_during_apply_b)
    plan_b = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-prewrite-multi-001",
        target_instances={"antigravity": ag_adapter.target_instance(), "matlab": matlab_b.target_instance()},
    )
    store_b = TransactionStore(tmp_path / "transactions_multi")
    rec_b = apply_plan(plan_b, {"antigravity": ag_adapter, "matlab": matlab_b}, store_b, confirm=True)
    assert rec_b.status == TransactionStatus.PARTIAL
    assert [op["operation"] for op in rec_b.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert settings_b.read_bytes() == light_bytes

    rb_b = store_b.rollback(rec_b.id, {"antigravity": ag_adapter, "matlab": matlab_b})
    assert rb_b.status == TransactionStatus.ROLLED_BACK
    assert rb_b.results["matlab"][-1]["status"] == "skipped"
    assert settings_b.read_bytes() == light_bytes


def test_matlab_pre_replace_guard_rechecks_bytes_after_final_process_enumeration(tmp_path):
    """Round 5 P2: Archive mutation during the final process check must still abort before os.replace."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    light_bytes = _make_theme_mlsettings(tmp_path / "other" / "R2026a" / "matlab.mlsettings", "Light").read_bytes()

    calls = {"count": 0}

    def edit_during_final_process_check() -> bool:
        calls["count"] += 1
        # 1=snapshot, 2=apply entry, 3=final pre-replace process enumeration
        if calls["count"] == 3:
            settings_path.write_bytes(light_bytes)
        return False

    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=edit_during_final_process_check)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-final-enum-race-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)

    assert calls["count"] == 3
    assert record.status == TransactionStatus.FAILED
    assert [op["operation"] for op in record.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert "changed concurrently" in record.results["matlab"][-1]["message"]
    assert settings_path.read_bytes() == light_bytes
    assert not list(settings_path.parent.glob("*.tmp"))


def test_matlab_apply_aborts_if_archive_changes_between_snapshot_and_apply(tmp_path):
    """Round 5 P2: Archive changed after snapshot() and before apply() must abort apply without rollback."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    light_bytes = _make_theme_mlsettings(tmp_path / "other" / "R2026a" / "matlab.mlsettings", "Light").read_bytes()

    class MutateAfterSnapshotAdapter(MatlabAdapter):
        def snapshot(self, backup_dir: Path):
            result = super().snapshot(backup_dir)
            settings_path.write_bytes(light_bytes)
            return result

    adapter = MutateAfterSnapshotAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-snap-apply-drift-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)

    assert record.status == TransactionStatus.FAILED
    assert [op["operation"] for op in record.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert record.results["matlab"][-1]["status"] == "failed"
    assert record.results["matlab"][-1]["changed"] is False
    assert "changed since snapshot" in record.results["matlab"][-1]["message"]
    assert settings_path.read_bytes() == light_bytes


def test_matlab_post_replace_report_error_marks_changed_true_and_triggers_auto_rollback(tmp_path):
    """Round 6 P1: Error after os.replace completes must record changed=True and allow auto/manual rollback."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")

    class PostWriteReportFailureAdapter(MatlabAdapter):
        def _metadata(self, plan=None, status="supported", *, target_instance=None):
            if status == "applied":
                raise PermissionError("simulated post-replace reporting failure")
            return super()._metadata(plan, status, target_instance=target_instance)

    # Case A: Auto-rollback succeeds immediately and restores Dark theme
    adapter = PostWriteReportFailureAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-postwrite-err-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions_a")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)

    assert record.status == TransactionStatus.FAILED
    ops = [op["operation"] for op in record.results["matlab"]]
    assert ops == ["detect", "snapshot", "apply", "auto_rollback"]
    apply_op = record.results["matlab"][2]
    assert apply_op["status"] == "failed"
    assert apply_op["changed"] is True
    assert not apply_op["metadata"].get("aborted_before_write")
    assert record.results["matlab"][3]["status"] == "ok"
    app_doc = _read_group(settings_path, "/settingstree/matlab/appearance")
    assert app_doc is not None
    assert json.loads(app_doc["settings"][0]["value"]) == "Dark"

    # Case B: Auto-rollback blocked by live MATLAB -> tx stays selectable by --latest and restorable once closed
    settings_b = _make_theme_mlsettings(tmp_path / "b" / "R2026a" / "matlab.mlsettings", "Dark")
    running_state = {"calls": 0, "block": False}

    def block_during_rollback() -> bool:
        running_state["calls"] += 1
        # 1=snapshot, 2=apply entry, 3=apply pre-replace -> False; 4=auto_rollback -> True while blocked
        return running_state["block"] or running_state["calls"] >= 4

    adapter_b = PostWriteReportFailureAdapter(settings_path=settings_b, is_running_fn=block_during_rollback)
    plan_b = create_plan("#22C55E", ["matlab"], plan_id="plan-postwrite-err-002", target_instances={"matlab": adapter_b.target_instance()})
    store_b = TransactionStore(tmp_path / "transactions_b")
    rec_b = apply_plan(plan_b, {"matlab": adapter_b}, store_b, confirm=True)
    assert rec_b.status == TransactionStatus.FAILED
    assert rec_b.results["matlab"][-1]["operation"] == "auto_rollback"
    assert rec_b.results["matlab"][-1]["status"] == "failed"
    # Disk still holds applied "System" theme, and --latest MUST select rec_b for manual recovery
    app_b = _read_group(settings_b, "/settingstree/matlab/appearance")
    assert app_b is not None and json.loads(app_b["settings"][0]["value"]) == "System"
    assert store_b.latest_transaction_id() == rec_b.id

    clean_adapter_b = MatlabAdapter(settings_path=settings_b, is_running_fn=lambda: False)
    rb_b = store_b.rollback(rec_b.id, {"matlab": clean_adapter_b})
    assert rb_b.status == TransactionStatus.ROLLED_BACK
    app_b_after = _read_group(settings_b, "/settingstree/matlab/appearance")
    assert app_b_after is not None and json.loads(app_b_after["settings"][0]["value"]) == "Dark"


def test_matlab_snapshot_failure_does_not_fail_multi_target_rollback(tmp_path):
    """Round 6 P2: A target whose snapshot failed (and never ran apply) must be skipped cleanly on rollback."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    original_matlab = settings_path.read_bytes()
    ag_config = tmp_path / "ag_config.json"
    ag_storage = tmp_path / "ag_storage.json"
    original_ag_config = json.dumps({"userSettings": {"themeMode": "THEME_MODE_DARK"}})
    original_ag_storage = json.dumps({"hubSurfaceBackgroundColor": "#000000"})
    ag_config.write_text(original_ag_config, encoding="utf-8")
    ag_storage.write_text(original_ag_storage, encoding="utf-8")

    class FailingSnapshotMatlab(MatlabAdapter):
        def snapshot(self, backup_dir: Path):
            from one_tone.adapters.base import AdapterResult

            return AdapterResult(self.target, "failed", False, False, "simulated snapshot disk failure")

    ag_adapter = AntigravityAdapter(config_path=ag_config, storage_path=ag_storage)
    matlab_adapter = FailingSnapshotMatlab(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan(
        "#22C55E",
        ["antigravity", "matlab"],
        plan_id="plan-snap-fail-multi-001",
        target_instances={"antigravity": ag_adapter.target_instance(), "matlab": matlab_adapter.target_instance()},
    )
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"antigravity": ag_adapter, "matlab": matlab_adapter}, store, confirm=True)
    assert record.status == TransactionStatus.PARTIAL
    assert [op["operation"] for op in record.results["matlab"]] == ["detect", "snapshot"]
    assert settings_path.read_bytes() == original_matlab

    latest_id = store.latest_transaction_id()
    assert latest_id == record.id
    restored = store.rollback(latest_id, {"antigravity": ag_adapter, "matlab": matlab_adapter})
    assert restored.status == TransactionStatus.ROLLED_BACK
    assert restored.results["matlab"][-1]["status"] == "skipped"
    assert json.loads(ag_config.read_text(encoding="utf-8")) == json.loads(original_ag_config)
    assert json.loads(ag_storage.read_text(encoding="utf-8")) == json.loads(original_ag_storage)
    assert settings_path.read_bytes() == original_matlab


def test_matlab_unsupported_zip_compression_returns_failed_verify_instead_of_crashing(tmp_path):
    """Round 6 P2: Unsupported ZIP compression method must map to failed/skipped, never uncaught NotImplementedError."""
    bad_zip_path = tmp_path / "R2026a" / "matlab.mlsettings"
    bad_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bad_zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("fsroot/schema.json", "com.mathworks/settings/jsonschema/1-1-0")
    raw = bytearray(bad_zip_path.read_bytes())
    # Patch compression method from 0 (STORED) to 99 (unsupported) in both Local File Header and Central Directory
    lfh_idx = raw.index(b"PK\x03\x04")
    cdh_idx = raw.index(b"PK\x01\x02")
    raw[lfh_idx + 8 : lfh_idx + 10] = (99).to_bytes(2, "little")
    raw[cdh_idx + 10 : cdh_idx + 12] = (99).to_bytes(2, "little")
    bad_zip_path.write_bytes(bytes(raw))

    adapter = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(bad_zip_path.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-bad-comp-001")
    assert adapter.detect().status == "skipped"
    verify_res = adapter.verify(plan)
    assert verify_res.status == "failed"
    assert verify_res.verified is False
    assert "Failed to read MATLAB settings archive" in verify_res.message


def test_matlab_verify_uses_single_read_for_verdict_and_target_instance(tmp_path, monkeypatch):
    """Round 6 P2: Verify verdict and metadata.target_instance must come from the same single read."""
    settings_path = _make_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-verify-single-001", target_instances={"matlab": adapter.target_instance()})
    assert adapter.apply(plan).status == "partial"

    read_calls = {"count": 0}
    orig_load_checked = adapter._load_checked

    def load_and_corrupt_after_read():
        read_calls["count"] += 1
        result = orig_load_checked()
        # Corrupt manifest on disk right after Verify's read completes
        _replace_zip_entry(settings_path, _MANIFEST_ENTRY, "<broken")
        return result

    monkeypatch.setattr(adapter, "_load_checked", load_and_corrupt_after_read)
    verify_res = adapter.verify(plan)
    assert read_calls["count"] == 1
    assert verify_res.verified is True
    assert verify_res.status == "partial"
    assert verify_res.metadata["target_instance"]["status"] == "ok"
    assert verify_res.metadata["target_instance"]["release"] == "R2026a"


def test_matlab_unsupported_xml_encoding_returns_failed_verify_instead_of_lookup_error(tmp_path):
    """Round 7 P2: Unknown XML encoding declaration must map to failed/skipped, never uncaught LookupError."""
    # Case A: Unsupported encoding in filesystemManifest.xml
    settings_a = _make_mlsettings(tmp_path / "a" / "R2026a" / "matlab.mlsettings")
    with zipfile.ZipFile(settings_a, "r") as zin:
        manifest_text = zin.read(_MANIFEST_ENTRY).decode("utf-8")
    bad_manifest = manifest_text.replace('encoding="UTF-8"', 'encoding="nonexistent-encoding-xyz"')
    _replace_zip_entry(settings_a, _MANIFEST_ENTRY, bad_manifest)

    adapter_a = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_a.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-bad-xml-enc-001")
    assert adapter_a.detect().status == "skipped"
    res_a = adapter_a.verify(plan)
    assert res_a.status == "failed"
    assert res_a.verified is False

    # Case B: Unsupported encoding in mwcorePropertiesReleaseInfo.xml
    settings_b = _make_mlsettings(tmp_path / "b" / "R2026a" / "matlab.mlsettings")
    _replace_zip_entry(
        settings_b,
        "metadata/mwcorePropertiesReleaseInfo.xml",
        '<?xml version="1.0" encoding="nonexistent-encoding-xyz"?><MathWorks_version_info><release>R2026a</release></MathWorks_version_info>',
    )
    adapter_b = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_b.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    assert adapter_b.detect().status == "skipped"
    res_b = adapter_b.verify(plan)
    assert res_b.status == "failed"
    assert res_b.verified is False


def test_matlab_rejects_mismatched_manifest_target_and_group_declared_path(tmp_path):
    """Round 7 P2: Inconsistent manifest file link or group JSON 'path' must fail validation and verify."""
    # Case A: Manifest points managed settings.json entry to another existing ZIP member
    settings_a = _make_theme_mlsettings(tmp_path / "a" / "R2026a" / "matlab.mlsettings", "Dark")
    with zipfile.ZipFile(settings_a, "a", compression=zipfile.ZIP_DEFLATED) as zapp:
        zapp.writestr("fsroot/other.json", '{"dummy":true}')
    with zipfile.ZipFile(settings_a, "r") as zin:
        manifest_text = zin.read(_MANIFEST_ENTRY).decode("utf-8")
    tampered_manifest = manifest_text.replace(
        'content="/fsroot/settingstree/matlab/appearance/settings.json"',
        'content="/fsroot/other.json"',
    )
    _replace_zip_entry(settings_a, _MANIFEST_ENTRY, tampered_manifest)
    original_a = settings_a.read_bytes()

    adapter_a = MatlabAdapter(
        target_instance={"status": "ok", "settings_path": str(settings_a.resolve()), "release": "R2026a"},
        is_running_fn=lambda: False,
    )
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-path-consistency-001")
    assert adapter_a.detect().status == "skipped"
    assert "inconsistent target" in adapter_a.detect().message
    assert adapter_a.apply(plan).status == "skipped"
    assert adapter_a.verify(plan).status == "failed"
    assert settings_a.read_bytes() == original_a

    # Case B: Settings group JSON declares wrong 'path' after valid apply
    settings_b = _make_mlsettings(tmp_path / "b" / "R2026a" / "matlab.mlsettings")
    adapter_b = MatlabAdapter(settings_path=settings_b, is_running_fn=lambda: False)
    plan_b = create_plan("#22C55E", ["matlab"], plan_id="plan-path-consistency-002", target_instances={"matlab": adapter_b.target_instance()})
    assert adapter_b.apply(plan_b).status == "partial"
    assert adapter_b.verify(plan_b).verified is True

    app_doc = _read_group(settings_b, "/settingstree/matlab/appearance")
    assert app_doc is not None
    app_doc["path"] = "/settingstree/matlab/wrong_group"
    _replace_zip_entry(settings_b, "fsroot/settingstree/matlab/appearance/settings.json", json.dumps(app_doc, separators=(",", ":")))

    verify_b = adapter_b.verify(plan_b)
    assert verify_b.status == "failed"
    assert verify_b.verified is False
    assert "declares path" in verify_b.message


def test_matlab_concurrent_adapter_reuse_checks_each_transactions_own_snapshot_digest(tmp_path):
    """Round 7 P2: Reusing one MatlabAdapter across interleaved transactions must check each tx's own snapshot digest."""
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    light_bytes = _make_theme_mlsettings(tmp_path / "other" / "R2026a" / "matlab.mlsettings", "Light").read_bytes()

    shared_adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan_a = create_plan("#22C55E", ["matlab"], plan_id="plan-reuse-a-001", target_instances={"matlab": shared_adapter.target_instance()})

    interleaved = {"done": False}

    class InterleavingStore(TransactionStore):
        def append_operation(self, record, target, operation, result):
            super().append_operation(record, target, operation, result)
            if operation == "snapshot" and not interleaved["done"]:
                interleaved["done"] = True
                # Simulate concurrent edit to Light + second transaction taking a snapshot on the SAME adapter
                settings_path.write_bytes(light_bytes)
                other_backup = tmp_path / "other_tx_backup"
                assert shared_adapter.snapshot(other_backup).status == "ok"

    store = InterleavingStore(tmp_path / "transactions")
    rec_a = apply_plan(plan_a, {"matlab": shared_adapter}, store, confirm=True)

    assert interleaved["done"] is True
    assert rec_a.status == TransactionStatus.FAILED
    assert [op["operation"] for op in rec_a.results["matlab"]] == ["detect", "snapshot", "apply"]
    assert "changed since snapshot" in rec_a.results["matlab"][-1]["message"]
    assert rec_a.results["matlab"][-1]["metadata"]["aborted_before_write"] is True
    assert settings_path.read_bytes() == light_bytes


def test_matlab_rollback_post_write_readback_error_records_changed_true(tmp_path, monkeypatch):
    """Round 7 P3: Read-back error after rollback os.replace completes must still record changed=True."""
    import one_tone.adapters.matlab as matlab_mod

    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: False)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-rb-readback-err-001", target_instances={"matlab": adapter.target_instance()})
    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.PARTIAL

    orig_load = matlab_mod._load_and_validate_mlsettings
    load_calls = {"count": 0}

    def fail_on_readback(path):
        load_calls["count"] += 1
        if load_calls["count"] == 2:
            raise PermissionError("simulated post-write rollback readback error")
        return orig_load(path)

    monkeypatch.setattr(matlab_mod, "_load_and_validate_mlsettings", fail_on_readback)
    rb = store.rollback(record.id, {"matlab": adapter})
    assert load_calls["count"] == 2
    assert rb.status == TransactionStatus.FAILED
    rb_op = rb.results["matlab"][-1]
    assert rb_op["status"] == "failed"
    assert rb_op["changed"] is True
    assert rb_op["verified"] is False
    app_doc = _read_group(settings_path, "/settingstree/matlab/appearance")
    assert app_doc is not None and json.loads(app_doc["settings"][0]["value"]) == "Dark"


def test_matlab_managed_process_shutdown_closes_during_write_and_fails_closed_if_stuck(tmp_path):
    settings_path = _make_theme_mlsettings(tmp_path / "R2026a" / "matlab.mlsettings", "Dark")
    state = {"running": True, "close_calls": 0}

    def closer():
        state["close_calls"] += 1
        state["running"] = False
        return True, "MATLAB closed gracefully"

    adapter = MatlabAdapter(settings_path=settings_path, is_running_fn=lambda: state["running"], process_closer=closer)
    plan = create_plan("#22C55E", ["matlab"], plan_id="plan-matlab-close-001", target_instances={"matlab": adapter.target_instance()})
    assert adapter.detect().status == "partial"
    assert state["close_calls"] == 0  # detect stays strictly read-only

    store = TransactionStore(tmp_path / "transactions")
    record = apply_plan(plan, {"matlab": adapter}, store, confirm=True)
    assert record.status == TransactionStatus.PARTIAL
    assert state["close_calls"] == 1

    state["running"] = True
    rb = store.rollback(record.id, {"matlab": adapter})
    assert rb.status == TransactionStatus.ROLLED_BACK
    assert state["close_calls"] == 2

    stubborn = MatlabAdapter(
        settings_path=settings_path,
        is_running_fn=lambda: True,
        process_closer=lambda: (False, "refused exit"),
    )
    assert stubborn.rollback(store.backup_path_for(record.id, "matlab")).status == "failed"
