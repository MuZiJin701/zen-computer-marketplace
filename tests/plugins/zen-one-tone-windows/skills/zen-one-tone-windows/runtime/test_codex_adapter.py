import json
import tomllib

from one_tone.adapters.codex import (
    CHATGPT_APP_CONFIG_SCHEMA_V1,
    CodexAdapter,
    default_codex_config_path,
    locate_verified_codex_config,
)
from one_tone.plan import create_plan


def write_codex_v1_fixture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Keep this comment and unrelated fields.\n[desktop]\nappearanceTheme = \"dark\"\nunrelatedSetting = \"keep\"\n\n[desktop.appearanceLightChromeTheme]\naccent = \"#FFE66D\"\ncontrast = 100\nink = \"#FFFFFF\"\nopaqueWindows = true\nsurface = \"#062D14\"\n\n[desktop.appearanceLightChromeTheme.fonts]\neditor = \"keep\"\n\n[desktop.appearanceLightChromeTheme.semanticColors]\ndiffAdded = \"#2EFF45\"\ndiffRemoved = \"#FF9AAF\"\nskill = \"#FFE66D\"\n\n[desktop.appearanceDarkChromeTheme]\naccent = \"#FFE66D\"\ncontrast = 100\nink = \"#FFFFFF\"\nopaqueWindows = true\nsurface = \"#062D14\"\n\n[desktop.appearanceDarkChromeTheme.fonts]\neditor = \"keep\"\n\n[desktop.appearanceDarkChromeTheme.semanticColors]\ndiffAdded = \"#2EFF45\"\ndiffRemoved = \"#FF9AAF\"\nskill = \"#FFE66D\"\n""",
        encoding="utf-8",
    )
    return path


