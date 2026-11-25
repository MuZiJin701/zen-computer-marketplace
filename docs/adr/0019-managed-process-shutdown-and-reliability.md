# ADR 0019: Managed process shutdown, Chrome NTP cleanup, and cross-target reliability

## Status

Accepted — 2026-11-25; supersedes the non-termination clauses of [ADR 0016](0016-matlab-desktop-mlsettings-target.md) and [ADR 0018](0018-chrome-native-preferences-dynamic-theme.md).

## Context

1. **Workflow continuity blocked by running `chrome.exe` and `MATLAB.exe`**: Under [ADR 0016](0016-matlab-desktop-mlsettings-target.md) and [ADR 0018](0018-chrome-native-preferences-dynamic-theme.md), One-Tone refused to terminate running Chrome or MATLAB processes, returning `skipped` on Apply and `failed` on Rollback. In interactive Skill usage (`sync`, `apply`, `rollback`), background Chrome processes (tray/extension hosts) and open MATLAB sessions repeatedly interrupted one-step harmonization and rollback.
2. **Chrome New Tab Page custom backgrounds mask the unified color theme**: Chromium's `ThemeService` applies `user_color2`, but user-configured `ntp.custom_background_dict` and `ntp.custom_background_local_to_device` in `Preferences` continue painting custom background images over the New Tab Page.
3. **Cross-target reliability & performance gaps**:
   - `_sync()` re-ran `verify_plan()` unconditionally across all `plan.targets`, misreporting `skipped` (unmodified) targets as `failed` instead of preserving `skipped`.
   - `WindowsAdapter.rollback()` unconditionally copied backed-up wallpapers over `old_path` / `dest_path`, failing with `PermissionError` when the user's original wallpaper resided in read-only Windows system directories (`C:\Windows\Web\Wallpaper\...`), and `generate_wallpaper()` wrote oversized `1920x1080` PNGs non-atomically.
   - `CodexAdapter` did not freeze `config_path` into `Plan.target_instances`, and `CodexAdapter`, `AntigravityAdapter`, and `VSCodeFamilyAdapter` performed whole-file `shutil.copy2` rollbacks rather than atomic/field-level restoration.
   - `VSCodeFamilyAdapter` and `TerminalAdapter` rewrote `settings.json` with `json.dumps()`, stripping user JSONC comments.
   - `create_plan()` invoked `generate_palette()` separately for Light and Dark, computing both modes twice.

## Decision

1. **Adopt default `Managed process shutdown` for `chrome` and `matlab` during write phases**:
   - During `Apply`, `sync`, and `Rollback` only (never during `Preview`, `Detect`, or `Verify`), when `chrome.exe` or `MATLAB.exe` is detected as running, One-Tone sends a graceful termination signal first (`taskkill /IM <exe> /T`) and polls for up to 3 seconds; if the process remains alive, it forcefully terminates the process tree (`taskkill /F /IM <exe> /T`) and re-verifies process exit before touching target files.
   - Applications are **not** automatically relaunched afterward.
   - `Live-process write guard` remains strictly **fail-closed**: if initial or post-shutdown Win32 process enumeration fails (`unknown`) without invoking termination, or if the process survives shutdown, writes are blocked and `os.replace` pre-checks continue guarding against mid-write process restarts or concurrent file replacement.
2. **Expand Chrome managed cleanup to New Tab Page background keys (`10` managed keys total)**:
   - Keep single active-Profile discovery (`ONE_TONE_CHROME_PREFERENCES` > `Local State` `profile.last_used` > `Default`) and keep `Secure Preferences`, `Sync Data/LevelDB`, and `account_values` untouched.
   - Add `ntp.custom_background_dict` and `ntp.custom_background_local_to_device` to Chrome's managed removal keys on `Apply` and field-level restoration (including empty `ntp` container cleanup) on `Rollback`.
3. **Fix `sync` status fidelity, Windows wallpaper rollback, `chatgpt-app` freezing, and upgrade Rollback across adapters**:
   - `_sync()` reuses internal `apply_plan` verify outcomes and preserves `skipped`/`failed` status for targets that never wrote, rather than marking skipped targets as `failed`.
   - `WindowsAdapter.rollback()` only restores original wallpaper files from snapshot when the target path is missing, avoiding `PermissionError` on read-only system wallpapers; `generate_wallpaper()` defaults to `64x64` and uses `atomic_write_bytes`.
   - `CodexAdapter` exposes and freezes `target_instance()` (`config_path`) in Preview/Plan when present in `target_instances`, and rolls back atomically.
   - `AntigravityAdapter` and `VSCodeFamilyAdapter` perform atomic, field-level / `extensions.json` entry-level Rollback (while retaining fallback for legacy snapshots), preserving post-Apply user preferences and newly installed extensions.
4. **Preserve JSONC comments on `vscode`, `trae`, `antigravity-ide`, and `terminal` with safe fallback**:
   - Implement a zero-dependency JSONC key-patching helper (`patch_jsonc_object`) that updates/inserts/removes targeted top-level keys in place while keeping `//` and `/* */` comments and indentation intact, verifies semantic equivalence via `loads_jsonc`, and safely falls back to `json.dumps()` if verification fails.
5. **Optimize palette generation and bump metadata revisions**:
   - Add `generate_mode_palettes(seed_color)` so `create_plan()` builds Light and Dark palettes in one shared pass and aligns `_channel_luminance` with the `0.04045` sRGB linearization threshold.
   - Bump `APPEARANCE_POLICY` to `2026-11-25.v11` (`chrome = "native_preferences_system_following_tonal_spot_clean_ntp"`, `live_process_shutdown = "graceful_3s_then_force_no_relaunch"`) and `_INVENTORY_VERSION` to `2026-11-25.v5`.

## Consequences

- `sync`, `apply`, and `rollback` no longer stall on background `chrome.exe` or active `MATLAB.exe` sessions while keeping read-only commands and fail-closed safety intact.
- Users with running MATLAB sessions must save unsaved workspace state before running `sync`/`apply`/`rollback`, since an unresponsive process after the 3-second graceful window is forcefully terminated.
- Chrome New Tab Pages consistently display the seed-derived solid surface without leftover custom background images, and roll back cleanly.
- Rollback across all desktop targets is atomic, non-destructive to read-only system wallpapers, and preserves post-Apply edits and extensions.
- Older `v10` and earlier Plans require fresh Preview under `2026-11-25.v11`, while historical Transaction Rollback remains independent.

## Rejected Alternatives

- **Keeping Chrome/MATLAB strictly manual-close only**: rejected because background Chrome tray processes and live sessions broke single-step `sync` and `rollback` continuity.
- **Immediate `taskkill /F` without graceful window**: rejected because Chrome triggers "Restore pages" recovery bars and MATLAB loses its chance to flush clean exit state.
- **Auto-relaunching Chrome after write**: rejected to avoid unprompted browser windows or interfering with non-graphical/scripted runs.
- **Syncing all Chrome profiles in `Local State`**: deferred; single active Profile remains cleaner and lower-risk.
- **Failing `Apply` if JSONC comment patching cannot handle unusual syntax**: rejected in favor of semantic verification with safe fallback to standard JSON formatting.
