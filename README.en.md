# Zen Computer Marketplace

[简体中文](README.md)

Unify your Windows desktop, wallpaper, and everyday app themes around a single Seed Color. Currently ships the `zen-one-tone-windows` plugin and Skill.

- **Supported targets**: Windows desktop and wallpaper, Windows Terminal, VS Code, TRAE, Antigravity IDE, ChatGPT App, Antigravity, MATLAB (`>= R2025a`), and Chrome.
- **Supported OS**: Windows 10 22H2+ (build `>= 19045`) and Windows 11 22H2+ (build `>= 22621`). Cursor is not supported as a theme target.

## 1. Install and update

Pick one installation method per host (`skills` CLI is recommended for most users).

### Option 1: Using the `skills` CLI (recommended)

Run the command below and choose your host (Codex, Claude Code, Antigravity, Grok Build, or GitHub Copilot CLI):

```powershell
npm install -g skills
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

To install for Codex only, add `-a codex`. If you do not want to install `skills` globally, prefix with `npx skills`.

Manage the installed Skill:

```powershell
skills list
skills update zen-one-tone-windows -g
skills remove zen-one-tone-windows
```

If you use `cc-switch`, add `https://github.com/MuZiJin701/zen-computer-marketplace.git` on the Skills page, refresh, and select `zen-one-tone-windows`.

### Option 2: Native plugin CLI commands

| Host | Install command |
| --- | --- |
| Codex | `codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git`<br>`codex plugin add zen-one-tone-windows@zen-computer-marketplace` |
| Claude Code | `claude plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`claude plugin install zen-one-tone-windows@zen-computer-marketplace` |
| Antigravity | `agy plugin install https://github.com/MuZiJin701/zen-computer-marketplace` |
| Grok Build | `grok plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`grok plugin install zen-one-tone-windows --trust` |
| GitHub Copilot CLI | `copilot plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`copilot plugin install zen-one-tone-windows@zen-computer-marketplace` |

Open a new session after installing or updating.

## 2. How to use

To avoid unintended changes to your desktop, this Skill is **explicit-invocation only**. Select it explicitly before sending your request:

- **Codex**: Type `$` and select `zen-one-tone-windows`
- **Claude Code**: Use `/zen-one-tone-windows` (standalone Skill) or `/zen-one-tone-windows:zen-one-tone-windows` (plugin)
- **Antigravity / Grok Build / Copilot CLI**: Invoke `/zen-one-tone-windows` or select it from the slash menu

Tell the agent your chosen Seed Color (and any specific target scope if you do not want all targets):

```text
Use $zen-one-tone-windows to unify my computer theme with green #22C55E.
```

### Safe workflow and rollback

- **One-step sync (`sync '#22C55E'`)**: Runs `Preview` (creates a read-only `Plan` without touching your PC), backs up and applies changes (`Apply`), and checks the result (`Verify`).
- **Step-by-step mode**: You can also run `preview`, `apply plan-... --confirm`, and `verify plan-...` separately.
- **Easy rollback**: Snapshots are saved automatically before each target is modified, and failed targets roll back on their own. You can undo anytime with `rollback --latest` or by specifying a `Transaction ID`.
- **Result statuses**: Each target reports `ok`, `partial` (some fields kept unchanged due to app version limits), `failed`, or `skipped`.

## Usage tips

- **Windows accent color and wallpaper**: Confirmed apply updates per-monitor wallpapers, disables transparency effects, and activates Windows Custom Mode (Dark Shell while preserving your Light/Dark app mode) so the taskbar accent color stays natively enabled; single-value desktop surfaces (wallpapers, fallback background, inactive title bar, and Shell accents) use mode-independent Seed-derived tones so toggling app Light/Dark mode keeps them consistent without re-running `sync`, and rollback restores the previous settings. Turning off Windows "Automatically pick an accent color from my background" is still recommended.
- **Chrome native dynamic theme**: One-Tone writes your Seed Color (`kTonalSpot`) directly into the active Google Chrome profile's `Preferences` with system Light/Dark following enabled and clears custom New Tab Page backgrounds—no manual `chrome://extensions` loading required. During `sync`, `apply`, and `rollback`, running Chrome processes are closed automatically (graceful close up to 3s, then force termination without auto-relaunch), so save any unsubmitted browser work first; if Chrome Sync restores an older cloud-selected theme on startup, reset to the default theme once in Customize Chrome or disable theme sync.
- **Light/Dark modes and terminal**: Windows Terminal, VS Code, TRAE, Antigravity IDE, ChatGPT App, Antigravity, MATLAB (`>= R2025a`), and Chrome follow your Windows app Light/Dark mode automatically. When PowerShell 7 (`pwsh`) is installed, Terminal sessions also adapt PSReadLine prediction and syntax colors to the active mode.
- **MATLAB notes**: MATLAB harmonizes editor, command window, workspace, and syntax colors without modifying installation bundle chrome (reported as `partial`), preserving `GraphicsTheme` and feature toggles. During `sync`, `apply`, and `rollback`, running MATLAB processes are closed automatically (graceful close up to 3s, then force termination without auto-relaunch), so save unsaved scripts or workspace state beforehand.
- **Personal settings preserved**: Fonts and unrelated settings stay untouched. Unsupported fields in older app versions are left unchanged and reported as `partial`.

## Repository layout and development

```text
.
├─ .claude-plugin/marketplace.json        # Shared Marketplace index
├─ plugin/                                # Installable One-Tone plugin
│  ├─ plugin.json                         # Agent Plugins 1.0 manifest
│  ├─ .claude-plugin/plugin.json          # Claude Code manifest
│  └─ skills/zen-one-tone-windows/        # Skill and standalone runtime
├─ tests/                                 # Distribution and runtime tests
├─ docs/                                  # Architecture, testing, and ADRs
└─ CONTEXT.md                             # Domain glossary
```

Run tests from the repository root or invoke the CLI directly from the Skill directory:

```powershell
uv run pytest
uv run --project plugin/skills/zen-one-tone-windows one-tone --help
```

From `plugin/skills/zen-one-tone-windows`, you can also run `python .\scripts\run_one_tone.py preview '#22C55E'` (as well as `sync`, `apply plan-... --confirm`, `verify plan-...`, and `rollback --latest`).

See [CONTEXT.md](CONTEXT.md), [SKILL.md](plugin/skills/zen-one-tone-windows/SKILL.md), [targets.md](plugin/skills/zen-one-tone-windows/references/targets.md), [architecture.md](docs/architecture.md), [testing.md](docs/testing.md), and [ADRs](docs/adr/) for developer details.
