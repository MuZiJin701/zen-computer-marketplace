# 支持目标

| 目标 | 范围 | 实际能力和保留项 |
| --- | --- | --- |
| `windows` | Windows 10 22H2+（build >=19045）/Windows 11 22H2+（build >=22621）；壁纸、Shell Accent、Start/Taskbar、标题栏、DWM、透明效果 | 确认 Apply 写 EnableTransparency=0；壁纸为 Seed 派生 Tonal surface；Shell Accent 保护固定白色图标 >=4.5。App/Shell 模式分别读取并保持，高对比度 API 开启/未知时 skipped；浅色/未知 Shell 的任务栏颜色 unsupported，自动取色可能覆盖固定 Accent，报告 partial |
| `terminal` | defaults、所有 Profile、已有 unfocusedAppearance；两套 Scheme/ANSI、光标、选择背景、Tab/Tab Row/window 和可选 pwsh/PSReadLine 预测 | 按 Preview 冻结的版本应用实心和原生跟随；保留字体、padding、字形、光标形状、Tab 偏好、rainbowFrame 和未知键；未知能力保留并 partial；配置回读不证明渲染阈值 |
| `vscode` | 完整固定公开颜色清单与实际 Workbench 注册字段交集；菜单、通知、Quick Input、Widget、Diff、Chat、Merge、Notebook、Debug、Testing、ANSI 与语义/语法高亮 | 已核查 Workbench 1.140.0/1.107.1；未知版本安全 skipped。使用精确贡献标签和原生 autoDetect；保留字体、光标形状、终端渲染和高对比度偏好 |
| `trae` | 实际 Workbench 版本对应的同一公开清单；公开 Git decoration 等 | 产品版本不替代 Workbench 注册基线；私有 AI 字段 unsupported，不猜测替代键。配置和扩展使用 Plan 的实例路径 |
| `chatgpt-app` | 已验证 config.toml v1 两个 Light/Dark 主题表及 appearanceTheme | appearanceTheme=system，contrast=100、opaqueWindows=true；完整 semanticColors；补齐缺失 fonts table，不发明字体值；未知布局安全 skipped。UI 字号、sidebar 透明度和内嵌终端无已验证入口，unsupported；手动重启 |
| `chrome` | 两个 canonical unpacked Light/Dark Manifest V3 主题，24 colors、6 tints 和适用 properties | ZIP 为内部产物，用户在 chrome://extensions 手动加载并确认。没有 NTP 图片时省略 alignment/repeat；只写 ntp_logo_alternate。不支持 theme 字体/全窗口透明度，内容字体保持原值 |

默认全部六个目标；显式 cursor 安全 skipped，不访问 Cursor 文件。Seed Color 必须显式输入；示例为 `#22C55E`，没有默认 Seed。

## 字段和版本证据

Field inventory `2026-10-05.v4` 与生成器共享显式字段映射，区分 color、font、display_property 和 theme_structure；逐项显示处理策略、来源、版本、适用条件、实际 capability 和生成值。能力为 supported、unsupported、not-applicable、applied、verified 或 failed。保留字体不等于生成字体值；App fonts 的空表修复属于结构修复。

