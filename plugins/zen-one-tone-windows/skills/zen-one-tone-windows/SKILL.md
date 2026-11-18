---
name: zen-one-tone-windows
description: >-
  用一个主色统一受支持的 Windows 目标，支持预览、验证和回滚主题。
disable-model-invocation: true
---

# 统一 Windows 主题

默认处理全部已实现目标：`windows`、`terminal`、`vscode`、`trae`、`antigravity-ide`、`chatgpt-app`、`antigravity`、`chrome`。只有用户明确指定目标时才缩小范围；不要把“统一电脑主题”解释成只处理当前提到的一个应用。Cursor 暂不属于用户可见支持目标，显式指定时安全返回 `skipped`。

## 交互与简化流程

1. **弹框交互（不中途纯文本停顿等待）**：当用户未提供 Seed Color 或需要选择预设色/目标范围时，Agent 必须直接调用宿主选择题弹窗工具（如 `ask_question`）弹出选项卡片让用户点选。一旦用户已提供 Seed Color（或已在弹窗点选），直接执行 `sync`（一站式完成 `Preview → Apply → Verify`），不再停下来等待纯文本确认。
2. 若用户明确只要求预览（如“先预览，不要应用”），则运行 `preview`，展示 Plan ID 和每个目标的检测结果；不要自行创建只包含 Windows 的窄范围 Plan。
3. `apply` / `sync` 对每个目标独立 Snapshot、Apply 和内部检查，并在每个操作后持久化事务记录；失败目标自动回滚，其他成功目标保留。补偿失败报告为 `failed`；无成功目标时整体为 `failed`，混合成功/失败或需要用户操作时为 `partial`。
4. 用户需要重启应用时手动重启，可随时运行 `verify <plan_id>`。`vscode`、`trae` 和 `antigravity-ide` 优先使用 C 盘标准配置目录（`%APPDATA%\<App>\User\settings.json` 与 `~/.<app>/extensions`），不改动 Scoop 便携目录结构，同时对已存在的 Scoop `data/` 便携目录镜像同步配置与扩展。
5. 用户要求撤销时，直接运行 `rollback --latest`（或省略 `transaction_id` 默认回滚最新事务，也可指定明确的 `transaction_id`）；Chrome 生成的 ZIP/unpacked 产物通过事务元数据跨进程清理。

Windows 使用 Palette `accent` 派生更深的 Shell Accent 来统一 Start/Taskbar、标题栏/窗口边框、DWM 强调色（含 `AccentColorInactive`）、`Control Panel\Colors\Background` 和 Quick Settings 等固定白色图标的活动卡片；该 Shell Accent 必须保持白色图标 `4.5:1` 对比度。壁纸与其他 Target 保持现有 Theme anchor 和 Tonal surface 行为。Light/Dark 都尝试 Taskbar accent display，不修改 `AppsUseLightTheme`、`SystemUsesLightTheme` 或 `AutoColorization`。如果 Windows 自动取色已开启，必须提示用户手动关闭它，否则 Windows 可能在壁纸变化后覆盖固定强调色；如果系统忽略 Light-mode taskbar display，必须报告实际能力。Windows Terminal 会为所有 Profile 注册统一的 `One Tone Light` 与 `One Tone Dark` 两套 Scheme 和窗口 `theme`，移除固定 `tabColor`，并将窗口 `theme`、`applicationTheme`、defaults 与所有 Profile 的 `colorScheme` 默认绑定为深色主题 `One Tone Dark`（`dark`）；同时可发现、验证和回滚 Windows Terminal 会话中的 PSReadLine 预测颜色。VS Code、TRAE、Antigravity IDE 更新标准 Workbench（含 `window.activeBorder`、`window.inactiveBorder`、`editor.selectionForeground`、`gauge.*`）、Git decoration、选择/光标、终端 ANSI、链接、通知、诊断和语义高亮字段，并启用 `window.autoDetectColorScheme`；私有 AI 面板仍可能不受标准字段控制。

