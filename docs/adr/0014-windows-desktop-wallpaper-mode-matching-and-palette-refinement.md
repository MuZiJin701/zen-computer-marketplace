# ADR 0014: IDesktopWallpaper multi-monitor sync, effective Windows mode matching, and OKLCH palette refinement

## Status

Accepted — 2026-11-19; extends [ADR 0004](0004-appearance-safe-palette.md), [ADR 0006](0006-mode-coherence-and-system-following.md), [ADR 0010](0010-evidence-backed-appearance-policy.md), and [ADR 0011](0011-single-plugin-antigravity-and-standard-editor-paths.md).

## Context

Real Windows 11 dual-monitor verification revealed four defects:

1. `WindowsDesktopBackend.set_wallpaper()` only invoked legacy `SystemParametersInfoW(SPI_SETDESKWALLPAPER, ...)` and `verify()` only read `HKCU\Control Panel\Desktop\WallPaper`. When Windows Explorer was in an empty-wallpaper solid-black state (`Custom.theme` with `Wallpaper=` and `Background=0 0 0`) across multiple monitors, `IDesktopWallpaper` remained empty (`""`) with `#000000` background even though registry `verify` passed.
2. `WindowsAdapter` and `AntigravityAdapter` (`hubSurfaceBackgroundColor`) always read `plan.palette_for(plan.mode)` (defaulting to `"dark"`), applying Dark-mode wallpapers, backgrounds, and accents even when the user's Windows Shell or App mode was Light.
3. In `palette.py`, `muted_foreground` collapsed visually onto `foreground` (`ΔE_OK < 0.012`), Light tonal surfaces were slightly muddy while Light accents sacrificed chroma before lightness (`#22C55E` degraded to grayish `#648068`), and Terminal/VS Code ANSI `blue`/`purple`/`cyan` all collapsed onto `accent_text`.
4. `TerminalAdapter` hardcoded `"applicationTheme": "dark"` inside the registered `One Tone Light` window theme.

## Decision

1. **Modern `IDesktopWallpaper` COM Integration**: Use the Windows `IDesktopWallpaper` COM interface (via stdlib `ctypes`, zero external dependencies) to set generated solid PNG wallpapers across all monitors (`SetWallpaper`), synchronize the desktop fallback color (`SetBackgroundColor`), and verify per-monitor wallpaper state and background color during `verify()`. Keep `SystemParametersInfoW` in sync for legacy registry readers and as a fallback when COM is unavailable. Snapshot and rollback preserve prior wallpaper paths and background colors.
2. **Effective Windows Mode Matching Without Mutating System Mode**:
   - Windows wallpaper, background color, and Shell accents select the effective Mode from current `SystemUsesLightTheme` (falling back to `AppsUseLightTheme`, then `plan.mode`), without modifying Windows light/dark switches or introducing any background daemon.
   - Antigravity `hubSurfaceBackgroundColor` selects the effective Mode from current `AppsUseLightTheme` (recorded in the hashed `antigravity` target instance during Preview, falling back to `plan.mode`).
3. **OKLCH Palette & Syntax/ANSI Separation**:
   - Generate `muted_foreground` with clear visual hierarchy (`ΔE_OK >= 0.08` from `foreground` while preserving `>= 4.5:1` contrast).
   - Brighten Light tonal surfaces cleanly (`L ≈ 0.825..0.976` with controlled chroma) and prioritize Seed chroma preservation in `_contrast_safe_accent()` so Light and Dark accents remain vivid without losing Seed hue.
   - Add distinct semantic text roles (`info_text`, `purple_text`, `cyan_text`, all `>= 4.5:1` on `surface`) and map Terminal and VS Code ANSI blue/purple/cyan plus editor syntax tokens (`function`, `type`, `keyword`, `string`, `constant`) to visually distinguishable roles.
4. **Windows Terminal Light Theme Fix**: Set `window.applicationTheme` in `_theme_colors()` to match each registered theme's own mode (`"light"` for `One Tone Light`, `"dark"` for `One Tone Dark`), while keeping `One Tone Dark` as the default active Terminal theme per ADR 0011.
5. **Preserve ChatGPT App Code Theme Enum**: Keep `desktop.appearanceLightCodeThemeId` untouched because it accepts only built-in syntax theme identifiers rather than custom Palette colors.

## Consequences

- Multi-monitor Windows 11 desktops switch reliably from solid-black or prior image states, and `verify` catches real Explorer wallpaper mismatches instead of passing on stale registry values.
- Users on Light Windows receive Light wallpapers, Light accents, and a Light Antigravity Hub surface; switching Windows system light/dark later requires re-running `sync` (no background watcher).
- `APPEARANCE_POLICY` revision bumps to `2026-11-19.v5` so older Plans must be regenerated through Preview while historical Transaction Rollback remains independent.

## Considered Options

- **Switching Windows to native Solid Color mode without generating a PNG**: rejected because restoring a user's previous image wallpaper on Rollback becomes more fragile than managing per-monitor PNG + `SetBackgroundColor` via `IDesktopWallpaper`.
- **Adding a background task or service to auto-switch wallpapers on Windows mode change**: rejected to preserve the zero-daemon, predictable transaction architecture (ADR 0006/0009/0010).
- **Mutating `AppsUseLightTheme`/`SystemUsesLightTheme`**: rejected to preserve user sovereignty over Windows light/dark switches (ADR 0006).
