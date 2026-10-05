# Documentation

主动文档和历史材料分开：

~~~text
docs/
├─ agents/       # Agent 协作配置
├─ specs/        # 当前开发说明
├─ architecture.md
├─ testing.md
└─ adr/          # 长期架构决策
~~~

历史设计和实施记录不作为当前结构入口。当前代码、分发边界、工作站行为和测试契约分别以 architecture、Skill package、对应开发说明和 testing 文档为准。

当前工作站 Plugin 的开发说明见 [Zen 工作站规范插件](specs/2026-07-26-zen-workstation-plugins.md)。

当前终端功能文字工作见 [spec](specs/2026-10-05-terminal-readability.md)、[验收步骤](testing.md) 和 [能力与未验记录](terminal-readability-evidence.md)。历史 spec/ADR 保留原决策；当前双 Mode 正文 `7:1` 要求以此 spec 为准。

六目标公开主题字段、实心窗口策略与瘦身已按 [开发规格](specs/2026-10-05-official-theme-coverage-and-slimming.md) 实施；[字段证据](theme-field-coverage-evidence.md) 记录版本清单、字段数量、自动验证与真实界面未验项。外部 Issue 状态未修改。
