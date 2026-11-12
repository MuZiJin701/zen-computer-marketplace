# Zen Computer Marketplace

[English](README.en.md)

面向极简、有序电脑使用场景的跨 Agent Skill 市场。

当前维护唯一 Plugin `zen-one-tone-windows`，用一个 Seed Color 统一 Windows 桌面、Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity 和 Chrome 本地主题。

One-Tone 支持 Windows 10 22H2+（build `>= 19045`）和 Windows 11 22H2+（build `>= 22621`）；Cursor 暂不在主题支持列表中。

## 安装

推荐使用 Vercel Labs Skills CLI 全局安装，让其他兼容 Agent 也能复用：

```powershell
npm install -g skills
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

只安装到 Codex：

```powershell
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g -a codex
```

不安装 CLI 时：

```powershell
npx skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

管理 Skill：

```powershell
skills list
skills update zen-one-tone-windows
skills remove zen-one-tone-windows
```

安装后重启 Codex。Skills CLI 的 Codex 全局目录是 `~/.codex/skills/`。

可选：Codex Plugin Marketplace：

```powershell
codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git
codex plugin add zen-one-tone-windows@zen-computer-marketplace
```

可选：CC Switch。在 Skills 页面添加以下仓库地址，刷新后选择 `zen-one-tone-windows`：

```text
https://github.com/MuZiJin701/zen-computer-marketplace.git
```

## 使用

直接告诉 Agent 你要做什么。若未指定颜色或需要选择范围，Agent 会通过弹窗卡片让你点选；选定后可直接通过 `sync` 一站式完成 `Preview → Apply → Verify`，或按需单独预览。

### 统一 Windows 主题

```text
使用 $zen-one-tone-windows，把我的电脑主题统一为绿色 #22C55E。
```

### 执行规则

- 支持一站式 `sync '#22C55E'`（依次执行 Preview、Snapshot + Apply、Verify），也支持分步 `preview`、`apply --confirm`、`verify`
- Preview 只生成 Plan，不修改电脑
- Apply 只执行已有 Plan，并在每个目标修改前创建 Snapshot；失败目标自动回滚
- Verify（verify）只读检查结果
- Rollback 支持 `rollback --latest`（默认回滚最新事务）或按明确的 Transaction ID 回滚
- 结果会说明 `ok`、`partial`、`failed` 或 `skipped`

## 注意事项

- Seed Color 作为 Theme anchor/Accent source；ChatGPT App Surface、Antigravity `customThemeSeeds*` / `hubSurfaceBackgroundColor` 和 Windows 壁纸使用派生的 Tonal surface。确认 Apply 后关闭 Windows 透明效果，同步 `AccentColorInactive` 与 `Control Panel\Colors\Background`；ChatGPT App 使用 `appearanceTheme = system`、`accentSource = custom`、实心窗口和最高对比度；已有字体值保持不变，只补齐缺失的 `fonts` table。
- Windows Terminal 覆盖 defaults、所有 Profile 和已有未聚焦配置；按 Preview 发现的版本关闭 Acrylic/Mica、设 `opacity = 100`、清空背景图片、移除固定 `tabColor`。同时注册 `One Tone Light` 和 `One Tone Dark` 两套 Scheme 与窗口主题，并将窗口 `theme`、`applicationTheme`、defaults 与所有 Profile 的 `colorScheme` 默认设为深色主题 `One Tone Dark`（`dark`）。
- PowerShell 命令与 Shell/PSReadLine 发现使用 PowerShell 7 `pwsh`，不自动选择 Windows PowerShell；显式宿主覆盖也必须验证为 Core `>= 7`。这不改变 Windows Terminal 的默认 Profile。
- Terminal 正文在 Light/Dark 都按受管背景 `7:1` 验收，其他功能文字为 `4.5:1`。ANSI black 用作受管背景，white/brightWhite 为正文色，brightBlack 为次要文字色；任意 ANSI 组合仍需实际渲染复核。Preview 读取 Windows Terminal 可执行文件版本，`>= 1.16` 时为 defaults、所有 Profile 和已有未聚焦配置启用 `adjustIndistinguishableColors = always`，并支持 Verify 和事务回滚；未知/旧版本保留该字段并报告 `partial`。
- ChatGPT App 内嵌终端使用独立的 xterm/CSS 色表；当前没有可验证的用户配置入口控制完整 ANSI 表或原生前景修正。桌面主题 Verify 不代表内嵌终端、dim、reverse、256 色、RGB 或真实 SSH 视觉验收通过，报告中的 `rendering_verification` 保持 `untested`。
- VS Code、TRAE、Antigravity IDE 按公开文档与本机 Workbench 版本注册表的交集生成主题，覆盖菜单、通知、Quick Input、Widget、Diff、Chat、Merge、Notebook、Debug、Testing、Gauge、窗口边框与选区前景等适用字段，保留透明装饰叠层并检查真实背景配对。优先使用 C 盘标准配置目录（`%APPDATA%\<App>\User\settings.json` 与 `~/.<app>/extensions`），不改动 Scoop 便携目录结构，同时对已存在的 Scoop `data/` 便携目录执行镜像同步。
- Windows 开启“自动从背景中选取强调色”时，系统可能覆盖固定强调色；想保持稳定颜色，请在 Windows 设置中关闭该选项。
- Chrome 生成完整公开的 24 个 colors、6 个 tints 和适用 properties；没有 NTP 背景图时省略无作用的对齐/重复属性。Light/Dark 两个 canonical unpacked 目录由用户在 `chrome://extensions` 手动加载，ZIP 是内部产物；浏览器字体和窗口透明度没有主题入口，保持原值。
- `.one-tone` 默认固定在 Skill 根目录下，与 Agent 当前工作目录无关；Target 路径仍通过用户目录、PATH、launcher 参数或环境变量探测，不依赖开发机盘符、Everything 或机器临时路径。仅测试或明确的高级用法可以覆盖运行时目录。