公开编辑器清单固定为 [vscode-docs commit 8889b05](https://github.com/microsoft/vscode-docs/blob/8889b0542cb2144fb53f5f53bd19c1395e2d9fa1/api/references/theme-color.md) 的 971 项。与 [1.107.1](https://github.com/microsoft/vscode/tree/1.107.1) / [1.140.0](https://github.com/microsoft/vscode/tree/1.140.0) 源码 registerColor、ANSI 和 contributes.colors 交集分别 901/962 项，排除 Windows 普通 Light/Dark 不适用的五项后生成 896/957 项。window.activeBorder/inactiveBorder 在 Windows 不适用；contrastBorder/contrastActiveBorder 和 editor.selectionForeground 仅高对比度适用。其余未注册项 unsupported；不写 panel.foreground。

普通正文保持不透明、低色度 Neutral primary text，在实际背景 >=7；其他功能/状态/语义文字 >=4.5。普通相邻区域目标 >=1.2，交互边界 >=3。35 项文档透明约束保留 alpha；查找文字按合成背景检查，Diff/Merge 叠层保留语义与区域区分。实心窗口策略不把叠层机械改为不透明。编辑器 ANSI black/white/brightBlack 保持不同角色。

Chrome 的 [固定公开 parser](https://github.com/chromium/chromium/blob/77270bd36581caca2ab02fe4526cc921560ad089/chrome/browser/themes/browser_theme_pack.cc) 是字段证据；不输出 display_properties、无效 separator 字段或未知 theme 设置。Windows AccentPalette/Afterglow 属于核查过的注册表运行时机制，不能称为稳定公开 schema；高对比度读取 [SPI_GETHIGHCONTRAST](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow)。ChatGPT App v1 是已验证运行时 schema，不是公开 API 承诺。

## Terminal 门槛和验收

| 字段 | 门槛 / 策略 |
| --- | --- |
| Scheme foreground / ANSI black | 同 Mode 的正文 / surface 配对 >=7；white/brightWhite 使用正文色，brightBlack 使用次要色 |
| Scheme selectionBackground | 有公开支持；Scheme 不写 selectionForeground；Palette 的 selection_foreground 仅供 PSReadLine 选择等实际支持的入口 |
| profile.colorScheme 对 / adjustIndistinguishableColors | >=1.16；后者 always。未知/旧版本使用单个 Scheme 并报告配对/原生修正 unsupported，不伪称完整跟随 |
| profile.tabColor / useAcrylic / backgroundImage | 已核查版本移除固定 tabColor，useAcrylic=false，backgroundImage 空；未知版本保留并 unsupported |
| profile.opacity | >=1.12 写 100，移除旧 acrylicOpacity；defaults、各 Profile、已有 unfocusedAppearance 一致 |
| theme 对 / window.useMica | >=1.17；Mica 仅适用 Windows 11 >=22621；applicationTheme 保持 system；未知/旧版本 root theme 使用 system |
| window.frame / unfocusedFrame | >=1.22 且 Windows 11 平台；旧/未知版本不新增字段，保留原有偏好并报告能力 |
| PSReadLine InlinePrediction/ListPrediction/ListPredictionSelected | 仅验证为 PowerShell Core >=7 的 pwsh；没有 pwsh 不回退 Windows PowerShell；Profile 与公开字段由 Preview 发现，受管块仅 WT_SESSION 生效 |

门槛对照 [v1.25.2733.0 schema](https://github.com/microsoft/terminal/blob/v1.25.2733.0/doc/cascadia/profiles.schema.json) 及 1.16/1.17/1.22 固定 schema；[原生修正](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance#adjust-indistinguishable-colors) 不保证任意程序组合达到本工具阈值。

## 流程和限制

Preview 只保存 Plan；字段能力、两套 Palette、实例和 Appearance policy 进入 Hash。旧 Plan 或变化的字段契约要求重新 Preview，Apply 在创建事务和 Snapshot 前拒绝；历史事务 Rollback 独立工作。Apply 对每个目标 Snapshot 并逐操作持久化，失败仅补偿该目标；至少一个成功且存在限制/失败/跳过时 partial，无成功或补偿失败时 failed。

Verify 只读，校验两套完整主题、注册贡献路径/类型/标签、settings、Chrome unpacked/ZIP、完整 TOML 和受管 Windows/Terminal 配置。不创建事务、不 Snapshot、不 Apply、不重启或回滚。Rollback 仅接受准确 transaction ID，恢复该事务的快照或工具产物并验证，包含原先缺失的字段。

Target、Plan ID、Transaction ID 必须是安全路径组件。ONE_TONE_<TARGET>_EXECUTABLE/SETTINGS/EXTENSIONS 可明确覆盖编辑器实例；Preview 解析普通/portable/启动器实例并冻结 Workbench 基线，Apply/Verify 不重新猜路径。运行时不要求 Everything、仓库根目录、开发机绝对路径或固定盘符。

配置 verified 与 rendering acceptance 分开。真实桌面/私有 AI/内嵌 xterm/应用自带背景/dim/reverse/ANSI256/RGB/真实 SSH 尚未验收；报告 rendering_verification=untested。诊断入口 `python .\scripts\terminal_readability_sample.py` 只输出代表性 ANSI 样例；可以经 stdin 送入已授权 SSH，不写远端配置。内嵌终端完整 ANSI/minimumContrastRatio 无已验证用户入口，不修改 App bundle。
