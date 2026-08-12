# Windows Shell Accent contrast for fixed white glyphs

## Status

ready-for-agent

## Problem Statement

用户选择亮绿色 Seed Color 后，Windows 快速设置中的活动卡片会显示浅绿色背景和固定白色系统图标。截图显示 Wi-Fi、蓝牙等图标几乎不可辨认，而黑色卡片标签仍清晰。现有 Windows Target 只验证注册表值是否写回，未验证 `AccentPalette` 产生的 Shell 背景与固定白色图标的可读性。

用户要求 Start、任务栏、标题栏和快速设置活动卡片统一变为更深的绿色，同时保留其他 Target、Theme anchor 与 Tonal surface 的现有行为。

## Solution

在现有 Windows Target Adapter seam 内，从 Plan Palette 的 `accent` 派生一个 Windows Shell Accent。该颜色用于 Start、任务栏、标题栏、窗口边框、DWM Accent 与 `AccentPalette`；其完整色阶必须使固定白色 Shell 图标的对比度至少达到 `4.5:1`。

不改变共享 Palette、Seed Color、壁纸、Windows 系统模式、自动取色、高对比度或任何非 Windows Target。Preview → Apply → Verify → Rollback 的事务与 Snapshot 契约保持不变。

## User Stories

1. As a Windows user, I want Quick Settings active-tile icons to remain clear on a green theme, so that Wi-Fi, Bluetooth and similar controls are usable.
2. As a Windows user, I want Start, the taskbar and title bars to use the same deeper green Shell Accent, so that Windows chrome remains visually coherent.
3. As a Windows user, I want a bright Seed Color to preserve its Theme anchor identity outside Windows Shell chrome, so that fixing icon contrast does not flatten the full theme.
4. As a Windows user, I want black Quick Settings labels to remain clear while white system glyphs become clear, so that the fix addresses the actual contrast failure.
5. As a Windows user, I want the tool to preserve my Light/Dark preference, automatic accent selection and high-contrast settings, so that accessibility and personalization choices are not overridden.
6. As a Windows user, I want my wallpaper and non-Windows Targets left on their existing Palette behavior, so that a Shell repair does not unexpectedly recolor other applications.
7. As a Windows user, I want a failed or unwanted change to remain rollback-safe, so that desktop personalization remains reversible.
8. As a maintainer, I want all Windows Shell accent registry outputs to share one derived color, so that Start, taskbar, title bar and DWM do not drift apart.
9. As a maintainer, I want the `AccentPalette` ramp checked against fixed white glyphs, so that a registry round-trip cannot falsely pass a visually unreadable theme.
10. As a maintainer, I want the fix limited to the Windows Adapter, so that shared Palette behavior and other Target mappings do not gain an unsupported special case.
11. As a maintainer, I want real Quick Settings screenshots treated as a separate acceptance gate, so that deterministic fixture checks do not claim to prove native Windows rendering.
12. As a maintainer, I want undocumented per-slot Windows behavior left unguessed, so that the implementation remains safe across supported Windows versions.

## Implementation Decisions

- The highest implementation seam is the existing Windows Target Adapter. It owns conversion of a Plan Palette into wallpaper and Windows registry values; no shared Palette role or new Target is introduced.
- A Windows-specific Shell Accent is derived by darkening the Palette `accent` only as much as needed for the lightest generated `AccentPalette` shade to reach white-glyph contrast `>= 4.5:1`.
- The Shell Accent is used consistently for Start/Taskbar, title bar/window border and DWM Accent registry outputs. The `AccentPalette` is generated as a darker ramp from the same Shell Accent.
- The Adapter does not assign different colors to undocumented `AccentPalette` slots. Until stable public per-slot semantics exist, every generated slot must meet the white-glyph contrast threshold.
- The byte order and persisted registry value shape remain unchanged. This change adjusts colors only, not binary encoding.
- The existing Plan retains Palette `accent` as the Theme anchor-derived Accent. Shell Accent is a transient Adapter output and is not a new persisted Palette role.
- Existing Apply, Verify, Snapshot and Rollback behavior remains unchanged. Verify compares the generated registry output for the same Plan; it does not claim that a registry write proves native rendering.
- Windows system mode, automatic accent selection and high contrast remain read-only contextual fields. No watcher, scheduled task, undocumented Shell API or mode switch is introduced.
- The glossary gains `Windows Shell active tile`. No ADR is added: this is a scoped correction within the accepted Windows Adapter boundary, without a durable cross-module architectural trade-off.

## Testing Decisions

- Tests assert Adapter-visible behavior: applying a representative bright-green Plan writes a coherent Windows Shell Accent and binary `AccentPalette` to the registry backend.
- Decode every `AccentPalette` color slot from the generated registry value and assert contrast against white is `>= 4.5:1`; do not test internal darkening-loop steps.
- Tests verify `AccentColorMenu`, Start color, DWM Accent and DWM colorization use the same Shell Accent as the palette ramp.
- Existing fixture tests continue to verify mode, automatic colorization, high-contrast preservation, Snapshot, Verify and Rollback.
- A manual Windows acceptance pass applies a representative bright green Seed, opens Quick Settings, and captures a screenshot showing legible active-tile white glyphs alongside the darker Start/taskbar/title-bar Accent.
- The manual pass uses Preview → explicit Apply confirmation → Verify and can be rolled back by its explicit transaction ID. Fixture success alone is insufficient visual proof.
- Standard runtime validation remains the repository pytest suite, the Skill CLI help command and `git diff --check`.

## Out of Scope

- Changing the shared Palette generator, Theme anchor, Seed Color, wallpaper generation or other Targets.
- Changing text/font rendering, icon assets, layout, Windows accessibility settings or system Light/Dark mode.
- Disabling automatic accent selection, changing high contrast or bypassing native Light-mode taskbar limitations.
- Inferring undocumented individual `AccentPalette` slot semantics, changing its byte order or adding private Windows APIs.
- Adding a watcher, service, database, new Target, persisted Shell Accent Palette role or separate transaction workflow.
- Automatic application of the repaired theme without the existing Preview and explicit Apply confirmation flow.

## Further Notes

- The observed failure is a foreground/background mismatch: white system glyphs are rendered by Windows over an overly light generated Shell background. It is not a shared Dense primary text failure.
- The existing `AccentPalette` round-trip is necessary but insufficient. The acceptance contract combines deterministic contrast checks with a real Quick Settings screenshot.
