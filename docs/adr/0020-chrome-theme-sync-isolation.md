# ADR 0020: Chrome theme sync isolation

## Status

Accepted — 2026-11-25; supersedes the Chrome Sync caveat / manual default-theme reset clause of [ADR 0018](0018-chrome-native-preferences-dynamic-theme.md); extends the Chrome `Preferences` boundary in [ADR 0019](0019-managed-process-shutdown-and-reliability.md).

## Context

Following [ADR 0018](0018-chrome-native-preferences-dynamic-theme.md) and [ADR 0019](0019-managed-process-shutdown-and-reliability.md), live verification on a signed-in Google Chrome desktop profile showed that writing a new Seed Color (green `#22C55E`, `user_color2 = -14498466`) to `Preferences` still reverted to the user's older purple cloud theme (`-8635667`) on launch when Chrome Sync held an active theme (`sync.themes = true` and `browser.theme.saved_local_theme` present).

Controlled live experiments against local Windows Google Chrome `158` (`Default` profile, with full backup/restore) established exact empirical facts:

1. **`sync.*` preferences are outside `Secure Preferences` HMAC protection**:
   - Inspecting `Secure Preferences` showed `"sync": {}` and `protection.macs.sync` = `None`. Modifying `sync.*` in `Preferences` leaves `Secure Preferences` `protection.macs` 100% intact.
   - By contrast, `account_values.browser` IS covered by `protection.macs.account_values`, so `account_values` must remain untouched. (Local `account_values.browser.theme` held `{"color_scheme": 0}` only.)
2. **Offline reset to the default Chrome theme while keeping `sync.themes = true` fails (Exp 2)**:
   - Removing `user_color2` / `browser.theme.saved_local_theme` and setting `extensions.theme.id = ""` offline while leaving `sync.themes = true` caused Chrome Sync on startup to overwrite `Preferences` back to the cloud-stored color and restore `browser.theme.saved_local_theme = "CAAQAEgB"` within seconds.
3. **Disabling `sync.themes` WITHOUT removing `browser.theme.saved_local_theme` also fails (Exp 1a / 1b1)**:
   - Setting `sync.keep_everything_synced = false`, `sync.themes = false`, and `sync.data_type_status_for_sync_to_signin.themes = false` while leaving `browser.theme.saved_local_theme = "CAAQAEgB"` caused Chromium's `ThemeSyncableService::StopSyncing()` to restore the saved local default theme on launch, clearing `user_color2` and setting `extensions.theme.id = ""`.
4. **Disabling `sync.themes` AND removing `browser.theme.saved_local_theme` succeeds across launches and consecutive seed changes (Exp 1b2 / 1c)**:
   - Setting `sync.keep_everything_synced = false`, `sync.themes = false`, and `sync.data_type_status_for_sync_to_signin.themes = false` AND deleting `browser.theme.saved_local_theme` alongside `user_color2 = -14498466` persisted green cleanly across full Chrome launch/close, preserved `bookmarks`/`passwords`/`extensions`/etc. as `true`, left `Secure Preferences` MACs intact, and allowed a subsequent offline seed change to sky blue (`#0EA5E9`, `-15817239`) to stick cleanly without cloud override.

## Decision

1. **Conditional automatic `Chrome theme sync isolation` during `Apply` (`chrome` Target)**:
   - Unconditionally remove `browser.theme.saved_local_theme` as part of Chrome's managed override cleanup.
   - Only when the active Profile's `Preferences` indicates active/configured Sync (`sync.has_setup_completed == true`, `sync.keep_everything_synced == true`, `sync.themes == true`, or `sync.data_type_status_for_sync_to_signin.themes == true`):
     - If `sync.keep_everything_synced` is not already `false`, set `sync.keep_everything_synced = false` and expand every missing key in Chrome's standard syncable data types (`apps`, `autofill`, `bookmarks`, `extensions`, `passwords`, `payments`, `preferences`, `reading_list`, `saved_tab_groups`, `tabs`, `typed_urls`) to `true`, while preserving any standard type the user had already set to `false`. (Note: Chrome 158 live testing covered `keep_everything_synced = false`; this `keep_everything_synced = true` expansion branch is derived from Chromium `SyncPrefs` source behavior and has not yet been live-tested against a `keep_everything_synced = true` Chrome account.)
     - Set `sync.themes = false`, and if `sync.data_type_status_for_sync_to_signin.themes` is present, set it to `false`.
   - Do **not** create a `sync` section on pure local non-synced profiles where no active sync indicator exists.
   - Continue to treat `Secure Preferences`, `Sync Data/LevelDB`, and `account_values` as strictly off-limits.
