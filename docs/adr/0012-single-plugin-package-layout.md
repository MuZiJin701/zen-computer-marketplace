# ADR 0012: Single-plugin package layout

## Status

Accepted (2026-11-18).

## Context

[ADR 0011](0011-single-plugin-antigravity-and-standard-editor-paths.md) narrowed the repository to One-Tone. The source tree and test hierarchy still mirror the former multi-plugin catalog. Codex supports a repository-root Plugin, but installing it also copies repository files into the cache. [Codex packaging documentation](https://developers.openai.com/plugins/build/plugins#how-local-marketplaces-work)

## Decision

Use `plugin/` as the root of the sole Plugin and `plugin/skills/zen-one-tone-windows/` as the self-contained Skill package. The root Marketplace points at `plugin/`. Use the same Skill package for Codex and standalone Skill installation. Keep repository documentation and the test harness outside the Plugin package. Revisit a multi-plugin layout if a second independently installable Plugin is needed.

Keep distribution checks directly under `tests/` and runtime checks under `tests/runtime/`.

## Consequences

Preserve the Marketplace, Plugin and Skill names and the Skill path relative to the Plugin root. The [Skill-local runtime root](0005-skill-local-runtime-root.md) remains the persistence boundary for Plans, Transactions and Rollback. The July 26 slimming spec recorded the directory constraints for that cleanup. This ADR governs the new directory layout.

The layout migration covers repository files only.