Seed Color 是 Theme anchor 和 Accent source；ChatGPT App 的浅色和深色主题表使用 appearance-safe 且保持 Mode coherence 的 Tonal surface（浅色模式高明度干净表面、深色模式深邃分层表面，对应大面积 Visual role 的 Light/Dark OKLCH 明度差上限 `0.75`）。两套主题的 `accentSource` 写为 `custom`、`contrast` 写为 `100`、`opaqueWindows` 写为 `true`，并将 `appearanceTheme` 写为 `system`。缺失的 `fonts` table 在 Apply 补齐，已有字体值不变。Antigravity 桌面端（`antigravity`）同步更新 `~/.gemini/config/config.json`（`userSettings.themeMode = THEME_MODE_INHERIT` 与 `customThemeSeedsLight` / `customThemeSeedsDark`）及 `%APPDATA%\Antigravity\app_storage.json`（`hubSurfaceBackgroundColor`）。Light Mode 的 Dense primary text 针对实际 Surface 使用不透明、低色度的 Neutral primary text 和 `7:1`，其他普通/强调文字使用 `4.5:1`；`background_foreground` 针对深层 `background` 保持 `7:1`。`muted_foreground` 仅供 inactive、placeholder、description 和语义状态使用，不得映射到 Dense primary text。语义文字色（`accent_text`、`error_text`、`warning_text`、`success_text`）在 OKLCH 空间保持饱满色度与语义色相并满足对比度目标。ChatGPT App 的 `semanticColors.diffAdded`、`diffRemoved`、`skill` 也必须分别使用 `success_text`、`error_text`、`accent_text`，不能直接使用 `success`、`error` 或 `accent`；`accent` 只用于强调背景、边框和系统强调色。普通角色不得无理由使用纯黑或纯白作为对比度兜底。

Chrome 目标生成 Manifest V3 的 Light/Dark 两个 canonical unpacked 主题目录；ZIP 只作为内部打包产物，不是额外的用户选项。Chrome 不允许普通本地 Skill 对任意扩展或主题执行安全的静默安装；因此必须由用户在 `chrome://extensions` 确认加载。企业策略或 Chrome Web Store 发布的扩展属于另一种部署方式，不在本 Skill 的权限范围内。

## 终端功能文字

确认 Apply 执行实心外观策略：Windows 写 `EnableTransparency = 0`；高对比度通过系统 API 读取，开启或未知时跳过 Windows。App/Shell 模式分别读取并保持，任务栏限制按实际 Shell 模式报告。Terminal 对 defaults、所有 Profile 和已有未聚焦配置按版本关闭 Acrylic/Mica、设 opacity=100、清空背景图片、移除固定 tabColor；保留字体、字号、字形、padding、光标形状、Tab 偏好、rainbowFrame 和未知键。`One Tone Light` 与 `One Tone Dark` 同时注册，窗口与 Profile 默认使用 `One Tone Dark`；平台限制另行校验，未知项保留并报告 partial，Scheme 不写 selectionForeground。

编辑器 Preview 读取自身启动器指向的 Workbench metadata，以固定公开清单和已核查的 1.107.1/1.140.0 注册字段交集生成主题。未知基线安全跳过，私有 AI 字段 unsupported。保持字体、光标形状、终端渲染和高对比度偏好；装饰性透明叠层保留 alpha，文字以合成后的实际背景验算。Chrome 仅生成 24 colors、6 tints 和适用 properties，不提供字体或全窗口透明度控制。

当前 Appearance policy 与字段能力纳入 Plan Hash。旧 Plan 必须重新 Preview；拒绝发生在创建事务和 Snapshot 之前，历史事务仍可独立 Rollback。Preview 的字段报告显示类别、处理策略、来源、版本、实际能力和生成值。Verify 检查完整 Light/Dark 内容和注册贡献路径/类型/标签；配置通过不代表真实界面已验收。

终端正文在 Light/Dark 的受管背景上都要求 `7:1`；ANSI 语义文字、路径、状态、占位提示和选中态要求实际背景 `4.5:1`。ANSI black 使用 surface，white/brightWhite 使用正文色，brightBlack 使用次要文字色，避免前景/背景槽位全部坍缩；一张色表不保证任意程序指定色组合。

Preview 读取 Windows Terminal 可执行文件版本；`>= 1.16` 时将 `adjustIndistinguishableColors = always` 能力与实际可执行文件纳入 Plan Hash。Apply 覆盖 defaults、所有 Profile 和已有 `unfocusedAppearance`，Snapshot/Verify/Rollback 覆盖新增字段；未知或旧版本保留字段并报告 `partial`。原生修正不自动证明最终对比度达标。

