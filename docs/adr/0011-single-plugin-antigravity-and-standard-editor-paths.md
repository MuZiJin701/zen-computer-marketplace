# ADR 0011: Single-plugin focus, Antigravity targets, Dark default Terminal, and standard C-drive editor priority

## Status

Accepted — 2026-11-12; supersedes [ADR 0007](0007-workstation-plugin-boundaries.md) and extends [ADR 0004](0004-appearance-safe-palette.md), [ADR 0006](0006-mode-coherence-and-system-following.md), and [ADR 0010](0010-evidence-backed-appearance-policy.md).

## Context

1. The repository previously included two auxiliary workstation plugins (`zen-desktop-zero` and `zen-scoop-toolchain`) alongside `zen-one-tone-windows`. The user decided to focus the repository solely on `zen-one-tone-windows` and completely remove the other two plugins.
2. In `palette.py`, capping Light/Dark OKLCH surface lightness delta at `0.35` forced Light mode surfaces down to `L ≈ 0.686` (a muted mid-gray), while `accent_text` fell back to a hardcoded blue hue (`0.58`) when derived from neutral foreground.
3. Windows Terminal previously used paired `light`/`dark` theme selection; the user requires Windows Terminal to default to `One Tone Dark` across `theme`, `window.applicationTheme`, `defaults.colorScheme`, all profile `colorScheme` entries, `unfocusedAppearance.colorScheme`, and `WT_SESSION` PSReadLine predictions while keeping `One Tone Light` and `One Tone Dark` registered.
4. The user works with Google Antigravity 2.0 (`antigravity`) and Antigravity IDE (`antigravity-ide`), and wants VS Code, TRAE, and Antigravity IDE to prioritize the standard C-drive configuration paths (`%APPDATA%\<Editor>\User\settings.json` and `~/.<editor>/extensions`) even when installed via Scoop, without modifying Scoop's installation layout.
5. In the Skill workflow, interactive selection should use the Agent's structured question popup (`ask_question`) only at the Skill level when user choice is needed, and the CLI should provide a single-step `one-tone sync <seed_color>` command (`Preview → Apply → Verify`) plus `one-tone rollback` defaulting to the latest transaction.

## Decision

1. **Single Plugin**: Remove `zen-desktop-zero` and `zen-scoop-toolchain` from `plugins/`, `tests/`, `docs/`, and `.agents/plugins/marketplace.json`. Keep only `zen-one-tone-windows`.
2. **OKLCH Palette Refinement**: Raise `MODE_TONAL_LIGHTNESS_DELTA` to `0.75` and `MODE_LIGHT_SURFACE_MAX_LUMINANCE` to `0.96` so Light mode uses clean bright tonal surfaces (`L ≈ 0.82..0.97`) and Dark mode uses deep layered surfaces (`L ≈ 0.17..0.34`). Derive `accent_text` from the Seed Color's OKLCH hue (and semantic `error_text`, `warning_text`, `success_text` from fixed OKLCH hues with controlled chroma) while guaranteeing `>= 4.5:1` contrast on `surface` and `>= 7:1` neutral `foreground` contrast.
3. **Windows Terminal Default Dark Theme**: Set Windows Terminal's active `theme` to `"One Tone Dark"` (or `"dark"` on `< 1.17`), `window.applicationTheme` to `"dark"`, and `colorScheme` to `"One Tone Dark"` across `defaults`, all profiles, and `unfocusedAppearance`, while continuing to write both `One Tone Light` and `One Tone Dark` into `schemes` and `themes`.
4. **New Targets (`antigravity` and `antigravity-ide`)**:
   - `antigravity`: Manage `~/.gemini/config/config.json` (`userSettings.themeMode = "THEME_MODE_INHERIT"`, `customThemeSeedsLight`, `customThemeSeedsDark` with all 5 seed keys) and `%APPDATA%\Antigravity\app_storage.json` (`hubSurfaceBackgroundColor`).
   - `antigravity-ide`: Reuse `VSCodeFamilyAdapter` with standard paths `%APPDATA%\Antigravity IDE\User\settings.json` and `~/.antigravity-ide/extensions`.
5. **Standard C-Drive Priority with Portable Mirror**: `resolve_editor_spec` ranks `standard` C-drive paths above `portable` and `launcher` paths, passes `--user-data-dir` and `--extensions-dir` explicitly when running editor CLI commands, and records any existing portable/launcher directories in `mirror_targets` so `VSCodeFamilyAdapter` snapshots, applies, verifies, and rolls back both the standard C-drive directory and any existing portable `data/` directory.
6. **Expanded Field Coverage & Version Fallback**: Add `accentSource = "custom"` to ChatGPT App themes, `AccentColorInactive` and `Control Panel\Colors\Background` to Windows, and `window.activeBorder`, `window.inactiveBorder`, `editor.selectionForeground`, and `gauge.*` to VS Code family themes. Support verified Workbench baselines `1.107.0`, `1.107.1`, `1.140.0`, and `1.145.3`, and map other valid semver versions in `package.json` to the closest verified baseline instead of skipping.
7. **Streamlined Skill & CLI Workflow**: Add `one-tone sync` and `one-tone rollback [--latest]` to the CLI while keeping `preview`, `apply`, `verify`, and `rollback <transaction_id>` intact. Keep popup selection strictly at the Agent Skill layer.
