# ADR 0010: Evidence-backed appearance policy

## Status

Accepted — 2026-10-05, implementing the user's [official coverage spec](../specs/2026-10-05-official-theme-coverage-and-slimming.md). Extends ADR 0001/0002/0006/0008; historical records remain unchanged.

## Context

The previous inventory covered common colors and could imply support beyond the installed version. New solid-window behavior must not silently enlarge an older Plan's authorization. Fonts, accessibility and unrelated preferences must remain independently preserved. ADR 0006 already selects native system following; the spec now explicitly replaces the older App appearanceTheme-preservation behavior with `system`.

## Decision

Keep the existing Palette → Plan → Adapter artifacts → Transaction seams. A fixed distributable field table intersects pinned public documentation with source-derived registered Workbench baselines; an independent fixture verifies coverage. Unknown versions safely skip or report unsupported. Window solidity and decorative alpha are separate policies; text contrast uses actual composited backgrounds.

Hash the current Appearance policy and discovered field/instance evidence into the Plan. Reject obsolete policies or changed field contracts before Transaction/Snapshot creation and require Preview. Explicit historical Transaction Rollback continues independently. Confirmed Apply closes supported Windows/Terminal transparency entries and selects App system appearance while preserving fonts, system modes, automatic accent selection, high contrast and unknown keys.

## Consequences

Current known Workbench baselines are 1.107.1 and 1.140.0; adding another requires fixed source evidence and independent coverage fixtures. Old Plans require regeneration. Full managed artifact Verify is read-only; configuration matching does not establish rendering acceptance. Chrome activation remains manual; no dependency, background service, watcher, generic serializer or plugin framework is added. See [field evidence](../theme-field-coverage-evidence.md).
