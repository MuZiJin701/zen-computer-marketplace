# Architecture

## Marketplace shape

The repository root contains the shared Marketplace index, documentation and test harness. The index points at the single installable Plugin under `plugin/` (which Antigravity also installs directly). [ADR 0012](adr/0012-single-plugin-package-layout.md) defines the package boundary. [ADR 0013](adr/0013-cross-agent-plugin-distribution.md) defines the distribution channels.

~~~text
.
├─ .claude-plugin/marketplace.json
├─ plugin/
│  ├─ plugin.json
│  ├─ .claude-plugin/plugin.json
│  ├─ README.md
│  └─ skills/zen-one-tone-windows/
│     ├─ SKILL.md
│     ├─ agents/
│     ├─ references/
│     ├─ scripts/
│     └─ runtime project
├─ tests/
│  ├─ test_marketplace.py
│  ├─ test_plugin.py
│  ├─ test_skill.py
│  └─ runtime/
├─ docs/
│  ├─ agents/
│  ├─ specs/
│  ├─ adr/
│  ├─ architecture.md
│  └─ testing.md
├─ CONTEXT.md
└─ pyproject.toml
~~~

The Plugin is the installable envelope. The Skill is the independently distributable capability. A Skill runtime belongs inside its Skill package; it must not depend on the Marketplace root or another Plugin.

## Runtime seams

- Plan Palette generation is the highest shared Seam for Seed Color, Mode and Visual role calculation.
- Each Target Adapter is the next Seam for mapping public Color fields to Palette roles and for Detect, Snapshot, Apply, Verify and Rollback.
- Transaction persistence is the safety Seam; it records each Target operation and keeps compensation local to the failed Target.
- Field inventory is the documentation and testing Seam; it defines expected coverage without coupling tests to private implementation helpers.
- Marketplace metadata is the installation Seam; it points to the `zen-one-tone-windows` Plugin envelope but does not contain runtime logic.

Do not add a shared runtime or cross-Plugin import layer. Reuse repository tooling and documentation conventions, not hidden runtime coupling.

## Responsibilities

