# 修复 Windows Terminal、ChatGPT App 内嵌终端与 SSH 的功能文字可读性

Status: configuration-implemented / rendering-acceptance-pending — 配置修复和 fixture 回归已实现；完整真实界面矩阵仍有未验项，不能宣称完整验收。

Issue: [#21](https://github.com/MuZiJin701/zen-computer-marketplace/issues/21)

## Problem Statement

One-Tone 主题应用后，Windows Terminal、ChatGPT App 内嵌终端及其中的 SSH 会话存在局部功能文字不清晰的问题。已提供的截图中，终端编辑器的深色内容区显示近黑正文，底部状态栏偏暗；浅色终端里的路径、版本信息及输入占位提示偏淡。默认正文可读不能证明这些区域也可读。

当前终端字段映射将默认 foreground 与 ANSI black、white、brightBlack、brightWhite 绑定到同一 Visual role。程序把这些槽位同时用于前景和背景时，会出现颜色相同、对比度为 1:1 的组合。这是代码可证明的缺口，但尚未复现截图对应的完整输出，不能据此认定所有截图的根因相同。

现有检查主要验证 Palette 角色相对预设背景的对比度，以及配置字段是否与 Plan 一致。它们不能证明程序自带背景、256 色、显式 RGB、dim、reverse 或选中态最终渲染可读。ChatGPT App 的桌面主题与其内嵌终端也不能假定共享 Windows Terminal Scheme。

## Solution

在保留 Seed Color 身份和浅深 Mode coherence 的前提下，让验收集合中的 Terminal functional text 清晰可读：两种 Mode 的正文相对实际背景至少 7:1；语法/ANSI 彩色文字、路径、状态、占位提示和选中态文字至少 4.5:1。装饰图案允许弱化，颜色语义仍需可区分。

先修复可复现的共享 Palette 或终端字段映射问题；对程序指定色及渲染属性，优先使用宿主已验证的原生前景修正能力。若宿主修复后仍有问题，将实际复现的本地程序主题配置纳入同一安全、可回滚的流程。只修改本地配置；真实 SSH 会话是必验场景，远端配置保持不变。

验收同时包含 fixture 回归、数值检查和真实界面复核。无法控制或无法验证的内容需要明确报告限制或未验项，不能以配置 Verify 成功代替最终渲染通过。

## User Stories

1. As a Windows Terminal user, I want ordinary terminal text readable in Light Mode, so that I can read commands and output on the generated Tonal surface.
2. As a Windows Terminal user, I want ordinary terminal text readable in Dark Mode, so that switching Mode does not introduce faded or invisible output.
3. As a ChatGPT App user, I want its embedded terminal readable in Light Mode, so that I can use terminal tools inside the App.
4. As a ChatGPT App user, I want its embedded terminal readable in Dark Mode, so that the App provides the same functional readability across Modes.
5. As a terminal user, I want ANSI semantic text readable against its actual background, so that errors, warnings and success messages remain distinguishable.
6. As a terminal user, I want ANSI black and white slots to retain useful foreground and background relationships, so that terminal applications do not produce invisible text from collapsed colors.
7. As a terminal user, I want paths and version information readable, so that I can identify my working context.
8. As a terminal user, I want status bars readable, so that application state and keyboard hints remain useful.
9. As a terminal user, I want input placeholders readable while remaining secondary, so that I can recognize where and how to enter a command.
10. As a terminal editor user, I want text readable in an application-owned dark content region, so that editor backgrounds do not hide the document body.
11. As a terminal user, I want selected text readable, so that selecting a region does not make its contents disappear.
12. As a terminal user, I want reverse-video text readable, so that applications can highlight controls without losing their labels.
13. As a terminal user, I want functional dim text checked after rendering, so that a valid source color does not conceal information once weakened.
14. As a Windows Terminal SSH user, I want remote output readable in the local host, so that SSH sessions remain usable without editing remote theme files.
15. As a ChatGPT App SSH user, I want remote output readable in its embedded terminal, so that remote work does not depend on launching another terminal host.
16. As a terminal user, I want representative 256-color output included in acceptance, so that testing does not stop at the configurable ANSI 16-color table.
17. As a terminal user, I want representative explicit RGB output included in acceptance, so that application-specified colors are not mistaken for Scheme-controlled colors.
18. As a user of a unified theme, I want Seed Color identity retained in surfaces and emphasis, so that improving readability preserves the One-Tone appearance.
19. As a user of a unified theme, I want region lightness adjusted when readability requires it, so that theme identity does not make functional text unusable.
20. As a terminal user, I want decorative graphics allowed to remain subdued, so that readability changes focus on functional information.
21. As a Windows Terminal user, I want supported native foreground correction used for indistinguishable colors, so that application-specified colors can benefit from host rendering capabilities.
22. As a user of an affected local terminal application, I want its supported theme settings adjusted when necessary, so that problems outside the host Palette can be resolved.
23. As a user running Preview, I want host and local-program configuration capabilities discovered without writes, so that I can review the intended scope before Apply.
24. As a user running Apply, I want the selected configuration inputs included in the validated Plan, so that Apply cannot silently modify a different instance.
25. As a user running Apply, I want every modified configuration captured before its write, so that a failed change can be restored.
26. As a user running Apply, I want unrelated settings and unknown keys preserved, so that a color repair does not erase other preferences.
27. As a user running Verify, I want configuration verification to remain read-only, so that checking a theme cannot reapply or repair it.
28. As a user running Rollback, I want an explicit Transaction to restore only its own changes and verify restoration, so that recovery remains bounded and reliable.
29. As a user encountering a Target failure, I want successful Targets retained and failed compensation reported accurately, so that the result does not conceal data-loss risk.
30. As a user with an unsupported host or program version, I want its limitation reported without guessed writes, so that unsupported settings remain safe.
31. As a maintainer, I want regression tests to assert generated behavior and transaction outcomes, so that implementation refactors do not require tests for private helpers.
32. As a maintainer, I want the current Seed Color and representative green and yellow Seeds tested in both Modes, so that the repair is not tuned to one screenshot.
33. As a maintainer, I want Codex CLI, the pictured terminal editor and diagnostic output checked in both local hosts and their real SSH sessions, so that the accepted scenarios are reproducible.
34. As a user reviewing verification results, I want configuration matches, visual passes and untested cases distinguished, so that a successful field readback is not presented as complete rendering proof.
35. As a user of an SSH workflow, I want remote configuration and application themes left unchanged, so that local readability repair does not alter the server.
36. As a maintainer, I want support boundaries and evidence updated with the implemented capabilities, so that future users understand which output is controlled and which remains limited.

## Implementation Decisions

- 复用现有共享 Palette 生成器、终端字段映射、Field inventory、宿主 Adapter 与 Plan/Transaction 边界；优先在实际共同原因所在的最小共享位置修复，不建立第二套字段注册表。
- ANSI 槽位需要按真实前景和背景用途映射。修复黑白槽位坍缩，保护代表性文字/背景组合；不要求任意颜色组合或故意同色输出都能仅靠一张色表满足阈值。
- Terminal functional text 的正文在 Light 与 Dark 都以实际背景 7:1 为验收要求；其他功能文字以 4.5:1 为要求。Dark 正文标准高于当前共享 foreground 的 4.5:1 门槛，调整共享生成器前必须检查其他 Target 的调用方和回归影响。
- 保留 Theme anchor、Tonal surface、Neutral primary text、语义文字与选择颜色的职责。可读性优先，允许区域明暗调整，但不能把全部功能文字变成单色或用无理由的纯黑/纯白兜底替代 Appearance-safe Palette。
- Windows Terminal 的原生前景修正采用已确认允许的 adjustIndistinguishableColors 的 always 范围；按实际安装版本验证能力，并纳入原有 Plan、字段报告、Apply、Verify 与 Rollback。该字段不自动证明达到 7:1 或 4.5:1。
- 独立查明当前 ChatGPT App 内嵌终端的主题来源与可用原生能力，不把桌面主题的 ink、contrast 或 Windows Terminal Scheme 当作内嵌终端的完整证据。
- 内嵌终端或本地程序只使用有证据支持且可验证的配置能力；未知结构、不可支持的版本或未验证字段安全跳过或报告限制，不猜测私有字段。
- 程序主题调整只覆盖实际复现问题的本地程序。宿主与程序的配色来源分别记录，不能以宿主配置已匹配推断程序配色已修复；不预建通用 TUI 适配框架。
- 新发现的本地程序配置沿用现有安全流程：Preview 发现且不写入；被选择的实例和配置输入纳入 Plan Hash；Apply 前 Snapshot；JSON 配置同目录临时文件加原子替换；其他已支持格式使用既有原子写入机制。
- 保留用户未涉及的配置、字体、键绑定和主题模式选择。工具不替用户切换 Windows 系统浅深模式、AutoColorization 或高对比度设置。
- Apply 后持久化每个操作；失败时只补偿失败 Target，其他成功 Target 保持修改；至少一个 Target 成功且有失败或 skipped 才报告 partial，没有成功或补偿失败则报告 failed。
- Verify 继续只读并核对 Plan，不 Snapshot、Apply、Restart 或 Rollback。真实渲染验收是独立证据，不能由配置 Verify 自动声称完成。
- Rollback 需要明确 Transaction ID，仅恢复该事务自己的 Snapshot 或产物，并验证恢复结果；可回滚范围必须包含新增的原生字段与本地程序配置修改。
- SSH 是输出与本地渲染的验收边界。远端程序决定输出样式，本地宿主渲染；此次不修改远端配置，也不通过改写 SSH 输出替代主题修复。
- 数值和真实界面检查覆盖程序实际背景、弱化、反色及选中态。缺少可验证原生能力、缺少远端程序或无法建立真实 SSH 会话时报告限制/未验项，不把未验证结果标为完整通过。
- 本功能仍属于 Skill-local runtime，保持安装位置可移植；能力发现和运行不能依赖开发机固定盘符、用户目录或 Plugin 元数据。
- 支持字段、能力状态、命令或验收行为发生变化时，同步对应 Target 说明、Field Evidence Matrix、架构与测试文档；不扩大其他 Target 的功能需求。

## Testing Decisions

- 测试边界沿用用户已确认的 Plan → Adapter → 配置产物及 Transaction 行为；真实终端渲染是单独的人工验收入口。优先复用这些现有边界，不新增测试专用框架或运行时抽象。
- 好的回归检查从 Seed Color、Mode 与被选择能力产生 Plan，观察生成配置、持久化操作、AdapterResult、字段能力和 Rollback 结果；不绑定私有颜色搜索或字符串拼接实现。
- 复用既有 Palette/Plan、Windows Terminal 全 Profile、PSReadLine 发现与受管区块、ChatGPT App TOML 保留未知键，以及 Transaction Snapshot/补偿/回滚测试的 temporary-file 和 fake-backend 模式。
- Palette/配置产物检查覆盖当前主色、#10B981 与 #FFD700 的 Light/Dark 对，验证实际可控背景上的正文 7:1、其他功能文字 4.5:1，以及 Seed Color 身份、Mode coherence 和语义区分。
- 留下能暴露当前槽位坍缩的最小回归：默认前景配 ANSI black 背景，以及 ANSI white 前景配 ANSI black 背景。修正原来锁定黑白槽位与默认前景相同的断言，按外部可读性行为验收。
- 原生前景修正测试检查支持与不支持宿主、Profile 直接覆盖和默认配置、Apply 后字段值、Verify 对偏离 Plan 的报告，以及 Rollback 恢复原值或原来不存在的字段。
- 本地程序配置测试从可发现且被选择的实例出发，检查 Preview 无写入、Plan 绑定、Snapshot-before-write、原子写入、未知键保留、失败补偿和回滚。没有选择的程序与远端配置不得被访问修改。
- 保留 Verify 只读、Plan Hash 校验、安全路径组件和 per-Target 结果聚合的既有回归；配置匹配不允许替代真实渲染验收。
- 诊断样例覆盖 default、ANSI16、256 色、RGB、dim、reverse 与 selection 的代表性可见组合；样例用于观察宿主渲染，不能通过禁止所有应用指定色来使测试通过。
- 真实界面矩阵如下，每行覆盖当前主色、#10B981 与 #FFD700：

| 宿主 | 会话 | Mode | 必验程序与内容 |
| --- | --- | --- | --- |
| Windows Terminal | 本地 | Light / Dark | Codex CLI、图示终端编辑器、诊断样例 |
| Windows Terminal | 真实 SSH | Light / Dark | Codex CLI、图示终端编辑器、诊断样例 |
| ChatGPT App 内嵌终端 | 本地 | Light / Dark | Codex CLI、图示终端编辑器、诊断样例 |
| ChatGPT App 内嵌终端 | 真实 SSH | Light / Dark | Codex CLI、图示终端编辑器、诊断样例 |

- 实施时查明图示编辑器的实际程序和版本，在每个可用场景复现正文、语法文字、路径、状态栏、占位提示、输入区与选中态；重点复核深色编辑区的暗正文/状态栏和浅色终端的弱化路径/占位提示。
- 记录宿主、程序版本、Seed、Mode、场景、对比度和视觉通过/失败/未验结果。fixture、录制输出或回读配置不能替代真实 SSH；存在必验场景未验或不达标时，不能宣称完整验收通过。
- 默认 fixture 检查不修改真实桌面或已安装应用。真实主题应用与截图验收单独执行，继续遵守 Preview → Apply → Verify → Rollback 的范围确认。
- 实施验证使用现有完整 pytest 套件、Skill CLI 帮助命令和差异检查，然后完成真实界面矩阵。本次规格整理只做文档检查及发布内容核对，不执行运行时修复或真实主题 Apply。

## Out of Scope

- 修改远端配置、远端程序主题、SSH 服务或服务器环境；仍有远端配色问题时独立记录，另行决定。
- 保证任意终端程序、任意前景/背景组合、故意隐藏文字或无能力证据的输出都自动达到阈值。
- 修改 ChatGPT App 或 Windows Terminal 的原生渲染器，猜测未验证私有配置，或增加输出代理来改写终端/SSH 流。
- 把全部 ANSI/语法/状态颜色改成同一个正文色，或把装饰图案提升到功能文字对比度要求。
- 字体、布局、字号、键绑定、预测来源、主题模式偏好与系统辅助功能设置的重设计。
- 其他 Target 的新增功能；共享代码被修改时仍需保证它们的既有行为与安全契约。
- 新数据库、后台服务、模式 watcher、复杂状态机、通用插件/TUI 框架或第二套 Field inventory。
- 自动安装缺少的远端应用，或把模拟 SSH 当成真实 SSH 通过证据。
- 本次发布规格时实施代码修复、自动应用真实主题、提交或推送仓库修改。

## Further Notes

### 2026-10-05 实施范围

已修复 Windows Terminal 默认正文/white 与 ANSI black 的槽位坍缩，brightBlack 使用次要文字色，显式双 Mode foreground 的验证门槛统一为 `7:1`。原生 `adjustIndistinguishableColors = always` 按可执行文件 `>= 1.16` 的版本资源在 Preview 发现并纳入 Plan，覆盖 defaults、所有 Profile 与已有未聚焦配置；旧/未知版本保留字段并报告 partial。新增字段沿用 Snapshot、原子写入、只读 Verify、目标补偿和明确事务回滚。

用户随后明确要求选择 PowerShell 7 而非 Windows PowerShell。Shell 发现现在只使用 `pwsh` 或显式指定且验证为 Core `>= 7` 的宿主，不自动回退 legacy Profile；未找到 PowerShell 7 时跳过预测子能力。该偏好不改变 Windows Terminal 宿主选择、默认 Profile 或系统模式。

独立查明 App 26.930.4958.0 内嵌 xterm/CSS 的主题来源；未发现已验证的完整 ANSI/minimumContrastRatio 用户配置入口，相关子能力报告 unsupported，未修改 App bundle 或私有字段。尚未确认截图中的编辑器身份，因此没有猜测或修改本地程序主题。两个宿主均明确区分配置匹配与渲染 untested，附带无配置写入的诊断脚本。当前主色 `#00C853` 与代表性 Seeds 的数值、版本证据和 SSH/界面未验项见 [验收记录](../terminal-readability-evidence.md)。

用户于 2026-10-05 已确认需求范围、数值标准、原生前景修正、本地程序主题调整边界和最小验收集合。本规格是对已确认讨论的整理，不是新一轮需求访谈。

ADR 0001/0002 的共享 Palette 与 Field inventory 单一事实源、ADR 0004 的 Appearance-safe Palette、ADR 0008 的字段证据与真实截图验收、ADR 0009 的可发现 Shell 能力和事务边界继续适用。本需求将终端正文的 Dark 门槛提高到 7:1，并在实际复现时扩展此前 App 迁移规格对 CLI/TUI 配色的排除范围；不据此声称桌面主题字段能控制所有 CLI/TUI 输出。

Windows Terminal 原生修正字段的依据是 [微软 Adjust indistinguishable colors 文档](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance#adjust-indistinguishable-colors)。它描述按背景调整前景的能力，没有承诺本规格的全部对比度阈值。

相关工作：[Light Mode 可读性 #9](https://github.com/MuZiJin701/zen-computer-marketplace/issues/9)、[ChatGPT App 主题结构 #13](https://github.com/MuZiJin701/zen-computer-marketplace/issues/13)、[Terminal 字段映射与证据 #17](https://github.com/MuZiJin701/zen-computer-marketplace/issues/17)。本规格处理跨宿主的终端功能文字渲染，不以这些 Issue 的配置产物检查代替真实 SSH 验收。

截图仅作为症状来源；其中展示的文档内容不构成本需求指令。本次发布不附带包含用户文档内容、机器路径或账号信息的截图。
