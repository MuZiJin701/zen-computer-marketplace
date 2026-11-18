# Zen Computer Marketplace

[简体中文](README.md)

A cross-agent Skill marketplace for a simple, orderly computer workspace.

The repository distributes the `zen-one-tone-windows` Plugin and Skill to unify Windows, Windows Terminal, VS Code, TRAE, Antigravity IDE, ChatGPT App, Antigravity and Chrome around one Seed Color.

One-Tone supports Windows 10 22H2+ (build `>= 19045`) and Windows 11 22H2+ (build `>= 22621`). Cursor is currently unsupported.

## Install

Install globally with the Vercel Labs Skills CLI for compatible agents:

```powershell
npm install -g skills
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

For Codex only, add `-a codex`. Without installing the CLI, use `npx skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g`. Restart Codex after installation; the CLI's global Codex Skill directory is `~/.codex/skills/`.

```powershell
skills list
skills update zen-one-tone-windows
skills remove zen-one-tone-windows
```

Alternatively use the Codex Plugin Marketplace:

```powershell
codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git
codex plugin add zen-one-tone-windows@zen-computer-marketplace
```

CC Switch users can add this repository in the Skills page, refresh and select `zen-one-tone-windows`.

## Use

In Codex, type `$` and select `zen-one-tone-windows`. In Claude Code, use `/zen-one-tone-windows`. When you need to choose a Seed Color or target scope, the agent opens a selection dialog. You can then run `sync` (`Preview → Apply → Verify`) in one step or request a preview on its own.

```text
Use $zen-one-tone-windows to unify my computer theme with green #22C55E.
```

The theme workflow supports one-step `sync '#22C55E'` as well as explicit `preview` → confirmed Plan `apply` → read-only `verify` → `rollback --latest` (or explicit Transaction ID). Results distinguish `ok`, `partial`, `failed` and `skipped`.

## Theme scope

- Seed Color remains the Theme anchor/Accent source; ChatGPT App surfaces, Antigravity `customThemeSeeds*` / `hubSurfaceBackgroundColor` and Windows wallpaper use derived Tonal surfaces. Confirmed Apply disables Windows transparency, writes `AccentColorInactive` and `Control Panel\Colors\Background`, and sets ChatGPT App `appearanceTheme = system`, `accentSource = custom`, opaque windows and maximum contrast. Existing font values and unknown keys are preserved; missing font tables are repaired.
- Windows Terminal covers defaults, every Profile and existing unfocused appearances. Verified versions disable Acrylic/Mica, use full opacity, clear background images and remove fixed `tabColor`; both `One Tone Light` and `One Tone Dark` Schemes and window themes are registered while window `theme`, `applicationTheme`, defaults and every Profile `colorScheme` default to `One Tone Dark` (`dark`). Unknown capabilities remain unchanged and report partial. Fonts and unrelated preferences are preserved. Shell discovery selects only PowerShell 7 (`pwsh`).
- Terminal body text uses 7:1 on controlled backgrounds in both Modes; other functional text uses 4.5:1. ANSI black uses the tonal surface, white/brightWhite use primary text and brightBlack uses secondary text. Preview discovers executable versions; Windows Terminal >= 1.16 enables `adjustIndistinguishableColors = always` on defaults, every Profile and existing unfocused appearances, with configuration Verify and transaction rollback. Old/unknown versions preserve that setting and report partial.
- The App embedded terminal has an independent xterm/CSS theme with no verified user entry for its complete ANSI table/native contrast correction. Configuration matching does not establish rendering acceptance for either host, application backgrounds, dim/reverse/selection, ANSI256, RGB or real SSH. Reports carry `rendering_verification = untested`.
- VS Code, TRAE and Antigravity IDE intersect the pinned public inventory with discovered Workbench registrations, including menus, notifications, Quick Input, widgets, Diff, Chat, Merge, Notebook, Debug, Testing, Gauge, window borders and selection foreground. Standard C-drive paths (`%APPDATA%\<App>\User\settings.json` and `~/.<app>/extensions`) are prioritized without altering Scoop's directory structure, while any existing Scoop portable `data/` directory is mirrored in sync. Overlays retain alpha and use actual composited backgrounds for contrast. Private AI fields are unsupported.
- Windows automatic Accent selection can override the fixed Accent; the tool reports that limitation without changing automatic selection or system appearance.
- Chrome generates all 24 public colors, 6 tints and applicable properties in two canonical unpacked Light/Dark directories. ZIPs are internal artifacts; activation through `chrome://extensions` remains manual. Image alignment/repeat properties are omitted without an NTP image; browser fonts and window opacity remain unchanged.
- `.one-tone` lives under the Skill runtime root regardless of the agent's current directory. Target paths are discovered from user directories, PATH, launcher inputs or environment variables, without fixed developer paths or Everything.

## Repository and development

`plugin/` contains the installable One-Tone Plugin and its independently distributable Skill. `tests/` contains distribution checks and runtime tests outside the Plugin package. `docs/` holds architecture, testing, specs and ADRs; [CONTEXT.md](CONTEXT.md) is the domain glossary. GitHub Issues track requests; agent collaboration rules live under `docs/agents/`.

See the [One-Tone Skill](plugin/skills/zen-one-tone-windows/SKILL.md), [Target matrix](plugin/skills/zen-one-tone-windows/references/targets.md), [architecture](docs/architecture.md) and [testing](docs/testing.md).

Current terminal requirements are in the [readability spec](docs/specs/2026-10-05-terminal-readability.md), with [capability evidence and incomplete visual gates](docs/terminal-readability-evidence.md). Run the Skill's `python .\scripts\terminal_readability_sample.py` in each host and send it over stdin through the existing real SSH session. The script changes no configuration; emitted samples do not prove visual acceptance.

The [field-coverage spec](docs/specs/2026-07-25-theme-field-coverage-and-separation.md) and [Shell/theme regression spec](docs/specs/2026-08-03-theme-regressions-and-portable-shell-integration.md) document the other accepted boundaries.

The [development spec](docs/specs/2026-10-05-official-theme-coverage-and-slimming.md) is implemented with fixture regressions; [field evidence](docs/theme-field-coverage-evidence.md) records source baselines, capability limits and pending real UI acceptance. The new appearance policy and field contract are hashed into Plans: recreate older Plans through Preview; historical Transactions remain independently restorable.

```powershell
uv run pytest
uv run --project plugin/skills/zen-one-tone-windows one-tone --help
git diff --check
```

From the Skill directory, use `python .\scripts\run_one_tone.py sync '#22C55E'` (or `preview '#22C55E'`, `apply plan-... --confirm`, `verify plan-...`, `rollback --latest`). Use PowerShell 7 (`pwsh`) for PowerShell commands. Real desktop/visual tests remain separate from the default fixture suite.