- Marketplace indexes list the installable `zen-one-tone-windows` Plugin.
- The Plugin package provides host metadata and contains the Skill.
- Skill package: provide instructions, references, launcher and runtime for one capability.
- Root test harness: run repository-wide marketplace, Plugin, Skill and runtime tests.
- Palette: generate explicit Light/Dark Visual roles, preserve Mode coherence across one Seed Color, limit corresponding large-area OKLCH lightness difference to `0.75`, enforce `muted_foreground` hierarchy (`ΔE_OK >= 0.08` from `foreground`), keep Light surfaces airy and Dark surfaces deep/calm with clean perceptual OKLCH steps, separate low-prominence `border` from `>= 3:1` interactive `accent`, keep semantic text hues (`accent_text`, `error_text`, `warning_text`, `success_text`, `info_text`, `purple_text`, `cyan_text`) distinct without Seed collisions, and validate text, region separation and cross-Mode appearance.
- Plan: hash Seed Color, both Mode Palettes, selected Targets, resolved instances, actual field capabilities and the current Appearance policy. Older policies or changed field contracts require Preview before any Transaction/Snapshot is created. Historical Transaction Rollback remains independent of Plan loading. `palettes` is the only persisted Palette representation; `mode` is a presentation default, not a Windows-mode switch.
- Storage: validate safe path components, parse JSONC (`strip_jsonc`/`loads_jsonc`), patch top-level JSONC keys while preserving comments (`patch_jsonc_object` with semantic verification and safe fallback), and perform atomic text/byte persistence (`atomic_write_text`/`atomic_write_bytes`).
- Transaction: journal Apply operations with JSON-safe report values, preserve Snapshots and coordinate compensation.
- Target Adapters: map public field inventories to Palette roles, resolve one Active Target instance during Preview (including `chatgpt-app` `config_path`), and report field-level capability across `windows`, `terminal`, `vscode`, `trae`, `antigravity-ide`, `chatgpt-app`, `antigravity`, `matlab`, and `chrome`.
- The MATLAB Adapter (`matlab`) manages `>= R2025a` Web desktop releases (verified on `R2026a`) via atomic offline updates to `matlab.mlsettings` (OPC ZIP), freezing absolute `settings_path` and valid `>= R2025a` `release` in Preview (rejecting invalid XML `<release>` values without folder-name fallback and rejecting directory/archive release mismatches during auto-discovery), strictly validating ZIP member uniqueness, `filesystemManifest.xml`, and managed `settings.json` groups including `isVector` shape and value encodings (fail-closed on corruption, with `Verify` reporting `failed` when a locked instance becomes corrupted), setting `matlab.appearance.MATLABTheme = "System"`, dual-mode `DesktopColors` and `SyntaxHighlightingColors` (enforcing `>= 7:1` body contrast and `>= 4.5:1` syntax contrast across `BackgroundColor`, `HighlightCurrentLineColor`, `AutofixHighlightColor`, and `VariableHighlightColor`), and Light RGB mirror keys while preserving `GraphicsTheme`, fonts, and feature toggles. `Verify` requires `hasValue = true` and expected `isVector`. Toolstrip/header chrome stays untouched (`unsupported`, reporting `partial` and `rendering_verification = untested`). During write operations (`sync`/`apply`/`rollback`), `Managed process shutdown` closes running `MATLAB.exe` processes (graceful up to 3s, then forceful, without auto-relaunch), while entry and pre-`os.replace` fail-closed `Live-process write guard` checks (requiring `ERROR_NO_MORE_FILES` on `Process32NextW`) block Apply (`skipped`, `changed = false`, no bogus `auto_rollback`) and Rollback (`failed`) if enumeration fails or the process remains alive; Rollback treats Snapshot's `settings_path` as authoritative (failing on adapter/metadata path mismatch) and restores only managed keys and `DesktopColors`/`SyntaxHighlightingColors` managed subkeys (including for legacy snapshots lacking `kind`/`modes`) so post-Apply user changes (including unmanaged colors) are preserved. Untouched skipped targets and already-verified restored targets are skipped during `TransactionStore.rollback` retries rather than failing or duplicating restoration, and `TransactionStore.latest_transaction_id()` skips zero-modification or fully auto-compensated failed transactions so `rollback --latest` selects the latest restorable transaction.
- The Chrome Adapter (`chrome`, Windows Google Chrome only, `verified-chrome-preferences-v1`) freezes one active Profile `Preferences` file in Preview (`ONE_TONE_CHROME_PREFERENCES` > `Local State` `profile.last_used` > `Default`, without guessing Edge/Brave or other Chromium browsers), writes 5 managed keys (`color_scheme2 = 0`, `color_variant2 = 1` `kTonalSpot`, `follows_system_colors = false`, signed 32-bit ARGB `user_color2` from `Seed Color`, `extensions.theme.id = "user_color_theme_id"`) and removes 5 conflicting override keys (`is_grayscale2`, `extensions.theme.pack`, `autogenerated.theme.color`, `ntp.custom_background_dict`, `ntp.custom_background_local_to_device`) without touching `Secure Preferences`, `Sync Data`, or `account_values`, runs `Managed process shutdown` on `chrome.exe` during write operations (graceful 3s -> forceful -> no relaunch) alongside entry and pre-`os.replace` fail-closed `Live-process write guard` + unredirected-path/digest continuity checks, surfaces honest Chrome Sync caveats (`saved_local_theme` / `account_values`), reports `ok` on verified match (`rendering_verification = untested`), and performs Snapshot-path-bound field-level Rollback without legacy MV3 extension compatibility.
- The Terminal Adapter also owns an optional Shell/PSReadLine sub-capability: Preview discovers the PowerShell 7 `pwsh` Profile and public prediction color fields, while Apply/Verify/Rollback use the Plan-persisted inputs and preserve unrelated Profile content. The managed `WT_SESSION` block reads `AppsUseLightTheme` at startup to select matching Light/Dark colors for both predictions and core PSReadLine syntax tokens. Default discovery excludes Windows PowerShell; explicit executable overrides must also verify as Core >= 7. Missing PowerShell 7 skips the prediction sub-capability, without changing the user's default Terminal Profile.
- Terminal native foreground correction is discovered from the executable version resource during Preview (preferring Win32 `GetFileVersionInfoW` with `pwsh` fallback, including Scoop shims). Windows Terminal >= 1.16 supports `adjustIndistinguishableColors = always` and paired `{"light", "dark"}` `colorScheme`; >= 1.17 supports paired `{"light", "dark"}` `theme`; unknown/older versions preserve unsupported settings and report partial. Resolved executable, version and capability are persisted in the hashed Terminal instance; Apply/Verify do not probe another host. Defaults, every Profile and existing unfocused appearances follow Windows App mode via paired `One Tone Light` / `One Tone Dark` Schemes and window themes. JSON restoration uses the existing atomic text writer; Profile write failure fails the Target and invokes transaction compensation.
- Explicit Light/Dark Palette `foreground` enforces 7:1 on `surface`; the legacy omitted-Mode generator retains its existing contract. Terminal black uses `surface`, white/brightWhite use `foreground`, and brightBlack uses `muted_foreground`, protecting primary/white text on black backgrounds and reverse pairs. A single ANSI table cannot satisfy every program-selected pair; native correction is not a guarantee of the acceptance thresholds.
- Configuration matching and rendering acceptance are independent. Terminal, ChatGPT App, and Antigravity results carry `rendering_verification = untested`. The App's embedded xterm reads its own CSS color tokens; the verified desktop TOML schema exposes no supported full ANSI/minimum-contrast setting. It remains unsupported without editing application bundles or guessing private fields. Local program configuration is added only after a named/versioned program is reproduced and a supported configuration seam is found.
- Editor instance resolution: prioritizes the standard C-drive user configuration (`%APPDATA%\<App>\User\settings.json` and `~/.<app>/extensions`) while keeping existing Scoop portable `data/` or launcher directories in `mirror_targets` for synchronized Snapshot/Apply/Verify/Rollback without altering Scoop's directory structure. Discovers the launcher's Workbench metadata (including commit-hashed resource subdirectories) and normalizes `1.x` versions (`<1.140` -> `1.107.1`, `>=1.140` -> `1.140.0`).
- CLI: expose `sync` (`Preview → Apply → Verify`, preserving `skipped` status for targets that did not write), `preview`, `apply`, `verify` and `rollback [--latest]` without bypassing the safety workflow, and emit recursively JSON-safe machine-readable reports.

