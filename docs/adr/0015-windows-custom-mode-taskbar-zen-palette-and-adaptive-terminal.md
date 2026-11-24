# ADR 0015: Windows Custom Mode for native taskbar accent, Zen palette refinement, adaptive Terminal, and bug fixes

## Status

Accepted — 2026-11-19; revises [ADR 0004](0004-appearance-safe-palette.md), [ADR 0006](0006-mode-coherence-and-system-following.md), [ADR 0009](0009-portable-shell-integration-and-taskbar-mode-recovery.md), [ADR 0011](0011-single-plugin-antigravity-and-standard-editor-paths.md), and [ADR 0014](0014-windows-desktop-wallpaper-mode-matching-and-palette-refinement.md); single-value surface mode matching revised by [ADR 0017](0017-mode-independent-single-value-surfaces.md).

## Context

Live Windows 11 inspection and user review surfaced several architectural tensions and concrete defects:

1. **Taskbar accent loss on mode switch**: Windows 10/11 Settings disables and actively resets `Personalize\ColorPrevalence` to `0` whenever `SystemUsesLightTheme = 1` (Light Shell). Previously, `WindowsAdapter` bypassed Settings by writing `ColorPrevalence = 1` without touching `SystemUsesLightTheme`, so opening Settings wiped the taskbar accent. Native Windows Custom Mode (`SystemUsesLightTheme = 0`, `AppsUseLightTheme` preserved) is the only daemon-free way Windows natively supports and preserves taskbar accent color alongside Light apps.
2. **Wallpaper matching under Custom Mode**: Once `SystemUsesLightTheme` is set to `0` for native taskbar accent display, matching desktop wallpaper to `SystemUsesLightTheme` (ADR 0014) would pair a Dark wallpaper with Light apps. Desktop wallpaper and desktop fallback background should instead follow `AppsUseLightTheme`.
3. **Windows `AccentPalette` defects and overly darkened Shell accent**: Live Windows 11 registry inspection confirmed `AccentPalette` uses 8 slots of `[R, G, B, 0]` ordered lightest-to-darkest (`Light3, Light2, Light1, Base, Dark1, Dark2, Dark3, Extra`). The current code wrote reversed `[B, G, R, 0]` bytes in an inverted slot order and darkened `_shell_accent` in sRGB to `4.5:1` with +20% white headroom, turning vivid seeds like `#22C55E` into muddy `#00672E` and inverting hues on non-symmetric colors.
4. **Zen palette polish vs rigid decorative thresholds**: Forcing `1.2:1` WCAG contrast between every adjacent large surface and `3:1` on all structural borders and selections made Light surfaces murky (`#D7E6D9`), Dark surfaces washed out (`L = 0.30..0.38`), editor dividers heavy, and Seed-colored syntax tokens collide with fixed semantic hues (e.g. green `keyword` vs `string`).
5. **Windows Terminal & PSReadLine Light/Dark adaptation**: ADR 0011 locked Windows Terminal to `One Tone Dark` and hardcoded Dark PSReadLine prediction colors. Users switching Windows App mode expect Terminal and PSReadLine (both predictions and core syntax tokens like `Command`/`Parameter`/`Comment`) to follow `AppsUseLightTheme` seamlessly without yellow-on-light readability regressions.
6. **Cross-target bugs and high-value gaps**:
   - `WindowsAdapter.rollback()` omitted `refresh_theme()`, and multi-monitor `snapshot()` only saved monitor 0's wallpaper.
   - `VSCodeFamilyAdapter` and `TerminalAdapter` used strict `json.loads()` and failed on JSONC comments/trailing commas.
   - `VSCodeFamilyAdapter.verify()` always reported `partial` even for plain VS Code (`ai_panel_supported` defaulted to `False`), and `tokenColors` had only 8 minimal TextMate scopes.
   - `TerminalAdapter._discover_native_correction()` depended on `pwsh` just to read `wt.exe`'s Win32 file version.
   - `ChromeAdapter._tint()` passed raw HLS lightness instead of Chromium's `0.5`-neutral HSL shift semantics, and gave Light/Dark manifests identical display names.
   - `CodexAdapter` skipped valid `~/.codex/config.toml` files that had not yet initialized desktop theme tables.

## Decision

1. **Windows Custom Mode for Native Taskbar Accent (revises ADR 0006, 0009, 0014)**:
   - On Apply, `WindowsAdapter` sets `SystemUsesLightTheme = 0` (Dark Shell) and `Personalize\ColorPrevalence = 1` while **preserving `AppsUseLightTheme`** (App mode) and remaining strictly zero-daemon.
   - Snapshot records the original `SystemUsesLightTheme`, all managed registry keys, and per-monitor wallpaper paths; Rollback restores all of them (including per-monitor wallpapers) and calls `refresh_theme()`.
   - `Effective Windows mode` for desktop wallpaper, desktop fallback background, `AccentColorInactive`, and Antigravity `hubSurfaceBackgroundColor` follows `AppsUseLightTheme` (falling back to `plan.mode`).
