# ADR 0016: MATLAB desktop (`matlab`) Target via offline `matlab.mlsettings` and live-process write guard

## Status

Accepted — 2026-11-22; extends [ADR 0006](0006-mode-coherence-and-system-following.md) and [ADR 0010](0010-evidence-backed-appearance-policy.md).

## Context

Starting with MATLAB R2025a (verified locally on R2026a / `26.1.0.3203278`), MathWorks replaced the legacy Java Swing desktop (`matlab.prf`) with a Web-based desktop storing user preferences inside `%APPDATA%\MathWorks\MATLAB\<release>\matlab.mlsettings` (an OPC ZIP archive containing `fsroot/settingstree/.../settings.json` and `metadata/filesystemManifest.xml`).

Isolated `MATLAB_PREFDIR` experiments against R2026a established four constraints:

1. **Dual-mode content/syntax colors exist, but window Chrome is fixed**: `matlab.appearance.MATLABTheme` supports `"System"` (following Windows Light/Dark via `prefers-color-scheme`), and the Colors preference panel persists independent `"light"` and `"dark"` overrides in `matlab.colors.DesktopColors` (`BackgroundColor`, `ForegroundColor`) and `matlab.colors.SyntaxHighlightingColors` (syntax, Command Window, Code Analyzer, `HighlightCurrentLineColor`, and `LineColor`), mirroring Light-mode RGB `[R G B]` (`int32`) keys under `matlab.colors.*`, `matlab.colors.commandwindow.*`, `matlab.colors.programmingtools.*`, and `matlab.editor.displaysettings.*`. However, Toolstrip, Header (`#004073`), Sidebar, and window chrome tokens live inside the installation bundle (`toolbox/matlab/ui_themes/resources/themes.json`) with no user-level override.
2. **Official CLI / extensions do not satisfy One-Tone's safety contract**: Windows `matlab -batch` forbids modifying settings; ordinary MATLAB launch has startup/migration side effects; and MathWorks' `matlab-color-theme-extensions` (`.p` scripts) binds each JSON file to a single `DesktopTheme` (`Light` or `Dark`) without clean dual-mode Snapshot/Rollback semantics.
3. **Offline OPC ZIP patching works cleanly**: Atomically patching `matlab.mlsettings` (updating target `settings.json` entries and `metadata/filesystemManifest.xml`) loads in MATLAB with zero warnings (`hasPersonalValue = 1` for all managed keys) and cleanly restores `hasPersonalValue = 0` on rollback.
4. **Live-process overwrite hazard**: A running `MATLAB.exe` does not hot-reload external `matlab.mlsettings` edits, and whenever that running session writes any unrelated setting (such as layout or recent files on exit), it serializes its in-memory settings tree back to disk and wipes external edits.

## Decision

1. **Add `matlab` as a default Target for verified `>= R2025a` Web desktop releases**:
   - Include `matlab` in the default Target set (expanding from 8 to 9). Uninstalled machines, legacy Java desktop releases (`<= R2024b`), uninitialized installations without an existing `matlab.mlsettings`, or unrecognized `mlsettings` schemas (`fsroot/schema.json != "com.mathworks/settings/jsonschema/1-1-0"`) safely report `skipped`.
   - Document this integration explicitly as a **verified runtime schema** (baselined on R2026a), not a MathWorks public file-format commitment.
2. **Single Active Target instance discovery (frozen in Preview)**:
   - Resolve the unique instance in Preview by deterministic precedence: (1) explicit override (`ONE_TONE_MATLAB_SETTINGS` or `MATLAB_PREFDIR`), (2) newest verified `>= R2025a` release with an existing valid `matlab.mlsettings` discovered via `HKLM\SOFTWARE\MathWorks\MATLAB\*` (`MATLABROOT` + `VersionInfo.xml`) and `%APPDATA%\MathWorks\MATLAB\R20*`. Persist the resolved instance in the hashed Plan; never fabricate a new `matlab.mlsettings` from scratch.
3. **Managed color boundary, zero bundle modification, honest `partial` status**:
   - Never modify MATLAB installation files (such as `themes.json`). Report window Chrome as `unsupported`, `rendering_verification = untested`, and overall verified target status as `partial`.
   - Set `matlab.appearance.MATLABTheme = "System"` and write Light/Dark overrides for `DesktopColors`, `SyntaxHighlightingColors` (including `HighlightCurrentLineColor` and `LineColor`), plus Light-mode RGB mirror keys. Preserve `matlab.appearance.figure.GraphicsTheme`, fonts, feature toggles (`HighlightCurrentLine`, `ShowLine`, `HighlightAutofixes`, `AutomaticallyHighlightVariables`, `ShowVariablesWithSharedScope`), and all unrelated settings.
4. **Live-process write guard**:
   - `Preview` and `Verify` remain strictly read-only and never spawn MATLAB.
   - Before `Apply` or `Rollback` writes `matlab.mlsettings`, check for a running `MATLAB.exe`. Never kill the user's process or silently write over disk state that will be clobbered on exit: `Apply` returns `skipped` with an explicit instruction to close MATLAB and retry, while `Rollback` fails closed (`failed`) so the user is never misled into believing rollback succeeded.
5. **Field-level Rollback with full Snapshot backup**:
   - Snapshot records both the original `matlab.mlsettings` archive and the exact pre-apply state (`present + value` vs `absent`) of every managed setting key.
   - Rollback performs **field-level restoration** inside the current `matlab.mlsettings` (restoring prior values or removing previously absent keys/entries and cleaning `filesystemManifest.xml`), preserving unrelated user changes made after Apply (such as `RecentFileList` or desktop layout).
6. **Bump `APPEARANCE_POLICY` revision**:
   - Record the `matlab` appearance policy in `APPEARANCE_POLICY` and bump its revision so older Plans require fresh Preview while historical Transaction Rollback remains independent.

## Consequences

- Windows MATLAB R2025a+ users get automatic Light/Dark content, editor, command window, and syntax harmonization following Windows App mode without modifying MATLAB binaries or running a background daemon.
- Toolstrip and header chrome remain native Light/Dark, honestly surfaced as `partial` / `unsupported`.
- Running MATLAB sessions are protected from silent data loss or overwritten themes, and rolling back a theme never wipes recent files or layout edits created after Apply.

## Rejected Alternatives

- **Invoking `matlab -batch` or launching MATLAB to write via the `settings` API**: rejected because `-batch` explicitly disallows settings modification on Windows and normal launches mutate state/run startup scripts, breaking read-only Preview/Verify and clean transaction boundaries.
- **Generating `matlab-color-theme-extensions` JSON artifacts only (manual import)**: rejected as the primary path because each JSON binds a single `DesktopTheme` and lacks dual-mode Snapshot/Rollback parity with other desktop Targets.
- **Whole-file `matlab.mlsettings` replacement on Rollback**: rejected because it would discard unrelated post-Apply user changes (`RecentFileList`, window layout, toolstrip preferences).
- **Patching `toolbox/matlab/ui_themes/resources/themes.json`**: rejected because modifying application installation bundles violates One-Tone's safety boundary and breaks on MATLAB updates.
