# Testing

## Default verification

Run from the repository root:

~~~powershell
uv run pytest
uv run --project plugin/skills/zen-one-tone-windows one-tone --help
git diff --check
~~~

The root project is a test harness. `tests/` contains distribution checks and `tests/runtime/` contains runtime tests and fixtures. The `zen-one-tone-windows` Skill owns its launcher and runtime under `plugin/`.

## Required coverage for the theme-field work

- Palette tests cover both light and dark modes, exact Seed Color anchor preservation, distinct surface roles, passive region separation and interactive boundary separation.
- Palette tests also cover appearance-safe Tonal surfaces, Theme anchor hue retention, bounded chroma, no unjustified pure-black/pure-white ordinary roles and extreme Seed Colors such as red, yellow, cyan and near-black.
- Palette and Plan tests also verify Mode coherence: explicit Light/Dark Accents retain one Seed Color identity, corresponding large-area roles stay within `0.75` OKLCH lightness difference, ordinary surfaces avoid near-white/near-black collapse, and incoherent persisted Mode pairs are rejected.
- Light Mode dense primary text uses an opaque primary role and `7:1` contrast on its actual surface; muted, transparent and semantic state colors remain limited to secondary or stateful fields and use the existing `4.5:1` target where applicable.
- Plan tests cover mode Palettes, field capability expectations, policy revision `v9` rejection of older `v8` Plans, and stable Plan hashes.
- Windows tests cover mode-independent single-value outputs (`Background`, stepped `AccentColorInactive`, genuine 8-slot RGB0 `AccentPalette`, `SystemUsesLightTheme = 0` Custom Mode), preserved app-mode/automatic-color/high-contrast settings, cross-`AppsUseLightTheme` `verify` invariance without re-applying, per-monitor wallpaper snapshot/rollback, `refresh_theme()` on rollback, and `>= 3:1` Shell accent / `>= 4.5:1` desktop surface white-glyph contrast.
- Windows Terminal tests cover paired Schemes and window themes (`{"light": "One Tone Light", "dark": "One Tone Dark"}` following App mode on `>= 1.16`/`>= 1.17`), JSONC comment parsing, all profile entries, all documented color fields, Tab/Tab Row/window fields, Win32 version discovery, and adaptive Light/Dark PSReadLine prediction + core syntax colors.
- VS Code, TRAE and Antigravity IDE tests cover JSONC settings parsing, the standard public Workbench field inventory (`window.activeBorder`, `window.inactiveBorder`, `editor.selectionForeground`, `gauge.*`), expanded TextMate `tokenColors`, Git decoration fields, exact contributed Light/Dark labels, enabled auto-detect settings, `ok` status for verified `vscode` (and `partial` for `trae`/`antigravity-ide`), standard C-drive priority and portable `data/` mirror synchronization.
- ChatGPT App (`chatgpt-app`) tests cover every verified v1 color field (`accentSource = custom`, `contrast = 100`, `opaqueWindows = true`), safe initialization of missing theme tables, inline `semanticColors` replacement, plus fonts-table repair in both theme tables, while preserving unknown configuration keys and existing font values.
- Antigravity (`antigravity`) tests cover `~/.gemini/config/config.json` (`userSettings.themeMode`, `customThemeSeedsLight`, `customThemeSeedsDark`) and `%APPDATA%\Antigravity\app_storage.json` (mode-independent `hubSurfaceBackgroundColor` matching the desktop surface) across detect, snapshot, apply, verify and rollback.
- MATLAB (`matlab`) tests use fixture OPC ZIP `matlab.mlsettings` archives and injected process detectors (never launching MATLAB or touching real `%APPDATA%`) to cover release/schema gating (`>= R2025a`, skipping `<= R2024b` / uninitialized / unknown schemas, rejecting invalid XML `<release>` without folder fallback and rejecting invalid or missing frozen `matlab` Plan instances without falling back to live discovery), absolute-path freezing across working-directory changes, per-transaction Snapshot-to-Apply digest continuity (`backup_dir/matlab-state.json` `snapshot_sha256`, safe even when reusing one adapter across interleaved transactions), single-read validation + single-read verdict/`target_instance` consistency + post-enumeration pre-`os.replace` byte-identity/unredirected-path guard (blocking concurrent archive swaps before and during the final process check), pre-write abort vs. post-replace failure distinction (`aborted_before_write = true` skipping `auto_rollback` to preserve concurrent edits, while post-replace errors in Apply or Rollback record `changed = true` and remain compensatable/restorable, and targets whose `detect`/`snapshot` failed before `apply` are skipped on multi-target rollback), and release-mismatch rejection, discovery precedence (`ONE_TONE_MATLAB_SETTINGS` > `MATLAB_PREFDIR` > newest registry/AppData with directory/archive release match verification), strict ZIP duplicate-member, unsupported compression (`NotImplementedError`), unknown XML encoding (`LookupError`), manifest/group path consistency, boolean `hasValue`, `isVector` shape, and manifest/group corruption fail-closed protection (with `Verify` reporting `failed` on post-Apply corruption), dual-mode `DesktopColors` / `SyntaxHighlightingColors` (including `HighlightCurrentLineColor` and `LineColor`) + Light RGB mirrors + `filesystemManifest.xml`, `hasValue = false` rejection in `Verify`, WCAG contrast (`>= 7:1` body, `>= 4.5:1` syntax) across `BackgroundColor` and all highlight backgrounds over diverse seeds, policy revision `v8` rejection of older `v7` Plans, fail-closed `Live-process write guard` (entry + pre-`os.replace` TOCTOU guard, Win32 process enumeration failures including `Process32NextW` returning `FALSE` with error `0`, post-snapshot launch races, missing-MATLAB multi-target rollback, retry skipping already-restored targets, and `rollback --latest` skipping zero-modification or auto-compensated failed transactions), honest `partial` reporting (`desktop.chrome = unsupported`, `rendering_verification = untested`), and Snapshot-path-bound subkey-level Rollback (rejecting symlink/junction-redirected snapshot paths and mismatched adapter paths, and upgrading legacy snapshots without `kind`/`modes`) preserving post-Apply user edits (`RecentFileList`, toggles, and unmanaged colors inside `DesktopColors`/`SyntaxHighlightingColors`) and `GraphicsTheme`.
- Chrome tests independently cover the fixed parser's 24 colors, 6 `0.5`-neutral HSL shift tints, distinct Light/Dark manifest display names, and applicable properties in exactly two unpacked Light/Dark directories and internal ZIPs; invalid fields and image-only properties are absent. Drift/missing artifacts fail read-only Verify; activation remains manual.
- Transaction and CLI tests cover `sync`, `rollback --latest`, per-Target Snapshot, operation persistence, compensation, rollback behavior and JSON-safe binary report values.

