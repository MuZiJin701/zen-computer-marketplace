# zen-one-tone-windows

提供可独立分发的 `zen-one-tone-windows` Skill，用一个 Seed Color 统一 Windows 桌面、Windows Terminal、VS Code、TRAE、ChatGPT App 和 Chrome 本地主题。Cursor 暂不属于当前支持目标。

## 安装

```powershell
npm install -g skills
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g
```

只安装到 Codex：

```powershell
skills add https://github.com/MuZiJin701/zen-computer-marketplace.git -g -a codex
```

可选的 Codex Plugin Marketplace：

```powershell
codex plugin marketplace add https://github.com/MuZiJin701/zen-computer-marketplace.git
codex plugin add zen-one-tone-windows@zen-computer-marketplace
```

CC Switch：在 Skills 页面添加

```text
https://github.com/MuZiJin701/zen-computer-marketplace.git
```

然后安装 `zen-one-tone-windows`。

## 命令

```powershell
python .\scripts\run_one_tone.py preview '#10B981'
python .\scripts\run_one_tone.py apply plan-... --confirm
python .\scripts\run_one_tone.py verify plan-...
python .\scripts\run_one_tone.py rollback tx-...
```

Seed Color 是 ChatGPT App 和 Windows 的 Theme anchor/Accent source；ChatGPT App 的 `surface` 与 Windows 壁纸使用同一 Seed 派生的 Tonal surface，Light/Dark 大面积角色保持受控的明度跨度。ChatGPT App 会补齐缺失的 `fonts` table，保留已有字体值，并在两个 Mode 使用实心窗口与最高对比度。ChatGPT App、Windows Terminal、VS Code 和 TRAE 跟随 Windows 系统模式；Windows 本身不被切换，Chrome 主题仍需在 `chrome://extensions` 手动加载。Windows 自动取色开启时可能覆盖固定强调色。

Skill runtime 位于当前目录，使用 `uv` 运行：

```powershell
uv run --project . one-tone --help
```

## 开发边界

终端正文在 Light/Dark 都要求受管背景 `7:1`，其他功能文字为 `4.5:1`。ANSI black 与正文/white 分开映射，brightBlack 使用次要文字色。Windows Terminal `>= 1.16` 的原生 `adjustIndistinguishableColors = always` 在 Preview 按可执行文件版本发现、纳入 Plan Hash，并覆盖 defaults、所有 Profile 和已有未聚焦配置；未知/旧版本保留字段并报告 `partial`。配置与 PSReadLine Profile 均由事务 Snapshot/补偿/Rollback 管理。

PowerShell 命令和 Shell 发现使用 PowerShell 7 `pwsh`；不回退 Windows PowerShell，显式 `ONE_TONE_POWERSHELL_EXECUTABLE` 也必须验证为 Core `>= 7`。Profile 路径由该宿主在 Preview 提供，不改变 Windows Terminal 的默认 Profile。

ChatGPT App 内嵌终端使用独立 xterm/CSS 色表，其完整 ANSI 和原生前景修正没有已验证的用户配置入口。`verified` 只表示配置匹配，`rendering_verification = untested` 单独说明渲染尚未验收。Skill 内 `python .\scripts\terminal_readability_sample.py` 输出 default、ANSI16/256、RGB、dim、reverse 和选择检查样例；同一脚本可以通过标准输入用于真实 SSH，远端配置保持不变。完整验收步骤见仓库 [测试说明](../../docs/testing.md) 与 [证据记录](../../docs/terminal-readability-evidence.md)。

主题字段扩展的正式开发说明位于仓库的 docs/specs。它要求覆盖 Windows、Windows Terminal、VS Code、TRAE、ChatGPT App 和 Chrome 的公开颜色字段，并记录模式、版本能力和相邻区域可区分性；本 Skill 仍保持独立 runtime，不依赖仓库根目录。
