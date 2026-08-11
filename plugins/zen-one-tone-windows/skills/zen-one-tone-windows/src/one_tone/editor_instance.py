from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EditorSpec:
    target: str
    executable: str | Path
    settings_path: Path
    extensions_dir: Path
    ai_panel_supported: bool = False
    artifacts_dir: Path | None = None
    resolution_status: str = "ok"
    resolution_message: str = ""
    resolution_source: str = ""

    def target_instance(self) -> dict[str, str]:
        instance = {"status": self.resolution_status}
        if self.resolution_status == "ok":
            instance.update({
                "executable": str(self.executable),
                "settings_path": str(self.settings_path),
                "extensions_dir": str(self.extensions_dir),
            })
            if self.resolution_source:
                instance["source"] = self.resolution_source
        elif self.resolution_message:
            instance["reason"] = self.resolution_message
        return instance


def _launcher_argument(executable: Path, argument: str) -> Path | None:
    if executable.suffix.lower() not in {".cmd", ".bat"} or not executable.is_file():
        return None
    try:
        contents = executable.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    pattern = re.compile(rf"--{re.escape(argument)}(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|([^\s%]+))", re.IGNORECASE)
    match = pattern.search(contents)
    if not match:
        return None
    value = next((group for group in match.groups() if group), None)
    if not value:
        return None
    value = os.path.expandvars(value)
    if value.startswith("%~dp0"):
        value = str(executable.parent) + value[5:]
    path = Path(value)
    return path if path.is_absolute() else executable.parent / path


def _portable_editor_candidates(executable: Path) -> list[tuple[Path, Path, str]]:
    if not executable.is_file():
        return []
    roots = [executable.parent.parent] if executable.parent.name.casefold() == "bin" else []
    roots.extend(executable.parents)
    candidates: list[tuple[Path, Path, str]] = []
    seen: set[tuple[Path, Path]] = set()
    for root in roots:
        pair = (root / "data" / "user-data" / "User" / "settings.json", root / "data" / "extensions")
        if pair not in seen and (pair[0].is_file() or pair[1].is_dir()):
            seen.add(pair)
            candidates.append((*pair, "portable"))
    return candidates


def resolve_editor_spec(
    target: str,
    executable: Path,
    default_candidates: list[tuple[Path, Path, str]],
    settings_override: Path | None,
    extensions_override: Path | None,
    artifacts_dir: Path,
) -> EditorSpec:
    launcher_settings = _launcher_argument(executable, "user-data-dir")
    launcher_extensions = _launcher_argument(executable, "extensions-dir")
    if settings_override is not None or extensions_override is not None:
        settings = settings_override or (launcher_settings / "User" / "settings.json" if launcher_settings else default_candidates[0][0])
        extensions = extensions_override or launcher_extensions or default_candidates[0][1]
        return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_source="environment")
    if launcher_settings is not None or launcher_extensions is not None:
        settings = launcher_settings / "User" / "settings.json" if launcher_settings else default_candidates[0][0]
        extensions = launcher_extensions or default_candidates[0][1]
        return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_source="launcher")

    existing = _portable_editor_candidates(executable) + [candidate for candidate in default_candidates if candidate[0].is_file() or candidate[1].is_dir()]
    if existing:
        priority = min({"portable": 0, "standard": 1}.get(candidate[2], 99) for candidate in existing)
        candidates = [candidate for candidate in existing if {"portable": 0, "standard": 1}.get(candidate[2], 99) == priority]
        score = lambda candidate: (int(candidate[0].is_file()), int(candidate[1].is_dir()))
        winners = [candidate for candidate in candidates if score(candidate) == max(score(item) for item in candidates)]
        if len({(candidate[0], candidate[1]) for candidate in winners}) > 1:
            description = "; ".join(f"{settings} + {extensions}" for settings, extensions, _ in winners)
            settings, extensions, _ = winners[0]
            return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_status="skipped", resolution_message=f"{target} configuration paths are ambiguous: {description}")
        settings, extensions, source = winners[0]
        return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_source=source)
    settings, extensions, source = default_candidates[0]
    return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_status="skipped", resolution_message=f"{target} configuration instance was not found", resolution_source=source)


def editor_spec_from_plan(target: str, context: dict[str, object], fallback: EditorSpec) -> EditorSpec:
    if context.get("status") != "ok":
        return EditorSpec(target, fallback.executable, fallback.settings_path, fallback.extensions_dir, artifacts_dir=fallback.artifacts_dir, resolution_status="skipped", resolution_message=str(context.get("reason") or f"{target} has no resolved configuration instance in Plan"))
    try:
        return EditorSpec(target, Path(str(context["executable"])), Path(str(context["settings_path"])), Path(str(context["extensions_dir"])), artifacts_dir=fallback.artifacts_dir, resolution_source=str(context.get("source") or "plan"))
    except (KeyError, TypeError):
        return EditorSpec(target, fallback.executable, fallback.settings_path, fallback.extensions_dir, artifacts_dir=fallback.artifacts_dir, resolution_status="skipped", resolution_message=f"{target} Plan instance paths are incomplete")


def validate_editor_instance(target: str, instance: object) -> bool:
    if target not in {"vscode", "trae"} or not isinstance(instance, dict):
        return False
    status = instance.get("status")
    return status == "skipped" or (
        status == "ok" and all(isinstance(instance.get(key), str) for key in ("executable", "settings_path", "extensions_dir"))
    )
