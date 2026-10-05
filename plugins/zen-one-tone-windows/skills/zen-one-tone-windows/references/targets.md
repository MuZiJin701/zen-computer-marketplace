# 支持目标

| 目标 | 范围 | 已知限制 |
| --- | --- | --- |
| `windows` | Windows 10/11 当前用户模式下的桌面壁纸、Start/Taskbar、标题栏强调色和 Quick Settings 活动卡片 | 壁纸使用 Seed 原色；Start/Taskbar、标题栏和固定白色图标的 Shell 卡片使用对比度安全的 Shell Accent；不修改浅/深色模式和自动取色；自动取色开启时报告 `partial` 并要求用户手动关闭；需要注册表和桌面后端，部分应用需要重启 |
| `terminal` | Windows Terminal defaults、所有 Profile 及已有未聚焦配置、成对 Light/Dark Scheme、ANSI、光标、Tab/Tab Row、窗口区域、原生前景修正和可选 PowerShell 7/PSReadLine 预测颜色 | Preview 读取版本资源，`>= 1.16` 使用 `adjustIndistinguishableColors = always`；未知/旧版本保留字段并 partial；`applicationTheme` 保持 `system`；只选择 `pwsh`、不回退 Windows PowerShell；原生修正与配置回读不证明最终渲染阈值；修改后可能需要重启 |
| `vscode` | VS Code 工作台、标题栏、侧边栏、Activity Bar、Tab、Panel、选择/光标、终端 ANSI、链接、诊断和语义高亮主题扩展 | AI 专属面板可能不受标准主题字段控制；Verify 会重新发现持久化扩展目录 |
| `trae` | TRAE 通用工作台、Git decoration、选择/光标、终端 ANSI、链接、诊断、语义高亮和主题扩展 | TRAE 专属 AI 界面可能不受标准主题字段控制；私有 Git 字段不猜测；需重启后 Verify，Verify 会重新发现扩展目录 |
| `chatgpt-app` | ChatGPT App `config.toml` 的已验证 v1 桌面主题字段；浅色和深色表使用同一 Seed 派生的 Tonal `surface` | 缺失的 `fonts` table 会在 Apply 补齐，已有字体值保持不变；`opaqueWindows` 为 `true`、`contrast` 为 `100`；内嵌终端独立 ANSI/xterm 修正没有已验证用户入口，子能力 unsupported；配置匹配不代表终端渲染通过；修改后需要用户手动重启 |
| `chrome` | 生成 Manifest V3 Chrome Light/Dark 两个 canonical unpacked 主题目录，覆盖浏览器框架、工具栏、标签、书签页、NTP、链接和地址栏文字；ZIP 仅为内部打包产物 | Chrome 不支持本工具静默安装；用户需要在 `chrome://extensions` 手动加载和确认 |

Windows 10 支持 build `>= 19045`；Windows 11 支持 build `>= 22621`。

目标结果使用 `ok`、`partial`、`failed` 或 `skipped`，至少包含 `target`、`status`、`changed`、`verified` 和 `message`。Palette 的 `background_foreground` 对深层背景目标为 `>= 7:1`；Light Mode 的 Dense primary text 对实际 `surface` 目标为 `>= 7:1`，其他普通/强调文字对实际 `surface` 目标为 `>= 4.5:1`（理论最大值不足时取最大可得值）；Accent 和选区背景上的文字也使用 `>= 4.5:1`。Dense primary text 必须使用不透明、低色度的 Neutral primary text 角色，不得复用 `muted_foreground`、透明色或状态色；后者只用于 inactive、placeholder、description 和语义状态。Seed 本身不因对比度计算被暗化。所有语义文字字段必须使用对比度安全的 `*_text` 变体，不能直接复用视觉强调色。

`partial` 表示至少一个目标完成但存在失败、跳过或用户操作；若没有目标完成，或补偿回滚失败，则为 `failed`。目标名、Plan ID 和 Transaction ID 不得包含路径分隔符或 `..`。VS Code/TRAE 的路径可通过 `ONE_TONE_<TARGET>_EXECUTABLE`、`ONE_TONE_<TARGET>_SETTINGS`、`ONE_TONE_<TARGET>_EXTENSIONS` 覆盖；Windows Terminal 的 Store/Scoop 用户配置和 ChatGPT App 的 `config.toml` 配置也会自动探测。旧 `codex` Target 的 Plan 不兼容。Skill 不要求 Everything，不使用固定盘符或开发机临时路径。

## 主题字段开发基线

下表是下一阶段实现和测试必须维护的 Field inventory 范围。每个字段必须生成并 Verify，或按实际版本记录为 unsupported。