## 仓库结构

```text
.
├─ .agents/plugins/marketplace.json       # Marketplace 清单
├─ plugins/                               # 可安装的 Plugin
│  └─ zen-one-tone-windows/               # zen-one-tone-windows Plugin
│     └─ skills/zen-one-tone-windows/     # zen-one-tone-windows Skill 与 runtime
├─ tests/                                 # Marketplace、Plugin、Skill 测试
├─ docs/                                  # 架构、测试、ADR 和开发说明
└─ CONTEXT.md                             # 项目领域词汇
```

更多细节见 [领域上下文](CONTEXT.md)、[zen-one-tone-windows Skill](plugins/zen-one-tone-windows/skills/zen-one-tone-windows/SKILL.md)、[目标矩阵](plugins/zen-one-tone-windows/skills/zen-one-tone-windows/references/targets.md) 和 [测试说明](docs/testing.md)。任务使用 GitHub Issues；Agent 协作配置见 docs/agents/。

## 开发说明

已确认的主题字段覆盖、浅深模式、相邻区域可区分性、版本能力和验收范围见 [主题字段覆盖与相邻区域可区分性开发说明](docs/specs/2026-07-25-theme-field-coverage-and-separation.md)。当前结构审计见 [架构说明](docs/architecture.md)。

完整公开字段、示例绿 `#22C55E`、实心外观与瘦身的 [开发规格](docs/specs/2026-10-05-official-theme-coverage-and-slimming.md) 已落实到运行时和 fixture 回归；来源、版本能力及真实界面未验项见 [字段证据](docs/theme-field-coverage-evidence.md)。新 Appearance policy 和字段能力纳入 Plan Hash；旧 Plan 必须重新 Preview，已有事务仍可按 ID 回滚。

TRAE Git decoration、Windows Terminal PSReadLine 预测颜色和 Windows 任务栏模式恢复见 [主题回归与可移植 Shell 集成开发说明](docs/specs/2026-08-03-theme-regressions-and-portable-shell-integration.md)。

终端功能文字实现范围见 [终端可读性 spec](docs/specs/2026-10-05-terminal-readability.md)，配置、宿主能力及真实界面未验项见 [验收证据](docs/terminal-readability-evidence.md)。可在两个宿主分别运行 Skill 内 `python .\scripts\terminal_readability_sample.py`；真实 SSH 诊断可通过标准输入执行同一脚本，不写入远端文件。运行样例只证明输出覆盖，最终显示仍需人工复核。

当前结构保留“根测试 harness + 可独立分发 Skill runtime”的边界；新增 docs/specs 作为主动开发说明目录，历史规划材料不作为当前架构入口。

维护者验证 One-Tone 的流程是：`sync '#22C55E'` 或 `preview '#22C55E'` → `apply plan-... --confirm` → `verify plan-...` → `rollback --latest`（或 `rollback tx-...`）。Skill 目录内的入口示例是 `python .\scripts\run_one_tone.py preview '#22C55E'`。
