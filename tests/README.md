# Tests

测试目录按 Marketplace → Plugin → Skill 的层级组织：

~~~text
tests/
├─ marketplace/                         # Marketplace manifest 和索引
├─ plugins/<plugin-name>/               # Plugin envelope
│  ├─ test_plugin.py                    # Plugin contract
│  └─ skills/<skill-name>/              # Skill package contract
│     ├─ test_skill.py
│     └─ runtime/                       # 该 Skill runtime 的行为
~~~

当前 runtime 测试按 Plugin 和 Skill 分开：One-Tone 位于 `tests/plugins/zen-one-tone-windows/skills/zen-one-tone-windows/runtime/`，Desktop zero 和 Scoop toolchain 的行为测试分别位于对应 Plugin 的 Skill 测试目录，与可分发 Skill 的目录边界对应。

默认测试使用临时目录和 fake backend，不触碰真实桌面、不提权、不终止进程，也不安装真实软件。真实桌面删除、进程处理、Scoop 和 winget 测试必须单独标记并说明风险。

One-Tone 的 runtime/fixtures 保存独立固定来源清单：公开编辑器 ID、文档 Hash、alpha 约束及两套 Workbench 注册集。完整字段差集、合成背景/状态文字、实心策略、字体与未知偏好保留、版本发现、API 失败、只读漂移及旧 Plan 拒绝均通过 Plan → Adapter 产物 → Transaction 边界检查。它们不替代真实界面验收；来源与未验项见 [字段证据](../docs/theme-field-coverage-evidence.md)。

终端回归从 Plan 经 Adapter 检查生成 Scheme、原生修正的版本能力、defaults/Profile/未聚焦覆盖、只读 Verify、PSReadLine 写入失败补偿和明确事务回滚；诊断脚本检查代表性 ANSI 输出及无文件写入。fixture、配置回读与真实 SSH 输出捕获均不替代最终渲染验收，步骤和未验项见 [测试说明](../docs/testing.md) 与 [证据记录](../docs/terminal-readability-evidence.md)。
