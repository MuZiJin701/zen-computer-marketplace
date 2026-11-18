import json
from pathlib import Path


def test_repo_marketplace_points_to_plugin():
    payload = json.loads(Path(".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert payload["name"] == "zen-computer-marketplace"
    (entry,) = payload["plugins"]
    assert entry["name"] == "zen-one-tone-windows"
    assert entry["source"] == "./plugin"


def test_redundant_host_marketplaces_are_removed():
    for removed in (".agents", ".github/plugin", ".grok-plugin", ".cursor-plugin"):
        assert not Path(removed).exists(), removed


def test_plugin_contains_skill_runtime_source():
    root = Path("plugin")
    skill = root / "skills/zen-one-tone-windows"
    assert (skill / "src/one_tone/cli.py").is_file()
    assert (skill / "pyproject.toml").is_file()
    assert not (root / "src").exists()
    assert not (root / "pyproject.toml").exists()


def test_skill_launcher_points_at_skill_runtime():
    script = Path("plugin/skills/zen-one-tone-windows/scripts/run_one_tone.py").read_text(encoding="utf-8")
    skill = Path("plugin/skills/zen-one-tone-windows/SKILL.md").read_text(encoding="utf-8")
    assert "uv" in script
    assert "--project" in script
    assert "parents[1]" in script
    assert "run_one_tone.py" in skill


def test_readmes_document_root_and_skill_runtime_commands():
    root_readme = Path("README.md").read_text(encoding="utf-8")
    plugin_readme = Path("plugin/README.md").read_text(encoding="utf-8")
    assert "python .\\scripts\\run_one_tone.py preview" in root_readme
    assert "uv run --project . one-tone" in plugin_readme


def test_readme_documents_repo_marketplace_and_plugin_runtime():
    root_readme = Path("README.md").read_text(encoding="utf-8")
    plugin_readme = Path("plugin/README.md").read_text(encoding="utf-8")
    assert ".claude-plugin/marketplace.json" in root_readme
    assert "plugin/" in root_readme
    assert "可独立分发" in plugin_readme


def test_repository_test_layout_is_documented():
    assert Path("tests/README.md").is_file()
    assert Path("docs/README.md").is_file()
    assert Path("tests/runtime/test_palette.py").is_file()