2. **Correct Windows 8-Slot `AccentPalette` & `>= 3.0:1` Icon-Safe Shell Accent**:
   - Write `AccentPalette` in genuine Windows `[R, G, B, 0]` byte order and `[Light3, Light2, Light1, Base, Dark1, Dark2, Dark3, Extra]` slot order.
   - Derive `shell_accent` in OKLCH targeting WCAG `>= 3.0:1` non-text/graphical icon contrast against white glyphs (preserving Seed hue and vibrancy while keeping taskbar/Quick Settings icons crisp), and derive inactive titlebar color from the effective App mode's `surface_subtle`.
3. **Zen Palette Refinement (revises ADR 0004, 0014)**:
   - Keep strict text readability floors: dense primary text `>= 7:1` and functional/secondary/semantic/state text `>= 4.5:1`.
   - Use clean perceptual OKLCH tone ladders for Light surfaces (bright, airy) and Dark surfaces (deep, calm) without forcing rigid `1.2:1` luminance jumps on decorative large areas.
   - Separate low-prominence `Structural border` (`border`) from high-contrast `Interactive boundary` (`accent` / focus ring `>= 3:1`), soften `selection_background` while keeping `selection_foreground >= 4.5:1`, make non-text semantic fills mode-aware, and prevent Seed-hue collisions between `accent_text` and fixed semantic text hues (`success_text`, `info_text`, `error_text`, `warning_text`).
4. **System-Following Windows Terminal & Adaptive PSReadLine (supersedes ADR 0011 Decision #3)**:
   - On Windows Terminal `>= 1.17`, set top-level `theme` to `{"light": "One Tone Light", "dark": "One Tone Dark"}`; on `>= 1.16`, set `colorScheme` to `{"light": "One Tone Light", "dark": "One Tone Dark"}` across defaults, profiles, and `unfocusedAppearance`.
   - Update the managed PowerShell 7 `$PROFILE` block (`WT_SESSION` guarded) to read `AppsUseLightTheme` at startup and apply matching Light or Dark colors for both PSReadLine predictions and core syntax tokens (`Command`, `Parameter`, `Operator`, `Variable`, `String`, `Number`, `Comment`, `Keyword`, `Member`, `Type`, `Error`, `Selection`, `Emphasis`, `Default`).
   - Query `wt.exe` version via Win32 `GetFileVersionInfoW` (`ctypes.windll.version`) with `pwsh` fallback so Terminal capability discovery does not fail when `pwsh` is absent.
5. **Cross-Target Reliability & Coverage Fixes**:
   - Support JSONC comments and trailing commas in VS Code family and Windows Terminal settings readers.
   - Set `ai_panel_supported = True` for `vscode` (reporting `ok` on full verification) while keeping `trae` and `antigravity-ide` `partial` for private AI panels; expand TextMate `tokenColors` for common non-semantic languages (Markdown, JSON, YAML, HTML/JSX, CSS, punctuation/operators); align initial `workbench.colorTheme` with current `AppsUseLightTheme`.
   - Fix `ChromeAdapter._tint()` to Chromium's `0.5`-neutral HSL shift contract and label Light/Dark manifest names explicitly (`One Tone <plan_id> Light` / `Dark`).
   - Allow `CodexAdapter` to safely initialize missing `[desktop.appearanceLightChromeTheme]` / `[desktop.appearanceDarkChromeTheme]` tables in an existing valid `~/.codex/config.toml` and safely update inline `semanticColors`.
   - Bump `APPEARANCE_POLICY` revision (`2026-11-19.v6`) so older Plans must be regenerated through Preview while historical Rollback remains independent.

## Consequences

- Light-app users get Light desktop wallpapers, Light apps/editors/Terminal, AND a genuinely native, persistent accented taskbar without running any background daemon.
- Switching between Light and Dark apps via Windows "Default app mode" keeps the taskbar accent intact while editors, Terminal, ChatGPT App, and Antigravity switch automatically; re-running `sync` updates wallpaper and single-mode surfaces.
- Windows Shell accents render with accurate RGB hues across Start, Taskbar, Titlebar, and Quick Settings, and Rollback cleanly restores original Shell mode, per-monitor wallpapers, and refreshes Explorer immediately.
- Editor, Terminal, and Chrome themes become visibly calmer, cleaner, and less error-prone on real user configs (including JSONC comments and fresh ChatGPT App installs).

## Rejected Alternatives

- **Running a background watcher/scheduled task to re-apply colors on Windows mode change**: rejected to preserve the zero-daemon, predictable transaction model.
- **Forcing `Personalize\ColorPrevalence = 1` under Light Shell (`SystemUsesLightTheme = 1`)**: rejected because Windows Settings actively overwrites it back to `0` and resets `StartColorMenu`.
- **Leaving classic Win32 `Control Panel\Colors\Hilight` managed**: deferred because it affects legacy Win32 dialogs and requires sign-out to fully apply.
