# zen-one-tone-windows

[简体中文](README.md)

Distributes the self-contained `zen-one-tone-windows` Skill for Windows 10 22H2+ and Windows 11 22H2+: unify Windows desktop, wallpaper, Windows Terminal, VS Code, TRAE, Antigravity IDE, ChatGPT App, Antigravity, MATLAB (`>= R2025a`), and Chrome around a single Seed Color. Cursor is not supported as a theme target.

## Install and use

`skills` CLI is recommended, and native plugin CLI installation is also supported for major agents. See the [installation guide](https://github.com/MuZiJin701/zen-computer-marketplace/blob/main/README.en.md#1-install-and-update) and [usage instructions](https://github.com/MuZiJin701/zen-computer-marketplace/blob/main/README.en.md#2-how-to-use).

From the Skill directory (`skills/zen-one-tone-windows/`), you can run the CLI directly:

```powershell
python .\scripts\run_one_tone.py sync '#22C55E'
python .\scripts\run_one_tone.py preview '#22C55E'
python .\scripts\run_one_tone.py apply plan-... --confirm
python .\scripts\run_one_tone.py verify plan-...
python .\scripts\run_one_tone.py rollback --latest
```

Or inspect the standalone package CLI with `uv`:

```powershell
uv run --project . one-tone --help
```

## Notes

- **Preview, backup, and rollback**: `preview` creates a read-only plan; `apply` snapshots each target before modifying it and automatically compensates failed targets. Undo anytime with `rollback --latest`.
- **Personal settings preserved**: Fonts and unrelated preferences remain untouched. Turn off Windows "Automatically pick an accent color from my background" if Windows overrides the fixed accent color.
- **Chrome themes**: Light and Dark unpacked extensions are generated and must be loaded manually in `chrome://extensions`.
- **Self-contained runtime**: This Skill runs independently of the repository root. See the [target matrix](skills/zen-one-tone-windows/references/targets.md) and [testing guide](../docs/testing.md) for details.
