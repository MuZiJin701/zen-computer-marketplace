# One-Tone 项目协作规则

## Agent skills

### Issue tracker

任务和需求使用 GitHub Issues；发布、读取或更新 ticket 前先读 docs/agents/issue-tracker.md。

### Triage labels

Triage 使用默认的五个状态标签；分类、状态映射和更新规则见 docs/agents/triage-labels.md。

### Domain docs

这是 single-context 项目；探索前读根目录 CONTEXT.md 和相关 ADR，术语、决策与需求文档的读写规则见 docs/agents/domain.md。

## 项目目标

这是一个小型、可验证、可回滚的 Windows 主题统一工具。核心流程：

~~~text
Preview → Apply → Verify → Rollback
~~~

支持范围以 `zen-one-tone-windows` 的 Target 矩阵（`plugin/skills/zen-one-tone-windows/references/targets.md`）为准，不根据相似应用猜测兼容性。
当前平台范围包括 Windows 10 22H2+（build >= 19045）和 Windows 11 22H2+（build >= 22621）。

## 仓库结构

- plugin/：Marketplace 指向的可安装 Plugin 包。
- plugin/skills/zen-one-tone-windows/：`zen-one-tone-windows` 中可独立分发的 Skill 包和唯一运行时项目。
- tests/：根目录下的分发检查和 `tests/runtime/` 下的运行时测试，均留在 Plugin 包之外。
- docs/：架构、测试、Agent 协作配置和 ADR。
- 根目录 pyproject.toml：仅用于开发和测试，不安装运行时包。

Skill 不得依赖 Codex Plugin 元数据、仓库根目录、开发机绝对路径或固定盘符才能运行。

## 核心安全规则

- Preview 只生成 Plan，不修改系统或应用配置。
- Apply 只接受已有 plan_id，应用前必须校验 Plan Hash；`sync` 命令按顺序组合 `Preview → Apply → Verify`。
- Skill 层面需要用户选择 Seed Color 或目标范围时，通过宿主弹窗工具（如 `ask_question`）让用户点选，不在纯文本对话中停顿等待。
- 每个目标修改前必须 Snapshot。
- 目标失败时只回滚失败目标；其他成功目标保持修改。
- Apply 每个操作后必须持久化事务记录；补偿回滚失败必须报告 failed。
- 至少一个目标成功且其他目标失败或 skipped 时才报告 partial；没有成功目标时报告 failed。
- Verify 只读取当前配置并与 Plan 对比，不创建事务、不 Snapshot、不 Apply、不 Restart、不 Rollback。
- Rollback 支持 `--latest`（或省略 `transaction_id` 默认回滚最新事务）及显式 `transaction_id`，只能恢复该事务自己的快照或产物元数据，并验证恢复结果。
- 只修改用户明确选择的目标，不猜测未知目标兼容性。
- Plan ID、Transaction ID 和 target 必须是安全路径组件；未知 target 可安全 skipped，但不得创建越界路径。
- Plan、事务和目标配置 JSON 使用同目录临时文件加原子替换，避免中断造成截断文件。
- 事务快照默认保留最近 5 个已完成事务；只清理工具生成的数据。
- Seed Color 保留为 Theme anchor/Accent source；ChatGPT App surface、Antigravity `customThemeSeeds*` / `hubSurfaceBackgroundColor` 与 Windows 壁纸/底色/非活动标题栏均跟随当前 Windows 应用模式（`AppsUseLightTheme`，壁纸经 `IDesktopWallpaper` 逐屏设置、快照与校验）使用派生 Tonal surface。Windows 采用原生自定义模式（将 `SystemUsesLightTheme` 设为深色 `0` 并开启 `Personalize\ColorPrevalence = 1`，同时保持用户 `AppsUseLightTheme` 不变，Rollback 原样恢复并广播刷新），`AccentPalette` 按微软真实 8 槽 `RGB0`（`Light3..Base..Dark3, Extra`）写入，基础 Shell Accent 在 OKLCH 中保护固定白色图标 `3:1`；确认 Apply 关闭透明效果，保持应用模式、AutoColorization、高对比度和字体，不引入后台常驻服务。高对比度开启或 API 未知时安全跳过 Windows。
- Cursor 暂不属于用户可见支持目标；显式输入 cursor 必须安全 skipped，不得访问或修改 Cursor 文件。

## 当前实现边界

