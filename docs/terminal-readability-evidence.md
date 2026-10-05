# Terminal functional text evidence

Date: 2026-10-05. Configuration implementation is available; complete rendering acceptance is pending. Fixture and numerical passes below do not establish the final rendered colors in either host.

This is the earlier terminal-task record, including its historical 168-test result and SSH transport observation. The subsequent [official-field implementation evidence](theme-field-coverage-evidence.md) updates the current policy and validation scope; no new desktop Apply or SSH run was performed. Scheme selectionForeground has been removed because the pinned parser does not support it. Selection ratios below describe the Palette/PSReadLine selection pair, not a Scheme foreground capability.

## Sources and installed capabilities

- Windows Terminal executable version resource: `1.25.2609.30003`. Preview discovers support for `adjustIndistinguishableColors = always`; [Microsoft's appearance documentation](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance#adjust-indistinguishable-colors) defines the field and [the 1.16 release announcement](https://github.com/microsoft/terminal/discussions/13977) establishes the enum baseline. Neither source guarantees this spec's full contrast thresholds.
- PowerShell 7: Core `7.6.6`, PSReadLine `2.4.5`, all three public prediction fields discovered. After the user's PowerShell 7 preference, discovery chooses `pwsh` and its `CurrentUserAllHosts` Profile; Windows PowerShell is excluded. No installed Profile was modified.
- ChatGPT App package: `26.930.4958.0`. Read-only inspection of `webview/assets/xterm-display-helpers-f861d9073117.js` shows its theme assembled from computed `--color-codex-terminal-*` CSS tokens. `terminal-panel-8f2b3c8ddb54.js` passes that theme to the renderer; the bundled xterm default `minimumContrastRatio` is `1`, but a library default alone does not establish every renderer's effective options. `app-shared-6fb15e58cd7f.css` maps ANSI black/brightBlack to tertiary/secondary text tokens and white to primary text, independently of Windows Terminal. No verified user setting exposes the complete ANSI table or minimum-contrast option. Desktop TOML theme matches remain configuration evidence only. No bundle was changed.
- Latest installed One-Tone Plan identifies current Seed `#00C853`; local Codex CLI reports `0.160.0`. The pictured editor is not identified; finding `micro`, `nano` or `vim` on the server is not evidence that any of them is the pictured application. No local application theme was guessed or changed.

## Generated configuration measurements

Ratios are computed from generated Scheme values with WCAG relative luminance. `black` uses the same Mode's tonal surface; names describe ANSI slots, not fixed physical black/white colors. Default text/black and white/black therefore match body/surface ratios, and black/white reverse has the same ratio. The secondary column is the minimum of brightBlack and representative red/green/yellow/blue/purple/cyan text on the Scheme background.

| Seed | Mode | Body/surface | White/black | Secondary minimum | Selection pair | Configuration result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| #00C853 | Light | 7.029 | 7.029 | 5.470 | 6.439 | pass |
| #00C853 | Dark | 8.771 | 8.771 | 8.770 | 6.803 | pass |
| #10B981 | Light | 7.030 | 7.030 | 5.471 | 6.502 | pass |
| #10B981 | Dark | 8.794 | 8.794 | 8.793 | 5.963 | pass |
| #FFD700 | Light | 7.043 | 7.043 | 5.381 | 6.399 | pass |
| #FFD700 | Dark | 8.869 | 8.869 | 8.868 | 11.262 | pass |

This protects the representative primary/white-on-black and reverse pairs. ANSI black as foreground on the default surface is indistinguishable before native correction, and brightBlack used as background, dim compositing, program-owned backgrounds, ANSI256/RGB and arbitrary pairs remain independent acceptance cases. The native correction setting is enabled only on supported versions and is not claimed to guarantee 7:1/4.5:1.

## Real SSH and visual matrix

The user-provided existing SSH connection was reached read-only. The packaged diagnostic executed remotely via `python3 -` over stdin, exit `0`, producing 40 lines with default/ANSI16/ANSI256/RGB/dim/reverse samples; no remote file was created. This establishes real SSH transport/output coverage, not either GUI host's rendering. Remote editor versions found: micro `2.0.13`, nano `7.2`, Vim `9.1`. Remote Codex CLI cannot start because `@openai/codex-linux-x64` is missing; no installation or repair was attempted.

Each matrix row covers both Modes, all three Seeds, actual Codex CLI, the pictured editor and the diagnostic. Current body/path/status/placeholder/selection/dim/reverse/256/RGB rendered ratios are **not measured** in these rows.

| Host | Session | Visual result | Remaining gate |
| --- | --- | --- | --- |
| Windows Terminal | Local | untested | Confirmed real theme Apply and visual measurement; identify pictured editor |
| Windows Terminal | Real SSH | untested | Same host checks; remote Codex dependency is broken |
| ChatGPT App embedded terminal | Local | untested | Full ANSI/native correction has no verified config entry; measure actual rendering and identify editor |
| ChatGPT App embedded terminal | Real SSH | untested | Same App limits plus broken remote Codex dependency |

The available Computer Use plugin's guidance prohibits automating terminal applications and the ChatGPT desktop UI. Visual acceptance therefore remains manual in this session. No actual theme Apply or system Mode switch was performed. Follow [the testing procedure](testing.md); record passes, failures and missing cases separately, and leave `rendering_verification` untested until that independent gate is fulfilled.

## Standards

The independent read-only Standards review found no actionable documented-standard breach or design smell. The implementation reuses the existing Field inventory, Plan, Adapter and Transaction boundaries without new dependencies or a TUI framework.

## Spec

The independent read-only Spec review found no actionable runtime mismatch or scope creep. Full visual acceptance, identification of the pictured editor and remote Codex availability remain incomplete acceptance gates, as recorded above; they are not represented as passing checks.

Review summary: Standards 0 actionable findings; Spec 0 actionable runtime findings, with 3 documented acceptance gates still pending. Automated validation uses `uv run pytest`, the Skill's `one-tone --help`, Python `compileall`, Markdown link checking and `git diff --check`; type checking is not configured.

Final automated result: `uv run pytest -q` — 168 passed. CLI help, Python compilation, all 13 affected documents' local links and both working/staged diff whitespace checks passed. Existing staged changes were preserved; this task's changes are staged without a commit or push.
