# Testing

## Default verification

Run from the repository root:

~~~powershell
uv run pytest
uv run --project plugins/zen-one-tone-windows/skills/zen-one-tone-windows one-tone --help
uv run --project plugins/zen-desktop-zero/skills/zen-desktop-zero desktop-zero --help
uv run --project plugins/zen-scoop-toolchain/skills/zen-scoop-toolchain scoop-toolchain --help
git diff --check
~~~

The root project is a test harness. Each Skill owns its launcher and runtime; tests remain outside distributable Skills and mirror the Marketplace → Plugin → Skill hierarchy. Default workstation tests use temporary directories and fakes; real desktop deletion, elevation, process termination, Scoop installation and winget installation remain risk-documented manual tests. Runtime tests for each Skill live under the matching Plugin and Skill test directory.

## Required coverage for workstation Plugins

- Marketplace and Plugin tests verify both workstation Plugin envelopes, their one-Skill package shape and Marketplace registration.
- Desktop zero tests cover Resolved desktop discovery, redirected desktop paths, Public Desktop exclusion, D-drive/data preflight, deterministic categories, shortcut deletion, collision suffixes, locked-item partial results and Preview read-only behavior.
- Desktop zero tests cover constrained repair: only confirmed non-system locking processes may be attempted, while unknown and system processes are never terminated.
- Desktop zero tests cover Verify and explicit transaction-ID rollback for moved files; deleted shortcuts remain non-restorable.
- Scoop toolchain tests cover existing-tool preservation, fixed `D:\software\scoop` preflight, Scoop bootstrap, Scoop-first installation, winget fallback, path-conformity reporting and no-uninstall behavior.
- Both workflows test explicit confirmation, structured `ok`, `partial`, `failed` and `skipped` aggregation, safe path validation and atomic Plan persistence.
- Default tests use fake desktop, process and installer backends. Real desktop deletion, process termination, elevation, Scoop and winget operations are separately marked and risk-documented.

## Required coverage for the theme-field work

- Palette tests cover both light and dark modes, exact Seed Color anchor preservation, distinct surface roles, passive region separation and interactive boundary separation.
- Palette tests also cover appearance-safe Tonal surfaces, Theme anchor hue retention, bounded chroma, no unjustified pure-black/pure-white ordinary roles and extreme Seed Colors such as red, yellow, cyan and near-black.
- Palette and Plan tests also verify Mode coherence: explicit Light/Dark Accents retain one Seed Color identity, corresponding large-area roles stay within `0.35` OKLCH lightness difference, ordinary surfaces avoid near-white/near-black collapse, and incoherent persisted Mode pairs are rejected.
- Light Mode dense primary text uses an opaque primary role and `7:1` contrast on its actual surface; muted, transparent and semantic state colors remain limited to secondary or stateful fields and use the existing `4.5:1` target where applicable.
- Plan tests cover mode Palettes, field capability expectations and stable Plan hashes.
- Windows tests cover safe registry and wallpaper outputs, preserved mode/automatic-color/high-contrast settings, field-level partial results, and `AccentPalette` white-glyph contrast.
- Windows Terminal tests cover paired Schemes, Profile `colorScheme` mappings, all profile entries, all documented color fields, Tab/Tab Row/window fields and system mode selection.
- Windows Terminal tests also cover optional PSReadLine prediction capability discovery, supported `InlinePrediction`/list prediction fields, Windows Terminal session guarding, Profile preservation and local rollback.
- VS Code and TRAE tests cover the standard public Workbench field inventory, Git decoration fields, exact contributed Light/Dark labels, enabled auto-detect settings and discoverable TRAE-specific fields.
- VS Code/TRAE instance tests cover standard and portable layouts, multiple-instance ambiguity, read-only path discovery, Plan-persisted paths, registration evidence, and non-zero CLI results with successful installation evidence.
- ChatGPT App tests cover every verified v1 color field plus fonts-table repair, opaque-window and maximum-contrast settings in both theme tables, while preserving unknown configuration keys and existing font values.
- Chrome tests independently cover the fixed parser's 24 colors, 6 tints and applicable properties in exactly two unpacked Light/Dark directories and internal ZIPs; invalid fields and image-only properties are absent. Drift/missing artifacts fail read-only Verify; activation remains manual.
- Transaction tests retain per-Target Snapshot, operation persistence, compensation and rollback behavior and cover JSON-safe binary report values.
- CLI tests cover parseable JSON-mode Apply and Verify responses when nested report metadata contains binary values.

## Test style