| Target | 公开字段范围 | 模式/产物要求 |
| --- | --- | --- |
| windows | 壁纸、Accent Palette（含 Quick Settings 活动卡片）、Accent color、Taskbar accent display、标题栏、窗口边框、DWM afterglow；模式选择、自动取色和高对比度只读 | 不强制模式；保持用户策略；所有 Accent Palette 槽位对白色图标至少 `4.5:1`；Light/Dark 都尝试 Taskbar accent display，并按实际系统能力报告 |
| terminal | 完整 Scheme、ANSI、cursor、selection、Profile tabColor/adjustIndistinguishableColors、Tab/Tab Row、frame/unfocusedFrame、窗口主题，以及 PowerShell 7/PSReadLine `InlinePrediction`、`ListPrediction`、`ListPredictionSelected` | light/dark 双 Scheme，正文在 surface 两种 Mode 均 `7:1`，功能文字/选择 `4.5:1`；原生修正与 PSReadLine 按 Preview 版本能力支持或跳过；theme 保持 system |
| vscode | 官方稳定 Workbench 颜色 ID：基础、编辑器、选择/光标、侧栏、Activity Bar、Tab、Panel、Input、List、Widget、Settings、Breadcrumb、通知、诊断、链接、语义和语法字段 | 一个安装包包含 Light/Dark 两套主题；设置使用扩展实际贡献的精确标签 |
| trae | VS Code 标准字段、公开 Git decoration 字段，加上安装版本中可发现且可验证的 TRAE 专属字段 | 一个安装包包含 Light/Dark 两套主题；设置使用精确标签；专属字段可 partial |
| chatgpt-app | 已验证 v1 两套主题表的 surface、ink、accent、contrast、opaqueWindows、fonts 和 semanticColors 字段 | 同一 Plan 同时更新 light/dark 表；补齐缺失 fonts table、强制实心窗口与最高对比度，并保留未知键和已有字体值 |
| chrome | 完整公开 colors、tints、display_properties；包括 frame、toolbar、tabs、bookmark、NTP、omnibox、separator、button、incognito 等稳定字段 | 生成两个 canonical unpacked 目录；内部 ZIP 不作为额外用户选项，用户手动加载 |

相邻背景角色的目标为至少 1.2:1；边框、焦点、选区和强调控件相对邻近背景至少 3:1；Light Mode 的 Dense primary text 使用不透明 Neutral primary text 和 surface 7:1，其他文字使用 surface 4.5:1，deep background 文字使用 7:1。字段清单不得把私有、实验或不可验证字段伪装成完整支持。

## 终端字段证据与验收边界

Field inventory `2026-10-05.v3` 继续由共享映射生成；下表解释公开字段的实际用途。

| 字段/输出 | 映射或能力 | 实际背景/状态及证据 |
| --- | --- | --- |
| Scheme foreground | foreground | 两种 Mode 对 surface `>= 7:1`；[微软 Scheme 文档](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/color-schemes) |
| ANSI black | surface | 代表性默认正文和 ANSI white 对 black 背景达标；black 作为前景时可能需要宿主修正，一张色表不保证所有组合 |
| ANSI white / brightWhite | foreground | 对 ANSI black 背景 `>= 4.5:1`，反色配对同样可读；槽位随 Mode 适配，不强求字面黑白 |
| ANSI brightBlack | muted_foreground | 对 surface `>= 4.5:1`；作为背景或经 dim 渲染后另行验收 |
| selectionForeground / selectionBackground | selection 对 | 配对 `>= 4.5:1`；实际选中的 ANSI/RGB/弱化文字仍需视觉复核 |
| profile.adjustIndistinguishableColors | display_property / always | [微软原生修正文档](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance#adjust-indistinguishable-colors)；[1.16 发布基线](https://github.com/microsoft/terminal/discussions/13977)；能力由 Preview 的本机版本资源发现，不代表全部 `7:1`/`4.5:1` |
| PSReadLine 预测颜色 | prediction_foreground / selection 对 | 仅 PowerShell Core `>= 7`，公开字段与 Profile 在 Preview 发现；Windows PowerShell 不参与选择 |
| ChatGPT App 内嵌 xterm | unsupported 配置子能力 | 已检查 App 26.930.4958.0 的独立 CSS token 与 xterm 主题装配；没有已验证的完整 ANSI/minimumContrastRatio 用户配置入口，保留未知结构 |
| ANSI256 / RGB / dim / reverse / SSH | 独立渲染验收 | `python .\scripts\terminal_readability_sample.py` 覆盖代表性输出；报告 `rendering_verification = untested`，配置 Verify 不自动转为视觉通过，远端配置保持不变 |