def test_codex_v1_config_is_detected(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    result = CodexAdapter(path).detect()
    assert result.status == "ok"
    assert result.version == CHATGPT_APP_CONFIG_SCHEMA_V1


def test_chatgpt_app_config_match_does_not_claim_embedded_terminal_rendering(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    adapter = CodexAdapter(path)
    plan = create_plan("#00C853", ["chatgpt-app"])
    assert adapter.apply(plan).status == "ok"
    before = path.read_bytes()
    result = adapter.verify(plan)
    assert result.verified
    assert result.metadata["embedded_terminal"]["status"] == "unsupported"
    assert result.metadata["rendering_verification"] == "untested"
    assert path.read_bytes() == before


def test_codex_system_appearance_mode_is_detected(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    path.write_text(
        path.read_text(encoding="utf-8").replace('appearanceTheme = "dark"', 'appearanceTheme = "system"'),
        encoding="utf-8",
    )

    assert CodexAdapter(path).detect().status == "ok"


def test_codex_default_path_uses_userprofile(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    path = write_codex_v1_fixture(tmp_path / ".codex" / "config.toml")
    assert default_codex_config_path() == path
    assert locate_verified_codex_config() == path


def test_codex_unknown_config_is_skipped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[desktop]\nappearanceTheme = 'dark'\n", encoding="utf-8")
    result = CodexAdapter(path).detect()
    assert result.status == "skipped"
    assert "chatgpt-app-config-v1" in result.message


def test_codex_malformed_toml_is_skipped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[desktop\nappearanceTheme = 'dark'\n", encoding="utf-8")
    assert CodexAdapter(path).detect().status == "skipped"


def test_codex_v1_fixture_applies_verifies_and_restores_preserving_fields(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    original = path.read_bytes()
    adapter = CodexAdapter(path)
    plan = create_plan("#00A86B", ["chatgpt-app"], plan_id="plan-chatgpt-app-v1-001")

    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    applied = adapter.apply(plan)
    assert applied.status == "ok"
    assert applied.version == CHATGPT_APP_CONFIG_SCHEMA_V1

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    for mode, palette_mode in (("appearanceLightChromeTheme", "light"), ("appearanceDarkChromeTheme", "dark")):
        theme = payload["desktop"][mode]
        palette = plan.palette_for(palette_mode)
        assert theme["accent"] == palette["accent"]
        assert theme["ink"] == palette["foreground"]
        assert theme["surface"] == palette["surface"]
        assert theme["contrast"] == 100
        assert theme["opaqueWindows"] is True
        assert theme["fonts"]["editor"] == "keep"
        assert theme["semanticColors"]["diffAdded"] == palette["success_text"]
        assert theme["semanticColors"]["diffRemoved"] == palette["error_text"]
        assert theme["semanticColors"]["skill"] == palette["accent_text"]
    assert payload["desktop"]["unrelatedSetting"] == "keep"

    assert adapter.verify(plan).verified is True
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert path.read_bytes() == original


def test_codex_apply_raises_existing_theme_contrast_to_maximum(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    path.write_text(path.read_text(encoding="utf-8").replace("contrast = 100", "contrast = 20"), encoding="utf-8")
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-contrast-100-001")

    assert adapter.apply(plan).status == "ok"

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    assert payload["desktop"]["appearanceTheme"] == "dark"
    assert payload["desktop"]["appearanceLightChromeTheme"]["contrast"] == 100
    assert payload["desktop"]["appearanceDarkChromeTheme"]["contrast"] == 100


def test_codex_apply_repairs_missing_fonts_and_enforces_solid_chrome(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    text = path.read_text(encoding="utf-8").replace("contrast = 100", "contrast = 20").replace(
        "opaqueWindows = true", "opaqueWindows = false"
    )
    for mode in ("appearanceLightChromeTheme", "appearanceDarkChromeTheme"):
        text = text.replace(f'\n[desktop.{mode}.fonts]\neditor = "keep"\n', "\n")
    path.write_text(text, encoding="utf-8")
    original = path.read_bytes()
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-repair-001")

    detected = adapter.detect()
    assert detected.status == "ok"
    assert detected.verified is False
    assert "appearanceLightChromeTheme.fonts" in detected.message
    assert "appearanceDarkChromeTheme.fonts" in detected.message
    assert path.read_bytes() == original
    assert adapter.snapshot(tmp_path / "backup").status == "ok"
    assert adapter.apply(plan).status == "ok"

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    for mode in ("appearanceLightChromeTheme", "appearanceDarkChromeTheme"):
        theme = payload["desktop"][mode]
        assert theme["fonts"] == {}
        assert theme["opaqueWindows"] is True
        assert theme["contrast"] == 100
    assert adapter.verify(plan).verified is True
    assert adapter.rollback(tmp_path / "backup").verified is True
    assert path.read_bytes() == original


def test_codex_verify_requires_fonts_solid_chrome_and_maximum_contrast(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-verify-001")

    assert adapter.apply(plan).status == "ok"
    text = path.read_text(encoding="utf-8").replace(
        '\n[desktop.appearanceLightChromeTheme.fonts]\neditor = "keep"\n', "\n"
    )
    path.write_text(text, encoding="utf-8")
    assert adapter.verify(plan).verified is False

    assert adapter.apply(plan).status == "ok"
    path.write_text(path.read_text(encoding="utf-8").replace("opaqueWindows = true", "opaqueWindows = false"), encoding="utf-8")
    assert adapter.verify(plan).verified is False

    assert adapter.apply(plan).status == "ok"
    path.write_text(path.read_text(encoding="utf-8").replace("contrast = 100", "contrast = 20"), encoding="utf-8")
    assert adapter.verify(plan).verified is False


def test_codex_apply_preserves_existing_font_values_while_repairing_other_mode(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    text = path.read_text(encoding="utf-8").replace(
        '\n[desktop.appearanceLightChromeTheme.fonts]\neditor = "keep"\n', "\n"
    ).replace(
        '[desktop.appearanceDarkChromeTheme.fonts]\neditor = "keep"',
        '[desktop.appearanceDarkChromeTheme.fonts]\nui = "Inter"\ncode = "JetBrains Mono"',
    )
    path.write_text(text, encoding="utf-8")
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-fonts-001")

    assert adapter.apply(plan).status == "ok"

    themes = tomllib.loads(path.read_text(encoding="utf-8"))["desktop"]
    assert themes["appearanceLightChromeTheme"]["fonts"] == {}
    assert themes["appearanceDarkChromeTheme"]["fonts"] == {"ui": "Inter", "code": "JetBrains Mono"}


def test_codex_apply_preserves_existing_empty_fonts_tables(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    path.write_text(path.read_text(encoding="utf-8").replace('editor = "keep"\n', ""), encoding="utf-8")
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-empty-fonts-001")

    assert adapter.detect().verified is True
    assert adapter.apply(plan).status == "ok"

    themes = tomllib.loads(path.read_text(encoding="utf-8"))["desktop"]
    assert themes["appearanceLightChromeTheme"]["fonts"] == {}
    assert themes["appearanceDarkChromeTheme"]["fonts"] == {}


def test_codex_wrong_type_fonts_are_skipped_without_writing(tmp_path):
    path = write_codex_v1_fixture(tmp_path / "config.toml")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '\n[desktop.appearanceLightChromeTheme.fonts]\neditor = "keep"\n', '\nfonts = "unsupported"\n'
        ),
        encoding="utf-8",
    )
    original = path.read_bytes()
    adapter = CodexAdapter(path)
    plan = create_plan("#10B981", ["chatgpt-app"], plan_id="plan-chatgpt-app-invalid-fonts-001")

    assert adapter.detect().status == "skipped"
    assert adapter.apply(plan).status == "skipped"
    assert path.read_bytes() == original
