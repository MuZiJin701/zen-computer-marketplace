# Zen Computer Marketplace

[English](README.en.md)

用一个主色（Seed Color）统一你的 Windows 桌面、壁纸和常用软件外观，目前包含唯一插件 `zen-one-tone-windows`。

- **支持应用**：Windows 桌面与壁纸、Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity、MATLAB（`>= R2025a`）、Chrome。
- **支持系统**：Windows 10 22H2+（build `>= 19045`）和 Windows 11 22H2+（build `>= 22621`）；Cursor 暂不在主题支持列表中。

## 1. 安装与更新

同一宿主选择下面一种方式安装即可（首次安装推荐用 `skills` CLI）。

### 方式一：使用 `skills` CLI（推荐）

运行后按提示选择你使用的 Agent（Codex、Claude Code、Antigravity、Grok Build 或 GitHub Copilot CLI）：

```powershell
npm install -g skills
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

只安装到 Codex 时，可执行 `skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g -a codex`；不想全局安装 `skills` 时，可把 `skills` 替换为 `npx skills`。

常用管理命令：

```powershell
skills list
skills update zen-one-tone-windows -g
skills remove zen-one-tone-windows
```

如果使用 `cc-switch`，直接在 Skills 页面添加仓库地址 `https://github.com/MuZiJin701/zen-computer-marketplace.git`，刷新后选择 `zen-one-tone-windows` 即可。

### 方式二：使用各 Agent 原生插件命令

| 宿主 | 安装命令 |
| --- | --- |
| Codex | `codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git`<br>`codex plugin add zen-one-tone-windows@zen-computer-marketplace` |
| Claude Code | `claude plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`claude plugin install zen-one-tone-windows@zen-computer-marketplace` |
| Antigravity | `agy plugin install https://github.com/MuZiJin701/zen-computer-marketplace` |
| Grok Build | `grok plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`grok plugin install zen-one-tone-windows --trust` |
| GitHub Copilot CLI | `copilot plugin marketplace add MuZiJin701/zen-computer-marketplace`<br>`copilot plugin install zen-one-tone-windows@zen-computer-marketplace` |

安装或更新后，请开启新会话再调用。

## 2. 使用方法

为避免误改系统外观，该 Skill 设为**仅显式调用**。使用前请在客户端中主动选中它：

- **Codex**：输入 `$` 并选择 `zen-one-tone-windows`
- **Claude Code**：输入 `/zen-one-tone-windows`（独立安装）或 `/zen-one-tone-windows:zen-one-tone-windows`（插件安装）
- **Antigravity / Grok Build / Copilot CLI**：输入 `/zen-one-tone-windows` 或从斜杠菜单中选择

直接告诉 Agent 你想要的主色（或需要调整的应用范围）：

```text
使用 $zen-one-tone-windows，把我的电脑主题统一为绿色 #22C55E。
```

### 工作流与安全回滚

- **一键同步（`sync '#22C55E'`）**：依次完成 `Preview`（生成 `Plan` 预览，不修改电脑）、自动备份并应用（`Apply`）、只读检查（`Verify`）。
- **分步操作**：也可以让 Agent 分步运行 `preview`、`apply plan-... --confirm` 和 `verify plan-...`。
- **随时回滚**：每次应用前都会自动保存快照，单个目标失败时自动回滚，不影响其他已完成目标；之后可随时运行 `rollback --latest` 恢复最近一次改动，或按明确的 `Transaction ID` 回滚历史操作。
- **状态说明**：结果会清晰标明 `ok`（完成）、`partial`（部分字段受版本限制保留原样）、`failed`（失败并已回滚）或 `skipped`（跳过）。

## 使用提示

- **Windows 强调色与壁纸**：应用后会同步逐屏壁纸并关闭系统透明效果，并自动采用 Windows 原生自定义模式（系统外壳深色 + 保持你的应用浅/深模式）以稳定显示任务栏主题色；壁纸、桌面底色、非活动标题栏及 Shell 强调色均由主色直接派生且与浅/深应用模式无关（切换应用浅/深模式时无需重跑 `sync`），回滚时原样恢复；如果开启了“自动从背景中选取强调色”，系统可能会覆盖固定主色，建议先关闭该开关。
- **Chrome 原生动态主题**：直接向 Google Chrome 活跃 Profile 的 `Preferences` 写入基于主色的 Material 3 种子色（`kTonalSpot`）并清理新标签页自定义背景图，自动随系统浅/深模式实时热切换（不再生成双套扩展包）；执行 `sync`/`apply`/`rollback` 时如检测到 Chrome 正在运行会先温和关闭（3 秒超时后强杀，写完不自动重开），请先保存网页中未提交的内容；若重启后被 Chrome 账号同步中的旧主题覆写，在「自定义 Chrome」重置一次默认主题或关闭主题同步即可。
- **明暗模式与终端**：Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity、MATLAB（`>= R2025a`）和 Chrome 均默认跟随系统应用浅/深色模式自动切换；若安装了 PowerShell 7（`pwsh`），终端启动时还会自动适配对应深浅模式的预测与语法色。
- **MATLAB 同步注意**：MATLAB 仅统一内容区、编辑器与语法配色（不修改安装包内置工具条外框，结果标为 `partial`），保留绘图主题（`GraphicsTheme`）与开关；执行 `sync`/`apply`/`rollback` 时如检测到 MATLAB 正在运行会先温和关闭（3 秒超时后强杀，写完不自动重开），请先保存未保存的代码或工作区变量。
- **保留个人设置**：不会改动你的字体或无关偏好；旧版应用不支持的字段会保持原样并标记为 `partial`。

## 仓库结构与本地开发

```text
.
├─ .claude-plugin/marketplace.json        # 共用 Marketplace 索引
├─ plugin/                                # 可安装的 One-Tone 插件包
│  ├─ plugin.json                         # Agent Plugins 1.0 清单
│  ├─ .claude-plugin/plugin.json          # Claude Code 包内清单
│  └─ skills/zen-one-tone-windows/        # Skill 与独立运行时
├─ tests/                                 # 分发检查与运行时测试
├─ docs/                                  # 架构、测试与 ADR 文档
└─ CONTEXT.md                             # 领域词汇表
```

在仓库根目录运行自动化测试，或在 Skill 目录下直接调试 CLI：

```powershell
uv run pytest
uv run --project plugin/skills/zen-one-tone-windows one-tone --help
```

在 `plugin/skills/zen-one-tone-windows` 目录下可执行完整命令行流程，例如：

```powershell
python .\scripts\run_one_tone.py preview '#22C55E'
```

（同样支持 `sync '#22C55E'`、`apply plan-... --confirm`、`verify plan-...` 和 `rollback --latest`。）

更多开发者资料见[领域词汇 (CONTEXT.md)](CONTEXT.md)、[Skill 说明](plugin/skills/zen-one-tone-windows/SKILL.md)、[目标矩阵](plugin/skills/zen-one-tone-windows/references/targets.md)、[架构说明](docs/architecture.md)、[测试说明](docs/testing.md)和[架构决策](docs/adr/)。
