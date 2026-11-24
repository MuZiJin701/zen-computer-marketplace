# ADR 0017: Mode-independent single-value surfaces for Windows and Antigravity Hub

## Status

Accepted — 2026-11-24; revises [ADR 0014](0014-windows-desktop-wallpaper-mode-matching-and-palette-refinement.md) and [ADR 0015](0015-windows-custom-mode-taskbar-zen-palette-and-adaptive-terminal.md).

## Context

Under [ADR 0015](0015-windows-custom-mode-taskbar-zen-palette-and-adaptive-terminal.md), One-Tone switched Windows to native Custom Mode (`SystemUsesLightTheme = 0`, preserving user `AppsUseLightTheme`) so taskbar and Start accent colors persist natively without a background daemon. All dual-mode Targets (`terminal`, `vscode`, `trae`, `antigravity-ide`, `chatgpt-app`, `matlab`, and Antigravity `config.json`) automatically follow `AppsUseLightTheme` switches at runtime.

However, four single-value settings without paired Light/Dark storage slots remained coupled to the `AppsUseLightTheme` value observed at execution time (`Effective Windows mode`), alongside an indirect coupling in Shell accents:

1. **Desktop wallpaper & fallback background (`wallpaper`, `IDesktopWallpaper::SetBackgroundColor`, `Control Panel\Colors\Background`)**: generated a Light or Dark `surface` PNG/color matching `AppsUseLightTheme`.
2. **Inactive title bar (`AccentColorInactive`)**: read `surface_subtle` from the `effective_mode` Palette.
3. **Antigravity Hub surface (`hubSurfaceBackgroundColor` in `%APPDATA%\Antigravity\app_storage.json`)**: wrote Light or Dark `surface` based on `AppsUseLightTheme`.
4. **Windows Shell accents (`shell_accent`, `AccentPalette`, `AccentColor`, `AccentColorMenu`, `StartColorMenu`, `ColorizationColor`, `ColorizationAfterglow`)**: read `plan.palette_for(effective_mode)["accent"]` instead of deriving directly from `plan.seed_color`, even though `SystemUsesLightTheme` is fixed at Dark (`0`) and Shell glyphs are fixed white.

Because Windows and Antigravity `app_storage.json` expose only a single value for each of these fields, toggling `AppsUseLightTheme` later in Windows Settings created visual drift and caused subsequent read-only `verify` runs to fail until the user re-ran `sync`.

## Decision

1. **Derive single-value surfaces directly from `Seed Color` (mode-independent)**:
   - Introduce `mode_independent_surface(seed_color)` in OKLCH: a low-chroma, mid-dark tonal surface preserving the Seed hue (neutral for grayscale seeds) and guaranteeing WCAG `>= 4.5:1` contrast against `#FFFFFF` for desktop icon labels while staying calmer than raw saturated seeds and compatible with both Light and Dark foreground windows.
   - Apply `mode_independent_surface(plan.seed_color)` uniformly to the Windows generated wallpaper PNG, `IDesktopWallpaper::SetBackgroundColor`, `Control Panel\Colors\Background`, and Antigravity `hubSurfaceBackgroundColor`.
2. **Stepped mode-independent `AccentColorInactive`**:
   - Introduce `mode_independent_inactive_titlebar(seed_color, shell_accent=...)` in OKLCH: a same-hue, low-chroma surface stepped in lightness away from `mode_independent_surface` (`|ΔL| >= 0.06`) and separated from `shell_accent` while keeping `>= 4.5:1` against `#FFFFFF`, so unfocused native windows remain distinct from both the desktop wallpaper behind them and active title bars.
3. **Decouple Windows Shell accents from `AppsUseLightTheme`**:
   - Compute `shell_accent` and the 8-slot `AccentPalette` directly from `plan.seed_color` (protecting fixed white Shell glyphs at `>= 3.0:1`), rather than indexing into `plan.palette_for(effective_mode)`.
4. **Retire `Effective Windows mode` and bump `APPEARANCE_POLICY` to `2026-11-24.v9`**:
   - Remove `effective_windows_mode` and `antigravity.app_mode` tracking; Preview, Apply, and Verify no longer vary expected single-value outputs with `AppsUseLightTheme`.
   - Bump `APPEARANCE_POLICY` revision to `2026-11-24.v9` (replacing `windows.wallpaper_mode_matching` / `antigravity.hub_mode_matching` with `windows.single_value_surfaces` / `antigravity.hub_surface`) so older Plans must be regenerated via Preview while historical Transaction Rollback remains independent.

## Consequences

- Switching Windows App mode (`AppsUseLightTheme`) between Light and Dark after a single `sync` keeps all dual-mode apps auto-switching while single-value desktop surfaces, Shell accents, inactive title bars, and Antigravity Hub stay consistent and pass `verify` without re-running `sync` or running a background daemon.
- `WindowsAdapter` and `AntigravityAdapter` outputs are completely deterministic from `plan.seed_color` regardless of `plan.mode` or runtime `AppsUseLightTheme`.
- Older `v8` and earlier Plans are rejected at `load_plan` with `PlanIntegrityError` until re-previewed; existing Transaction Snapshots continue to roll back cleanly.

## Considered Options

- **Writing raw `Seed Color` directly to wallpaper, `AccentColorInactive`, and `hubSurfaceBackgroundColor`**: rejected because vivid or bright Seed Colors (e.g. `#39FF14`, `#FACC15`) make full-screen wallpapers glaring, obscure white desktop icon labels, and make `AccentColorInactive` collide with active title bars.
- **Deleting `AccentColorInactive` so Windows switches unfocused native title bars automatically, or leaving `hubSurfaceBackgroundColor` unmanaged**: rejected because the user prefers an explicit, Seed-harmonized, visibly bordered inactive title bar and a unified Antigravity Hub surface over unmanaged system gray defaults.
- **Adding a background daemon or scheduled task to rewrite wallpaper and registry keys on `AppsUseLightTheme` changes**: rejected to preserve the zero-daemon, deterministic transaction architecture (ADR 0006/0014/0015).
