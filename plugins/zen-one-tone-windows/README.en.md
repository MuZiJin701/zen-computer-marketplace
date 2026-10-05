# zen-one-tone-windows

[简体中文](README.md)

This Plugin distributes one self-contained Skill for Windows 10 22H2+ and Windows 11 22H2+: unify Windows, Windows Terminal, VS Code, TRAE, ChatGPT App and Chrome around an explicitly supplied Seed Color.

Use Preview → confirmed Plan Apply → read-only Verify → explicit Transaction Rollback. From the Skill directory:

```powershell
python .\scripts\run_one_tone.py preview '#22C55E'
python .\scripts\run_one_tone.py apply plan-... --confirm
python .\scripts\run_one_tone.py verify plan-...
python .\scripts\run_one_tone.py rollback tx-...
```

Use the actual saved IDs. Preview writes only a Plan; no real theme is applied without confirmation. Apply snapshots each target, journals every operation and compensates only failed targets. Rollback restores its own snapshot, including formerly absent settings. Older Plans must be recreated for the current appearance policy; historical Transactions remain restorable.

Confirmed Apply disables Windows transparency, applies version-gated solid Terminal appearances and sets ChatGPT App appearance to `system`. Windows modes, automatic accent selection, high contrast and font preferences are preserved. Missing App font tables are repaired without inventing font values. High contrast active/unknown safely skips Windows; Shell taskbar limitations follow actual Shell mode.

Editor colors use the intersection of pinned public documentation and discovered Workbench `1.107.1`/`1.140.0` registrations. Unknown versions skip; private AI colors remain unsupported. Terminal paired Schemes require >=1.16; paired window themes/Mica require >=1.17; frame fields require >=1.22 and a compatible Windows platform. Unsupported settings remain unchanged and report partial. PowerShell prediction discovery uses only verified Core >=7 `pwsh`.

Chrome generates 24 colors, 6 tints and applicable properties in two unpacked Light/Dark directories, with ZIPs as internal artifacts. Load the desired directory manually through `chrome://extensions`; no silent activation, browser-font or full-window-opacity control is claimed.

Configuration verification checks complete managed artifacts; it does not establish visual acceptance. Real application/SSH rendering remains independently untested. See the Skill's [target matrix](skills/zen-one-tone-windows/references/targets.md), repository [testing guide](../../docs/testing.md) and [field evidence](../../docs/theme-field-coverage-evidence.md).
