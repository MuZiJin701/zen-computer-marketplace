import json
from pathlib import Path


def test_plugin_scaffold_is_present():
    root = Path("plugin")
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == "zen-one-tone-windows"
    assert manifest["extensions"]["com.openai"]["interface"]["displayName"] == "统一 Windows 主题"
    claude_manifest = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert claude_manifest["name"] == manifest["name"]
    assert claude_manifest["version"] == manifest["version"]
    for removed in (".cursor-plugin", ".grok-plugin", ".codex-plugin"):
        assert not (root / removed).exists(), removed
    assert [path.name for path in (root / "skills").iterdir() if path.is_dir()] == [manifest["name"]]
    assert not (root / "pyproject.toml").exists()
    assert (root / "skills/zen-one-tone-windows/SKILL.md").is_file()
    assert (root / "skills/zen-one-tone-windows/agents/openai.yaml").is_file()
    assert (root / "skills/zen-one-tone-windows/references/targets.md").is_file()
    assert (root / "skills/zen-one-tone-windows/examples/preview-request.md").is_file()
    assert not (root / "examples").exists()
    assert not (root / "skills/zen-one-tone-windows/references/workflow.md").exists()
    assert not (root / "skills/zen-one-tone-windows/references/target-matrix.md").exists()
    assert (root / "skills/zen-one-tone-windows/scripts/run_one_tone.py").is_file()
    assert not list((root / "skills/zen-one-tone-windows/scripts").glob("*.ps1"))


def test_packaged_skill_preserves_explicit_invocation():
    skill = Path("plugin/skills/zen-one-tone-windows")
    assert "disable-model-invocation: true" in (skill / "SKILL.md").read_text(encoding="utf-8")
    metadata = (skill / "agents/openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in metadata


def test_skill_package_does_not_include_repository_tests_or_archive():
    plugin = Path("plugin")
    skill = plugin / "skills/zen-one-tone-windows"
    for root in (plugin, skill):
        assert not (root / "tests").exists()
        assert not (root / "docs").exists()


def test_generated_runtime_directories_are_ignored():
    ignore = Path(".gitignore")
    assert ignore.is_file()
    text = ignore.read_text(encoding="utf-8")
    assert ".one-tone/" in text
    assert "__pycache__/" in text
    assert ".pytest_cache/" in text