Shell/PSReadLine 默认只发现 PowerShell 7 的 `pwsh`，不选择或回退 Windows PowerShell `powershell.exe`。显式 `ONE_TONE_POWERSHELL_EXECUTABLE` 也必须经探测确认为 Core、版本 `>= 7`。没有 PowerShell 7 时跳过预测颜色子能力，保留 Windows Terminal Scheme；缺少 PSReadLine 公共字段时报告 `unsupported`。Profile 路径来自该宿主的 `$PROFILE.CurrentUserAllHosts`，纳入 Plan；Apply/Verify 使用同一实例，受管区块仅在 Windows Terminal 会话生效。执行本 Skill 的 PowerShell 命令也使用 `pwsh`。

ChatGPT App 内嵌终端使用独立 xterm/CSS 色表；已验证的桌面主题字段没有完整 ANSI 表或原生前景修正入口。该子能力报告 `unsupported`，保留 App 配置中的未知键。各宿主的报告均区分配置 `verified` 与 `rendering_verification = untested`；dim、reverse、256 色、RGB、应用自带背景和真实 SSH 需独立复核。

在两个宿主本地运行 `python .\scripts\terminal_readability_sample.py`，再把同一脚本经标准输入送入已有 SSH 会话。它不读写配置；手动选中示例文字检查选择状态，并使用实际 Codex CLI 和已确认名称/版本的编辑器复核。记录 Seed、Mode、宿主/程序版本、实际前景/背景、对比度和视觉通过/失败/未验。仅在复现并找到已验证配置入口后扩展本地程序主题；远端配置保持不变。详细字段与能力边界见 [目标矩阵](references/targets.md)。

## 命令

```powershell
python .\scripts\run_one_tone.py sync '#22C55E'
python .\scripts\run_one_tone.py preview '#22C55E'
python .\scripts\run_one_tone.py apply plan-... --confirm
python .\scripts\run_one_tone.py verify plan-...
python .\scripts\run_one_tone.py rollback --latest
```

需要缩小范围时再显式使用 `--targets windows,chatgpt-app`。Preview / Sync 的 `--targets` 默认值就是全部已实现目标。

`verify` 只读取当前目标并与 Plan 对比，不创建事务、不 Snapshot、不 Apply、不 Restart、不 Rollback。

Plan ID、Transaction ID 和 target 必须是安全路径组件。默认 `.one-tone` 运行时根目录固定在 Skill-local runtime root，由运行时模块位置解析，不随 Agent 当前工作目录变化；编辑器和 Terminal 的实际路径会优先使用 C 盘标准用户目录与 PATH 探测，也可通过 `ONE_TONE_<TARGET>_...` 环境变量覆盖。运行时不依赖 Everything、固定盘符、特定用户或安装管理器目录；需要配置实例发现的 Target 在 Preview 中解析唯一 Active Target instance（含便携目录镜像列表），并将路径纳入 Plan，Apply/Verify 不静默切换实例。fixture 测试不代表真实 Windows 桌面目标已验证。

## 已确认的主题字段开发范围

当前运行时按已确认开发说明覆盖 Windows、Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity 和 Chrome 的公开主题颜色字段，并支持浅色/深色 Mode、Field inventory、字段级 capability status 和相邻 UI region 可区分性。普通相邻背景目标为 1.2:1，选区/焦点/边框/强调控件目标为 3:1，Light Mode 的 Dense primary text 使用不透明、低色度 Neutral primary text 和 7:1，其他文字使用 4.5:1，深层背景文字使用 7:1。

同语义字段可以复用 Visual role；关键相邻 UI region 使用可区分的背景、边界和状态标记。Chrome 输出 Light/Dark 两个 canonical unpacked 目录和内部 ZIP；Windows Terminal 输出双 Scheme 并默认启用 `One Tone Dark`；Windows 分开报告 Accent color 与 Taskbar accent display，不改变系统模式、自动取色或高对比度设置；VS Code/TRAE/Antigravity IDE 使用扩展实际贡献的 Light/Dark 标签；ChatGPT App 与 Antigravity 以已验证运行时 schema 为边界；私有 AI 面板只处理可发现且可验证的字段。

完整决策见仓库 docs/specs 与 docs/adr 下的开发说明与架构决策记录；真实桌面字段仍需按测试说明单独验收。
