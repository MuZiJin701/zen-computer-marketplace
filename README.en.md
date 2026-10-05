# Zen Computer Marketplace

[简体中文](README.md)

A cross-agent Skill marketplace for a simple, orderly computer workspace.

Three independent Plugins are available: `zen-one-tone-windows` unifies Windows themes, `zen-desktop-zero` organizes the current user's desktop, and `zen-scoop-toolchain` checks and completes the basic development toolchain.

One-Tone supports Windows 10 22H2+ (build `>= 19045`) and Windows 11 22H2+ (build `>= 22621`). Cursor is currently unsupported. The two workstation Plugins require an available, writable D drive and do not silently choose another drive.

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
skills update zen-desktop-zero
skills update zen-scoop-toolchain
skills remove zen-one-tone-windows
skills remove zen-desktop-zero
skills remove zen-scoop-toolchain
```

Alternatively use the Codex Plugin Marketplace:

```powershell
codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git
codex plugin add zen-one-tone-windows@zen-computer-marketplace
codex plugin add zen-desktop-zero@zen-computer-marketplace
codex plugin add zen-scoop-toolchain@zen-computer-marketplace
```

CC Switch users can add this repository in the Skills page, refresh and select the desired Skills.

## Use

Tell your agent what you need. Every Skill previews its changes before execution confirmation.

```text
Use $zen-one-tone-windows to unify my computer theme with emerald #10B981. Preview first.
Use $zen-desktop-zero to preview desktop cleanup: delete shortcuts and classify other items under D:\data.
Use $zen-scoop-toolchain to check Python, Git, uv and Node.js. Preview missing tools before installation.
```

Desktop shortcuts are deleted and cannot be restored. Other files and folders can be rolled back using an explicit Transaction ID. The recommended launch entry is Windows taskbar Search; no background monitor is installed. Existing tools are preserved. Missing tools use Scoop under `D:\software\scoop` first, then winget when Scoop cannot provide them; winget commonly controls its own install path.

The common theme workflow is Preview → confirmed Plan Apply → read-only Verify → explicit Transaction Rollback. Results distinguish `ok`, `partial`, `failed` and `skipped`.

## Theme scope

- Seed Color is the Theme anchor/Accent source. ChatGPT App surfaces and Windows wallpaper use derived Tonal surfaces in the current runtime. The App preserves `appearanceTheme`, existing font values and unknown keys, repairs missing font tables, and uses opaque windows with maximum contrast.
- Windows Terminal generates paired Light/Dark Schemes for all discovered Profiles, follows system appearance and supports optional PSReadLine prediction colors. Shell discovery chooses PowerShell 7 (`pwsh`), verifies Core >= 7 and never falls back to Windows PowerShell. It does not change the user's default Terminal Profile.
- Terminal body text uses 7:1 on controlled backgrounds in both Modes; other functional text uses 4.5:1. ANSI black uses the tonal surface, white/brightWhite use primary text and brightBlack uses secondary text. Preview discovers executable versions; Windows Terminal >= 1.16 enables `adjustIndistinguishableColors = always` on defaults, every Profile and existing unfocused appearances, with configuration Verify and transaction rollback. Old/unknown versions preserve that setting and report partial.
- The App embedded terminal has an independent xterm/CSS theme with no verified user entry for its complete ANSI table/native contrast correction. Configuration matching does not establish rendering acceptance for either host, application backgrounds, dim/reverse/selection, ANSI256, RGB or real SSH. Reports carry `rendering_verification = untested`.
- VS Code/TRAE themes cover standard Workbench, Git decorations, selections/cursors, terminal ANSI, links, notifications and semantic highlighting, and enable native system appearance following. Private AI panels remain application-controlled.
- Windows automatic Accent selection can override the fixed Accent; the tool reports that limitation without changing automatic selection or system appearance.
- Chrome produces two canonical Manifest V3 unpacked Light/Dark theme directories; ZIP files are internal artifacts. Load and confirm the desired theme manually through `chrome://extensions`.
- `.one-tone` lives under the Skill runtime root regardless of the agent's current directory. Target paths are discovered from user directories, PATH, launcher inputs or environment variables, without fixed developer paths or Everything.

## Repository and development

`plugins/` holds independent Plugin envelopes and distributable Skill runtimes. `tests/` mirrors Marketplace → Plugin → Skill and stays outside distributable Skills. `docs/` holds architecture, testing, specs and ADRs; [CONTEXT.md](CONTEXT.md) is the domain glossary. GitHub Issues track requests; agent collaboration rules live under `docs/agents/`.

See the [One-Tone Skill](plugins/zen-one-tone-windows/skills/zen-one-tone-windows/SKILL.md), [Desktop zero Skill](plugins/zen-desktop-zero/skills/zen-desktop-zero/SKILL.md), [toolchain Skill](plugins/zen-scoop-toolchain/skills/zen-scoop-toolchain/SKILL.md), [Target matrix](plugins/zen-one-tone-windows/skills/zen-one-tone-windows/references/targets.md), [architecture](docs/architecture.md) and [testing](docs/testing.md).

Current terminal requirements are in the [readability spec](docs/specs/2026-10-05-terminal-readability.md), with [capability evidence and incomplete visual gates](docs/terminal-readability-evidence.md). Run the Skill's `python .\scripts\terminal_readability_sample.py` in each host and send it over stdin through the existing real SSH session. The script changes no configuration; emitted samples do not prove visual acceptance.

The [field-coverage spec](docs/specs/2026-07-25-theme-field-coverage-and-separation.md), [Shell/theme regression spec](docs/specs/2026-08-03-theme-regressions-and-portable-shell-integration.md) and [workstation spec](docs/specs/2026-07-26-zen-workstation-plugins.md) document the other accepted boundaries.

```powershell
uv run pytest
uv run --project plugins/zen-one-tone-windows/skills/zen-one-tone-windows one-tone --help
git diff --check
```

From the Skill directory, use `python .\scripts\run_one_tone.py preview '#10B981'`, then `apply plan-... --confirm`, `verify plan-...` and `rollback tx-...` with the actual confirmed IDs. Use PowerShell 7 (`pwsh`) for PowerShell commands. Real desktop/visual tests remain separate from the default fixture suite.
