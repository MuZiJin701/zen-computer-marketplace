from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EDITOR_TARGETS = ("vscode", "trae", "antigravity-ide")


@dataclass(frozen=True)
class EditorSpec:
    target: str
    executable: str | Path
    settings_path: Path
    extensions_dir: Path
    ai_panel_supported: bool | None = None
    artifacts_dir: Path | None = None
    resolution_status: str = "ok"
    resolution_message: str = ""
    resolution_source: str = ""
    color_baseline: str = ""
    mirror_targets: tuple[tuple[Path, Path], ...] = ()

    def target_instance(self) -> dict[str, Any]:
        instance: dict[str, Any] = {"status": self.resolution_status}
        if self.resolution_status == "ok":
            instance.update({
                "executable": str(self.executable),
                "settings_path": str(self.settings_path),
                "extensions_dir": str(self.extensions_dir),
                "color_baseline": self.color_baseline,
            })
            if self.resolution_source:
                instance["source"] = self.resolution_source
            if self.mirror_targets:
                instance["mirror_targets"] = [
                    {"settings_path": str(settings), "extensions_dir": str(extensions)}
                    for settings, extensions in self.mirror_targets
                ]
        elif self.resolution_message:
            instance["reason"] = self.resolution_message
        return instance


def _normalize_color_baseline(version: object) -> str:
    if not isinstance(version, str):
        return ""
    if version in {"1.107.1", "1.140.0"}:
        return version
    match = re.match(r"^(\d+)\.(\d+)\.\d+", version.strip())
    if not match:
        return ""
    major, minor = int(match.group(1)), int(match.group(2))
    if major != 1 or minor < 80:
        return ""
    return "1.140.0" if (major, minor) >= (1, 140) else "1.107.1"


def discover_editor_color_baseline(executable: Path) -> str:
    shim = executable.with_suffix(".shim")
    if shim.is_file():
        try:
            match = re.search(r'^path = "([^"]+)"$', shim.read_text(encoding="utf-8"), re.MULTILINE)
        except OSError:
            return ""
        if not match:
            return ""
        executable = Path(match[1])
    metadata_paths: list[Path] = []
    # Resolve documented launcher forwarding and cli.js paths without executing it.
    for _ in range(3):
        if executable.suffix.lower() not in {".cmd", ".bat"}:
            break
        try:
            contents = executable.read_text(encoding="utf-8", errors="replace")
        except OSError:
            break
        quoted = re.findall(r'"([^"\r\n]+)"', contents)
        paths = [Path(value.replace("%~dp0", str(executable.parent) + os.sep)) for value in quoted]
        metadata_paths.extend(path.parent.parent / "package.json" for path in paths if path.name == "cli.js")
        forwarded = next((path for path in paths if path.suffix.lower() in {".cmd", ".bat"} and path.is_absolute() and path != executable), None)
        if forwarded is None:
            break
        executable = forwarded
    # Read only this launcher's product roots (including commit-hashed child directories), never an unrelated installation.
    for root in (executable.parent, executable.parent.parent):
        metadata_paths.append(root / "resources/app/package.json")
        if root.is_dir():
            try:
                for child in sorted(root.iterdir()):
                    if child.is_dir():
                        candidate = child / "resources/app/package.json"
                        if candidate.is_file():
                            metadata_paths.append(candidate)
            except OSError:
                continue
    for path in metadata_paths:
        try:
            version = json.loads(path.read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError, AttributeError):
            continue
        baseline = _normalize_color_baseline(version)
        if baseline:
            return baseline
    return ""


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
    color_baseline = discover_editor_color_baseline(executable)
    launcher_settings = _launcher_argument(executable, "user-data-dir")
    launcher_extensions = _launcher_argument(executable, "extensions-dir")
    if settings_override is not None or extensions_override is not None:
        settings = settings_override or (launcher_settings / "User" / "settings.json" if launcher_settings else default_candidates[0][0])
        extensions = extensions_override or launcher_extensions or default_candidates[0][1]
        return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_source="environment", color_baseline=color_baseline)

    portable_candidates = _portable_editor_candidates(executable)
    if len(portable_candidates) > 1:
        score = lambda candidate: (int(candidate[0].is_file()), int(candidate[1].is_dir()))
        portable_winners = [candidate for candidate in portable_candidates if score(candidate) == max(score(item) for item in portable_candidates)]
        if len({(candidate[0], candidate[1]) for candidate in portable_winners}) > 1:
            description = "; ".join(f"{settings} + {extensions}" for settings, extensions, _ in portable_winners)
            settings, extensions, _ = portable_winners[0]
            return EditorSpec(target, executable, settings, extensions, artifacts_dir=artifacts_dir, resolution_status="skipped", resolution_message=f"{target} configuration paths are ambiguous: {description}")

    launcher_pair: tuple[Path, Path] | None = None
    if launcher_settings is not None or launcher_extensions is not None:
        launcher_pair = (
            launcher_settings / "User" / "settings.json" if launcher_settings else default_candidates[0][0],
            launcher_extensions or default_candidates[0][1],
        )

    standard_existing = [candidate for candidate in default_candidates if candidate[0].is_file() or candidate[1].is_dir()]
    appdata_root_exists = bool(default_candidates) and default_candidates[0][0].parent.parent.parent.is_dir()
    if standard_existing or (executable.is_file() and (portable_candidates or launcher_pair is not None) and appdata_root_exists):
        if len(standard_existing) > 1:
            score = lambda candidate: (int(candidate[0].is_file()), int(candidate[1].is_dir()))
            winners = [candidate for candidate in standard_existing if score(candidate) == max(score(item) for item in standard_existing)]
            settings, extensions, source = winners[0]
        elif standard_existing:
            settings, extensions, source = standard_existing[0]
        else:
            settings, extensions, source = default_candidates[0]
        mirrors: list[tuple[Path, Path]] = []
        for candidate_settings, candidate_extensions, _ in portable_candidates:
            pair = (candidate_settings, candidate_extensions)
            if pair != (settings, extensions) and pair not in mirrors:
                mirrors.append(pair)
        if launcher_pair is not None and launcher_pair != (settings, extensions) and launcher_pair not in mirrors:
            if launcher_pair[0].is_file() or launcher_pair[1].is_dir() or launcher_pair[0].parent.is_dir():
                mirrors.append(launcher_pair)
        return EditorSpec(
            target,
            executable,
            settings,
            extensions,
            artifacts_dir=artifacts_dir,
            resolution_source=source or "standard",
            color_baseline=color_baseline,
            mirror_targets=tuple(mirrors),
        )

    if launcher_pair is not None:
        return EditorSpec(
            target,
            executable,
            launcher_pair[0],
            launcher_pair[1],
            artifacts_dir=artifacts_dir,
            resolution_source="launcher",
            color_baseline=color_baseline,
        )
    if portable_candidates:
        settings, extensions, source = portable_candidates[0]
        return EditorSpec(
            target,
            executable,
            settings,
            extensions,
            artifacts_dir=artifacts_dir,
            resolution_source=source,
            color_baseline=color_baseline,
        )
    settings, extensions, source = default_candidates[0]
    return EditorSpec(
        target,
        executable,
        settings,
        extensions,
        artifacts_dir=artifacts_dir,
        resolution_status="skipped",
        resolution_message=f"{target} configuration instance was not found",
        resolution_source=source,
    )