Public coverage regressions use an independent fixture with 971 documented VS Code IDs, 35 alpha constraints and source-derived 1.107.1/1.140.0 registrations; generated sets must exactly match the applicable intersections, excluding five Windows/ordinary-theme inapplicable fields. Numerical regressions check real composited find backgrounds, button/input hover pairs, focused icons, distinguishable Diff/Merge regions and opaque primary text. Font, high-contrast, cursor/glyph and unknown preferences remain unchanged. Runtime JSON is required in independently distributed Skill packages.

Windows regressions include mixed App/Shell modes, active/unknown high contrast, simulated API failure, actual Shell taskbar capability, transparency drift and absent-value restoration. Terminal covers version/platform gates, solid defaults/Profile/unfocused policies, removal of fixed tabColor and invalid Scheme selectionForeground, preservation of custom theme preferences and only two native variants. ChatGPT tests repair missing semantic/font structures and verify system appearance plus every managed field. Editor discovery tests forwarded/versioned launchers, unknown baselines and exact contribution paths/types/labels; complete non-frame/token drift fails Verify without writes.

Plan/Transaction regressions reject old appearance policies and changed field contracts before Transaction/Snapshot creation while keeping historical Rollback independent. Preview must report actual capability statuses and generated values. Python compilation is checked with `uv run python -m compileall -q plugins/zen-one-tone-windows/skills/zen-one-tone-windows/src`; no type checker or new dependency is installed. Source and visual limits are recorded in [field evidence](theme-field-coverage-evidence.md).

Tests cross the highest available Seam and assert external behavior:

- Generated Palette and Plan data, not private color helper calls.
- JSON, TOML and ZIP artifacts, not internal dictionary construction.
- AdapterResult status and field capability payloads, not logging text.
- Temporary files and fake registry/desktop backends for default tests.
- Temporary files and fake process/package-manager backends for workstation workflows.
- Real installed applications only in separately marked, risk-documented tests.

A passing fixture test is not proof that a real desktop Target renders every public field. Manual screenshots remain required for visual acceptance.

The focused regression gate additionally covers TRAE Git decorations, Windows Terminal PSReadLine prediction colors, Windows Light/Dark taskbar Accent mode cycling, and a real Quick Settings screenshot with legible active-tile white glyphs. Taskbar registry state is not treated as visual proof when the OS ignores the requested Light-mode display.

The runtime Plan stores both `light` and `dark` Palettes under one canonical `palettes` field. The legacy persisted `palette` field is rejected rather than guessed or migrated. `Plan.palette_for(mode)` returns a copy; single-mode Adapters use the Plan's selected mode, while paired artifact Adapters explicitly cover both modes. Existing v1 callers that invoke `generate_palette(seed)` retain the original single-palette shape; new Plan and artifact paths use explicit modes.

## Terminal functional text acceptance

The [terminal spec](specs/2026-10-05-terminal-readability.md) requires body text at 7:1 in both Modes and other functional text at 4.5:1 against its actual rendered background. Regression tests at Plan → Adapter → configuration/Transaction cover Seeds `#00C853`, `#10B981`, `#FFD700`, primary/white text on ANSI black, reverse pairs, semantic distinction and selection pairs. They also cover supported/old/unknown host versions, defaults/Profile/unfocused overrides, read-only drift detection, exact restoration including absent fields, and compensation on Profile write failure. PowerShell discovery chooses only `pwsh`, verifies Core >= 7, and never falls back to Windows PowerShell.

Run the packaged `scripts/terminal_readability_sample.py` in Windows Terminal and the App embedded terminal. It emits synthetic default/ANSI16/ANSI256/RGB/application-background/dim/reverse combinations without reading or writing configuration. Manually select ordinary, ANSI, RGB and dim samples. For an already-authorized real SSH connection, send the same script over stdin using PowerShell 7; do not copy configuration or install remote tools:

~~~powershell
Get-Content -Raw .\scripts\terminal_readability_sample.py | ssh <existing-host> python3 -
~~~

For each host × local/real SSH × Light/Dark × all three Seeds, also exercise the actual Codex CLI and the identified editor/version, including body, syntax, path, version, status bar, placeholder, input and selected text. Record host/program versions, actual displayed foreground/background, contrast and visual pass/fail/untested. Host correction does not guarantee those thresholds, and dim/selection compositing requires final rendered colors. Configuration `verified`, diagnostic transport and captured output never substitute for this matrix.

Real theme changes still follow Preview → confirmed Plan Apply → read-only Verify → explicit Transaction Rollback. Do not switch the Windows theme mode automatically. The App embedded terminal's full ANSI/native correction is unsupported because its verified user schema exposes no entry point. An unidentified local program, broken/missing remote Codex CLI or unavailable visual check remains untested; no complete acceptance claim is allowed. Current measurements and remaining gates are in [the evidence record](terminal-readability-evidence.md). No type checker is configured; Python compilation is checked alongside fixture tests without installing a new dependency.