## Test style

Public coverage regressions use an independent fixture with 971 documented VS Code IDs, 35 alpha constraints and source-derived 1.107.1/1.140.0 registrations; generated sets must exactly match the applicable intersections, excluding two high-contrast-only fields (`contrastBorder`, `contrastActiveBorder`). Numerical regressions check real composited find backgrounds, button/input hover pairs, focused icons, distinguishable Diff/Merge regions and opaque primary text. Font, high-contrast, cursor/glyph and unknown preferences remain unchanged. Runtime JSON is required in independently distributed Skill packages.

Windows regressions include mixed App/Shell modes, active/unknown high contrast, simulated API failure, actual Shell taskbar capability, transparency drift and absent-value restoration. Terminal covers version/platform gates, solid defaults/Profile/unfocused policies, removal of fixed tabColor and invalid Scheme selectionForeground, preservation of custom theme preferences and two native variants with `One Tone Dark` selected by default. ChatGPT tests repair missing semantic/font structures and verify system appearance plus every managed field. Editor discovery tests forwarded/versioned launchers, commit-subdirectory `package.json`, unknown baselines, standard C-drive priority + portable mirror, and exact contribution paths/types/labels; complete non-frame/token drift fails Verify without writes.

Plan/Transaction regressions reject old appearance policies and changed field contracts before Transaction/Snapshot creation while keeping historical Rollback independent. Preview must report actual capability statuses and generated values. Python compilation is checked with `uv run python -m compileall -q plugin/skills/zen-one-tone-windows/src`; no type checker or new dependency is installed. Source and visual limits are recorded in [field evidence](theme-field-coverage-evidence.md).

Tests cross the highest available Seam and assert external behavior:

- Generated Palette and Plan data, not private color helper calls.
- JSON, TOML and ZIP artifacts, not internal dictionary construction.
- AdapterResult status and field capability payloads, not logging text.
- Temporary files and fake registry/desktop backends for default tests.
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

Real theme changes follow `sync` or Preview → confirmed Plan Apply → read-only Verify → Transaction Rollback. Do not switch the Windows theme mode automatically. The App embedded terminal's full ANSI/native correction is unsupported because its verified user schema exposes no entry point. An unidentified local program, broken/missing remote Codex CLI or unavailable visual check remains untested; no complete acceptance claim is allowed. Current measurements and remaining gates are in [the evidence record](terminal-readability-evidence.md). No type checker is configured; Python compilation is checked alongside fixture tests without installing a new dependency.