- Windows Terminal 覆盖 defaults、所有 Profile 及已有 unfocusedAppearance（支持 JSONC 注释与尾随逗号）；按版本关闭 Acrylic/Mica、设实心 opacity、清空背景图片、移除固定 tabColor，并保留字体和非受管偏好。同时注册 `One Tone Light`（`applicationTheme = light`）与 `One Tone Dark`（`applicationTheme = dark`）两套 Scheme 和窗口主题，默认在 `>= 1.17` / `>= 1.16` 上按 `{light, dark}` 配对跟随系统应用模式。平台能力另行校验，未知项报告 partial。Scheme 不写 selectionForeground。
- Windows Terminal 正文在两种 Mode 的受管背景均要求 `7:1`；原生 `adjustIndistinguishableColors = always` 按 Preview 发现的版本能力应用（优先 Win32 版本 API，不强依赖 `pwsh`）。Shell/PSReadLine 默认只选 PowerShell 7 `pwsh`，不回退 Windows PowerShell，受管块启动时按 `AppsUseLightTheme` 自适应浅/深预测色与核心语法色；配置 Verify 与真实渲染验收分别报告。
- VS Code / TRAE / Antigravity IDE 以固定公开清单与实际 Workbench 注册字段的交集为范围；支持 1.x Workbench（`<1.140` 映射 `1.107.1`，`>=1.140` 映射 `1.140.0`），未知版本安全跳过，支持 JSONC 配置读取并扩展常见语言 TextMate 高亮。优先使用 C 盘标准配置目录（`%APPDATA%\<App>\User\settings.json` 与 `~/.<app>/extensions`），不改动 Scoop 便携目录结构，同时对已存在的 Scoop `data/` 便携目录执行镜像同步。透明装饰叠层与实心窗口策略分开，文字检查真实合成背景；普通 VS Code 校验通过报 `ok`，TRAE / Antigravity IDE 私有 AI 面板保持 `partial`/`unsupported`。
- Antigravity 桌面端（`antigravity`）保持独立 Adapter，管理 `~/.gemini/config/config.json` 与 `%APPDATA%\Antigravity\app_storage.json`。
- MATLAB 桌面端（`matlab`）保持独立 Adapter，面向已验证的 `>= R2025a` Web 桌面（基线 `R2026a`），离线原子读写 `matlab.mlsettings`（`MATLABTheme=System`、双模式 `DesktopColors` / `SyntaxHighlightingColors` 含 `HighlightCurrentLineColor`/`LineColor` 与 Light 单键 RGB 同步），保留 `GraphicsTheme`、字体与功能开关；不修改安装包 `themes.json`，窗口 Chrome 报 `unsupported`/`partial`，并受 `Live-process write guard` 与字段级 Rollback 保护。
- Chrome 使用 Manifest V3 本地主题，覆盖框架、工具栏、标签、书签页、NTP、链接和地址栏文字，按 Chromium `0.5` 中性基准生成 `tints` 并区分 Light/Dark 显示名；激活仍由用户手动确认。
- 普通正文在实际受管背景以及深层背景文字目标为 7:1，其他功能/状态文字为 4.5:1；结构分隔线（`border`）柔和克制，交互焦点边界保持 3:1，主色与代码语义色避撞，视觉 accent 不直接作为文字色，装饰叠层按合成背景校验。
- Codex（`chatgpt-app`）保持独立 Adapter，不与 VS Code/TRAE/Antigravity IDE Adapter 合并；支持在有效 `config.toml` 中安全初始化缺失主题表及替换内联 `semanticColors`。

## 技术约束

- 使用 Python 和 uv。
- 核心保持精简，不引入数据库、后台服务、复杂状态机或插件运行时框架。
- Adapter 使用结构化 AdapterResult，不得只返回布尔值。
- 修改共享模块前先检查所有调用方；优先复用已有模块和依赖。
- 只实现当前需求，不预建未来抽象、兼容层或目录。

## 测试与交付

~~~powershell
uv run pytest
uv run --project plugin/skills/zen-one-tone-windows one-tone --help
git diff --check
~~~

默认测试使用 fixture，不修改当前桌面或已安装应用。真实桌面测试必须单独标记并明确风险。修改后报告实际运行的验证命令和结果。

保留无关的已有修改；未经明确要求，不提交、推送、发送消息、修改权限或影响生产资源。

## 文档同步

支持范围、命令、状态、目录结构或验收标准变化时，同步检查并按需更新：

- README.md
- docs/architecture.md
- docs/testing.md
- CONTEXT.md
- 对应 Skill 的 SKILL.md 和 references/targets.md
