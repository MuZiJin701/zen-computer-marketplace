# zen-one-tone-windows

[English](README.en.md)

提供可独立分发的 `zen-one-tone-windows` Skill，用一个主色（Seed Color）统一 Windows 桌面、壁纸、Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity、MATLAB（`>= R2025a`）和 Chrome 本地主题。Cursor 暂不属于支持目标。

## 安装与使用

首选通过 `skills` CLI 安装，也支持各主流 Agent 的原生插件安装命令；详细步骤与各宿主调用方式见[安装指南](https://github.com/MuZiJin701/zen-computer-marketplace#1-安装与更新)和[使用说明](https://github.com/MuZiJin701/zen-computer-marketplace#2-使用方法)。

在 Skill 目录（`skills/zen-one-tone-windows/`）下可直接运行本地脚本：

```powershell
python .\scripts\run_one_tone.py sync '#22C55E'
python .\scripts\run_one_tone.py preview '#22C55E'
python .\scripts\run_one_tone.py apply plan-... --confirm
python .\scripts\run_one_tone.py verify plan-...
python .\scripts\run_one_tone.py rollback --latest
```

也可以直接用 `uv` 查看命令帮助：

```powershell
uv run --project . one-tone --help
```

## 安全与使用说明

- **先预览、再备份、可回滚**：`preview` 只生成计划不改系统；`apply` 修改每个应用前都会自动保存快照，失败目标自动回滚，也支持随时用 `rollback --latest` 恢复。
- **保留个人习惯**：不会改动字体设置和无关偏好；若 Windows 开启了“自动从背景中选取强调色”，系统可能会覆盖固定主色。
- **Chrome 原生动态主题**：直接向 Google Chrome 活跃 Profile 的 `Preferences` 写入主色（`kTonalSpot`）并清理新标签页自定义背景，随系统浅/深模式实时热切换（不再生成扩展目录）；写操作前会自动温和关闭（3 秒超时后强杀、写完不自动重开）运行中的 Chrome/MATLAB 进程以防覆盖磁盘改动，若账号同步中的旧主题覆写修改，在「自定义 Chrome」重置一次默认主题即可。
- **独立边界**：本 Skill 包自带完整运行时，可独立于仓库根目录运行，支持目标与版本能力细节见 [目标矩阵](skills/zen-one-tone-windows/references/targets.md) 和 [测试说明](../docs/testing.md)。
