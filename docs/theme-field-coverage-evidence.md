# 公开主题字段实施证据

日期：2026-10-05。对应 [开发规格](specs/2026-10-05-official-theme-coverage-and-slimming.md)。本记录区分公开清单、安装版本能力、配置回读与真实渲染；真实桌面 Apply、Chrome 激活和本次 SSH/视觉验收均未执行。

## 固定来源与适用性

| Target | 固定来源 / 证据 | 当前输出与边界 |
| --- | --- | --- |
| VS Code / TRAE | [公开文档 commit 8889b05](https://github.com/microsoft/vscode-docs/blob/8889b0542cb2144fb53f5f53bd19c1395e2d9fa1/api/references/theme-color.md)；[VS Code 1.107.1](https://github.com/microsoft/vscode/tree/1.107.1) / [1.140.0](https://github.com/microsoft/vscode/tree/1.140.0) 的 registerColor、ANSI 注册和扩展 contributes.colors | 971 个公开 ID，注册交集分别 901 / 962；排除 Windows 普通 Light/Dark 不适用的 5 项后生成 896 / 957 项 |
| Terminal | [v1.25.2733.0 schema](https://github.com/microsoft/terminal/blob/v1.25.2733.0/doc/cascadia/profiles.schema.json)，并核查 1.16、1.17、1.22 schema | Scheme 无 selectionForeground；colorScheme 对需 >=1.16，theme 对/Mica >=1.17，frame/unfocusedFrame >=1.22；Mica/frame 另受 Windows 平台能力限制 |
| Chrome | [固定 Chromium parser](https://github.com/chromium/chromium/blob/77270bd36581caca2ab02fe4526cc921560ad089/chrome/browser/themes/browser_theme_pack.cc) | 24 colors、6 tints、3 properties；仅生成适用的 ntp_logo_alternate，无 NTP 图片时省略 alignment/repeat；移除六个无效颜色键和 display_properties |
| Windows | 已核查用户注册表机制；[SPI_GETHIGHCONTRAST API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow) | EnableTransparency=0；App/Shell 模式分别读取，高对比度来自 API，不假造注册表布尔字段；AccentPalette/Afterglow 不称为公开稳定 schema |
| ChatGPT App | 已验证的 chatgpt-app-config-v1 TOML 运行时 schema；来源为运行时检查而非公开稳定 API | appearanceTheme=system；两个主题表含颜色、contrast=100、opaqueWindows=true、fonts 和三项 semanticColors；未知结构安全跳过 |

五项不适用编辑器颜色是 window.activeBorder、window.inactiveBorder（Windows 不应用），contrastBorder、contrastActiveBorder 和 editor.selectionForeground（普通 Light/Dark 非高对比度主题）。其他公开但未注册的字段逐项 unsupported，不猜测私有替代字段。1.140.0 文档中的 gauge.* 等未注册项不写入主题。

正式清单中的 35 项含透明约束（32 项必须透明，另 3 项建议透明），独立 fixture 保存来源 SHA256、公开 ID 和各基线注册集。可分发 runtime 的 vscode_fields.json 使用显式角色、版本、处理条件、文字类别和真实背景配对；测试 fixture 不导入该映射，避免自证完整性。

## 实心策略与保留项

Appearance policy `2026-10-05.v4`、两套 Palette、实际实例和字段能力一起纳入 Plan Hash；缺少策略或字段契约变化的旧 Plan 在创建事务、Snapshot 和写目标之前拒绝，要求重新 Preview。Rollback 独立于 Plan，继续恢复历史事务的原有快照和产物。

Terminal 仅保留 One Tone Light/Dark 两套 Scheme/Theme，移除旧单套重复副本；defaults、所有 Profile 和已有 unfocusedAppearance 共用策略。字体、字号、轴、字形、padding、光标形状、Tab 偏好、rainbowFrame 及未知键保留。未知版本能力不写入不支持的外观字段、不宣称完整实心。支持能力缺失时报告 partial。

实心策略不取消编辑器装饰叠层的 alpha。查找高亮文字按叠层与编辑器 surface 合成后的背景校验；Diff/Merge 叠层保留语义区分，并保持区域对比度 >=1.2 和正文 >=7。悬停背景与未变的前景配对，状态文字 >=4.5，普通文字保持不透明。

Preview JSON 展示字段类别、处理策略、固定来源、版本、实际能力和生成值；不支持或保留字段不虚构生成值。Verify 校验完整 Light/Dark 主题内容、注册贡献的路径/类型/标签、settings、Chrome unpacked/ZIP manifest 及 TOML/Windows/Terminal 受管字段，不产生事务或配置写入。

## 验证与未验项

默认回归均使用临时目录和 fake backend，包括独立公开清单差集、叠层实际背景、ANSI 黑白区分、字体/未知键保留、未知版本、混合系统模式、高对比度 API 失败、完整只读漂移、事务局部补偿及历史恢复。执行入口见 [测试说明](testing.md)。没有引入新依赖、数据库、服务、插件运行时框架或通用 TOML 序列化层。

安装 metadata 只用于发现这一次 Preview 的基线：可解析 Scoop 转发启动器及编辑器 commit 子目录中的 cli.js 资源路径；不把开发机路径或产品版本写为运行时默认值。未核查的新 Workbench 版本安全跳过，需要新增固定来源和独立 fixture 后才能支持。

真实 Windows UI、TRAE 私有 AI 面板、ChatGPT App 内嵌终端、程序自带背景、dim/reverse/ANSI256/RGB 和真实 SSH 的最终显示仍未验收。Chrome 用户激活仍需人工确认；配置 verified 不提升为 rendering acceptance，报告保持 rendering_verification=untested。

本次自动验证结果：`uv run pytest` — **187 passed**；Skill 的 `uv run --project plugins/zen-one-tone-windows/skills/zen-one-tone-windows one-tone --help`、Python `compileall`、18 份变更 Markdown 的本地链接检查、工作区/暂存区 `git diff --check` 均通过。独立复制 Skill 后的只读 Chrome Preview 可运行；10 个 Seed × 两模式主题生成均通过。两轮 Standards/Spec 审查发现的问题已修复，复核无剩余可行动问题。未配置独立类型检查器。
