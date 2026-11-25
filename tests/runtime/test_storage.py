import pytest

import one_tone.storage as storage


def test_atomic_write_text_preserves_original_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("original", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("forced replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="forced replace failure"):
        storage.atomic_write_text(path, "updated")

    assert path.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_write_bytes_writes_exact_bytes(tmp_path):
    path = tmp_path / "nested" / "blob.bin"
    payload = b"\x89PNG\r\n\x1a\n\x00\xff"
    storage.atomic_write_bytes(path, payload)
    assert path.read_bytes() == payload
    assert not list(path.parent.glob(".blob.bin.*.tmp"))


def test_patch_jsonc_object_preserves_comments_and_falls_back_safely():
    original = (
        "// Top header comment\n"
        "{\n"
        "  /* keep proxy comment */\n"
        '  "http.proxy": "http://127.0.0.1:7890",\n'
        '  "remove.me": true,\n'
        '  "workbench.colorTheme": "Old Theme" // trailing comment\n'
        "}\n"
    )
    patched = storage.patch_jsonc_object(
        original,
        {"workbench.colorTheme": "One Tone Dark", "window.autoDetectColorScheme": True},
        removals=("remove.me",),
    )
    assert "// Top header comment" in patched
    assert "/* keep proxy comment */" in patched
    assert "// trailing comment" in patched
    parsed = storage.loads_jsonc(patched)
    assert parsed == {
        "http.proxy": "http://127.0.0.1:7890",
        "workbench.colorTheme": "One Tone Dark",
        "window.autoDetectColorScheme": True,
    }

    # Malformed JSONC falls back safely to valid JSON without crashing
    fallback = storage.patch_jsonc_object("{broken", {"a": 1}, expected_dict={"a": 1})
    assert storage.loads_jsonc(fallback) == {"a": 1}