2. **Strict `Verify` enforcement and honest `sync_caveat` reporting**:
   - `Verify` requires `browser.theme.saved_local_theme` to be absent, and for profiles with Sync state (`_is_sync_tracked_for_verify`) strictly requires `sync.keep_everything_synced == false`, `sync.themes == false`, and `sync.data_type_status_for_sync_to_signin.themes == false` (when present). Re-enabling theme sync in Chrome causes `Verify` to report `failed`.
   - Clear `sync_caveat = false` once theme sync is isolated and `account_values.browser.theme` / `account_values.extensions.theme` contain no explicit theme/color override (ignoring benign `{"color_scheme": 0}`), surfacing `sync_caveat = true` only when drift or an unmanaged `account_values` theme override remains.
3. **Field-level Snapshot / Rollback with legacy snapshot compatibility**:
   - `Snapshot` records exact presence and values for `browser.theme.saved_local_theme`, `sync.keep_everything_synced`, `sync.themes`, `sync.data_type_status_for_sync_to_signin.themes`, and all 11 standard syncable data type keys (plus container presence flags for `sync` and `sync.data_type_status_for_sync_to_signin`).
   - `Rollback` restores every snapshotted key at field level (including restoring `keep_everything_synced = true` and removing newly expanded sync type keys while keeping post-Apply edits), while skipping newly added sync/override keys when rolling back older `v10`/`v11` snapshots that only recorded the 8 core keys.
4. **Inventory and `APPEARANCE_POLICY` revision bump (`2026-11-25.v12` / `2026-11-25.v6`)**:
   - Add `browser.theme.saved_local_theme` (`remove-override`, `display_property`) and the three sync isolation fields (`sync.keep_everything_synced`, `sync.themes`, `sync.data_type_status_for_sync_to_signin.themes`, `display_property`) to `FIELD_INVENTORY["chrome"]` and bump `_INVENTORY_VERSION` to `2026-11-25.v6`.
   - Bump `APPEARANCE_POLICY["revision"]` to `2026-11-25.v12` with `chrome = "native_preferences_system_following_tonal_spot_clean_ntp_sync_isolated"`.

## Consequences

- Signed-in Chrome users running `sync` automatically isolate theme sync without manual Customize Chrome intervention, while keeping bookmarks, passwords, extensions, tabs, and other synced data active.
- Toggling Chrome's "Themes" sync switch back on is surfaced deterministically as verification drift rather than silently failing on next launch.
- Chrome themes stop syncing across the user's other devices while One-Tone is applied; `Rollback` cleanly re-enables the prior sync configuration.
- Older `v11` and earlier Plans are rejected by `load_plan()` until refreshed via Preview, while existing transaction rollbacks continue to work independently.

## Rejected Alternatives

- **Offline reset to default Chrome theme while keeping `sync.themes = true`**: empirically disproved by Exp 2; Chrome Sync immediately restores the cloud theme.
- **Disabling `sync.themes = false` without removing `browser.theme.saved_local_theme`**: empirically disproved by Exp 1a/1b1; `StopSyncing()` restores the saved local default theme.
- **Setting enterprise Registry policies `SyncTypesListDisabled` or `BrowserThemeColor`**: rejected because enterprise policies trigger Chrome's "Managed by your organization" UI banner and lock user controls.
- **Mutating `Secure Preferences`, `account_values`, or `Sync Data/LevelDB`**: rejected because `account_values` and `Secure Preferences` are HMAC-protected and binary LevelDB mutation is fragile.