## Test layout

The distributable `vscode_fields.json` is the single explicit per-field mapping for public color roles, conditions, baselines and actual-background pairings. The independent test fixture stores the pinned public ID set, documentation hash, transparency constraints and source-derived registrations. Runtime inventory and generators reuse the mapping; tests compare generated artifacts against the independent source inventory. Terminal inventory likewise reuses its generation tables rather than parallel manual key lists.

Appearance policy v11 (`2026-11-25.v11`) extends v10 by adding default write-phase `Managed process shutdown` (`graceful_3s_then_force_no_relaunch`) for `chrome` and `matlab`, expanding Chrome cleanup to `ntp.custom_background_dict` and `ntp.custom_background_local_to_device`, freezing `chatgpt-app` `config_path` in Plan instances, upgrading `antigravity` / `chatgpt-app` / VS Code family rollbacks to atomic and field/entry-level restoration, preserving JSONC comments in editor and Terminal `settings.json` with safe fallback, and optimizing dual-mode palette generation (`generate_mode_palettes`), while retaining Chrome's native `Preferences` (`user_color2`, `kTonalSpot`, `color_scheme2 = 0`), mode-independent single-value OKLCH surfaces (`mode_independent_surface`, `mode_independent_inactive_titlebar`, Shell accents / 8-slot `AccentPalette`) without adding a daemon, `matlab.contrast_guard`, `matlab.MATLABTheme = "System"`, Windows transparency disabling, Windows Custom Mode (`SystemUsesLightTheme = 0`, preserving `AppsUseLightTheme`), `IDesktopWallpaper` per-monitor wallpaper/background snapshot/apply/verify/rollback (using compact `64x64` solid PNGs and non-destructive rollback on existing system wallpapers), version/platform-gated solid Terminal fields with paired system-following `One Tone Light` / `One Tone Dark` themes/schemes and adaptive PSReadLine syntax/prediction colors, and App `system` appearance. Font/display preferences and unknown keys are preserved; ChatGPT App safely initializes missing theme/font tables on valid `config.toml`. Windows distinguishes actual App/Shell modes and uses SPI_GETHIGHCONTRAST; unknown/active high contrast skips. Registry mechanisms are reported separately from public stable schemas. Editor overlays retain alpha; contrast checks use the composited background, with semantic Diff/Merge regions kept distinct; `vscode` and `chrome` report `ok` on verified standard coverage while `trae`/`antigravity-ide`/`matlab` keep `partial` for unsupported chrome/AI surfaces. Chrome uses a `Seed-driven native theme` (`kTonalSpot`) following Windows Light/Dark switches natively.

Verify compares complete Light/Dark artifacts and exact editor contributions, rather than representative frame colors. Preview reports actual capabilities and generated values without writing artifacts. Private AI fields, Chrome Sync cloud overrides and Chromium-derived palette colors, and full embedded-terminal controls remain limited; rendering remains untested. See [field evidence](theme-field-coverage-evidence.md).

The root `tests/` files check Marketplace registration, the Plugin envelope and the independently installable Skill. `tests/runtime/` exercises the Skill runtime with its fixtures. The root harness and Skill runtime have separate uv projects.