def editor_spec_from_plan(target: str, context: dict[str, object], fallback: EditorSpec) -> EditorSpec:
    if context.get("status") != "ok":
        return EditorSpec(target, fallback.executable, fallback.settings_path, fallback.extensions_dir, artifacts_dir=fallback.artifacts_dir, resolution_status="skipped", resolution_message=str(context.get("reason") or f"{target} has no resolved configuration instance in Plan"))
    try:
        raw_mirrors = context.get("mirror_targets", [])
        mirrors: list[tuple[Path, Path]] = []
        if isinstance(raw_mirrors, list):
            for entry in raw_mirrors:
                if isinstance(entry, dict) and isinstance(entry.get("settings_path"), str) and isinstance(entry.get("extensions_dir"), str):
                    mirrors.append((Path(entry["settings_path"]), Path(entry["extensions_dir"])))
        return EditorSpec(
            target,
            Path(str(context["executable"])),
            Path(str(context["settings_path"])),
            Path(str(context["extensions_dir"])),
            artifacts_dir=fallback.artifacts_dir,
            resolution_source=str(context.get("source") or "plan"),
            color_baseline=str(context.get("color_baseline") or ""),
            mirror_targets=tuple(mirrors),
        )
    except (KeyError, TypeError):
        return EditorSpec(target, fallback.executable, fallback.settings_path, fallback.extensions_dir, artifacts_dir=fallback.artifacts_dir, resolution_status="skipped", resolution_message=f"{target} Plan instance paths are incomplete")


def validate_editor_instance(target: str, instance: object) -> bool:
    if target not in EDITOR_TARGETS or not isinstance(instance, dict):
        return False
    status = instance.get("status")
    if status == "skipped":
        return True
    if status != "ok" or not all(isinstance(instance.get(key), str) for key in ("executable", "settings_path", "extensions_dir")):
        return False
    mirrors = instance.get("mirror_targets")
    if mirrors is not None:
        if not isinstance(mirrors, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("settings_path"), str)
            or not isinstance(item.get("extensions_dir"), str)
            for item in mirrors
        ):
            return False
    return True
