# 六目标公开主题字段完整覆盖、实心外观与瘦身

## Problem Statement

One-Tone 用户希望以一个明确主色统一 Windows、Windows Terminal、VS Code、TRAE、ChatGPT App 和 Chrome，但当前插件的支持声明、实际生成字段与官方能力存在差异：

- CLI 没有默认 Seed Color；现有绿色只是示例，容易被误解为运行时默认值。
- 部分公开颜色字段缺漏，部分生成字段不被目标解析器支持，Field inventory 仍可能把它们报告为 supported。
- 生成了 Light/Dark 产物并不代表窗口主题真正跟随系统；固定 Profile 覆盖和第三套固定主题可能阻断切换。
- 字体、窗口透明度与主题颜色的范围混在一起；用户需要实心窗口，但不需要修改字体。
- Verify 有只验证 frame 或只核查原来存在的语义字段的情况，无法证明完整主题符合 Plan。
- 重复字段清单和重复期望值增加维护成本，更新字段时容易产生不一致。

用户需要公开稳定颜色的完整生成与验证、准确的字段级能力边界、现有字体保留，以及可预览、可验证、可回滚的实心外观和系统模式跟随。

## Solution

文档示例统一使用用户选择的绿色 `#22C55E`；Seed Color 仍须显式输入，不增加默认值。由同一个 Seed 派生 Appearance-safe Palette 和 Light/Dark Mode，保持既有可读性与相邻区域区分。

对六个 Target 核查全部公开稳定、可写且适用的主题颜色，补齐生成和 Verify。字体及其他外观字段列入清单，明确受管修改、保留或不支持的策略。字体值保持原样，不新增字体修改入口。

未来确认 Plan 的 Apply 使用实心窗口策略：关闭 Windows 透明效果，关闭 Terminal Acrylic/Mica、将受管透明度设为实心并清除受管背景图片覆盖，将 ChatGPT App 外观设为 system。不切换 Windows 系统模式，不改变自动取色、高对比度或无关设置。Chrome 继续由用户手动选择并加载 Light/Dark 主题。

完整性与能力以固定官方证据及实际目标版本为准。ChatGPT App 的已验证运行时 schema、TRAE 专属字段与公开稳定 schema 分别报告，不猜测私有设置。瘦身只删除重复、无效和没有实际使用的内容，保留事务安全。

## User Stories

1. As a One-Tone user, I want 文档示例使用 `#22C55E`, so that 示例绿符合我选择的主色。
2. As a One-Tone user, I want Seed Color 继续必须显式输入, so that 工具不会静默选择颜色。
3. As a One-Tone user, I want 自定义其他 Seed Color 仍可使用, so that 示例色不会变成强制主题。
4. As a One-Tone user, I want 六个现有 Target 继续可用, so that 字段补齐和瘦身不会缩小支持范围。
5. As a One-Tone user, I want 全部适用的公开稳定颜色字段被生成和验证, so that 完整支持不只是常用字段的子集。
6. As a One-Tone user, I want 字段证据包含来源和版本基线, so that 支持声明可以核对。
7. As a One-Tone user, I want 未支持、实验和不适用字段有明确原因, so that 不可控能力不会伪装成成功。
8. As a One-Tone user, I want 颜色、字体和外观行为分别说明处理策略, so that 清单中的字段不会被误认为全部将被修改。
9. As a One-Tone user, I want Light/Dark 共享同一 Seed 的主题身份, so that 切换外观后仍是一套主题。
10. As a One-Tone user, I want 正文和语义文字按实际背景保持可读, so that 统一配色不损害阅读。
11. As a One-Tone user, I want 相邻界面区域可以区分, so that 编辑器、侧栏、工具栏和控件不会融成一片。
12. As a One-Tone user, I want 字体、字号、字重和字体特性保留, so that 主题工具不会改变我的阅读习惯。
13. As a One-Tone user, I want 不新增字体参数或配置入口, so that 当前需求不引入无用配置。
14. As a Windows user, I want 应用模式与 Shell 模式分别检测, so that Custom 混合模式下的能力判断正确。
15. As a Windows user, I want 高对比度通过有效系统 API 检测, so that 错误的 registry 键不会形成假证据。
16. As a Windows user, I want 系统透明效果在确认 Apply 时关闭, so that 系统外观符合实心策略。
17. As a Windows user, I want 系统模式、自动取色和高对比度保持原值, so that 主题不会覆盖我的系统偏好与辅助功能。
18. As a Windows user, I want Taskbar accent display 根据实际 Shell 能力报告, so that registry 写入不会被当作视觉成功。
19. As a Terminal user, I want Scheme 只包含解析器支持的字段, so that 无效的 selectionForeground 不会被报告为已生效。
20. As a Terminal user, I want 双模式窗口主题原生跟随系统, so that 顶部界面和终端正文不会使用错配主题。
21. As a Terminal user, I want 固定 tabColor 覆盖不阻断模式切换, so that 标签颜色来自实际活动主题。
22. As a Terminal user, I want defaults、所有 Profile 和已有 unfocusedAppearance 都执行实心策略, so that 非默认或失焦窗口不会留下旧透明配置。
23. As a Terminal user, I want 字体、padding、字形渲染、光标形状和其他偏好保留, so that 外观修复只改变已确认的主题策略。
24. As a Terminal user, I want Mica、边框和原生修正按实际版本判断, so that 旧版或未知版本不会被误标为支持。
25. As a VS Code user, I want 菜单、通知、Quick Input、Widget、diff、Chat 等完整公开颜色得到覆盖, so that 常见和较少使用的区域都遵循主题。
26. As a VS Code user, I want ANSI black、white 和 brightBlack 保持各自用途, so that 终端槽位不会全部坍缩为正文色。
27. As an editor user, I want 需要透明的选区和装饰性背景保留正确 alpha, so that 实心窗口策略不会遮盖底层内容。
28. As a TRAE user, I want 标准字段按自己的 Workbench 版本核查, so that 微软新版本字段不会被误报为 TRAE 支持。
29. As a TRAE user, I want 专属 AI 字段只在可发现且可验证时处理, so that 工具不会猜测私有配置。
30. As a ChatGPT App user, I want 两模式主题与 system 外观选择一致, so that App 原生跟随系统模式。
31. As a ChatGPT App user, I want 缺失 fonts 表只补空结构而已有字体不变, so that 主题结构完整而字体偏好保留。
32. As a ChatGPT App user, I want 缺失且可验证的 semanticColors 表和字段被补齐, so that 仅核查已有键不会被当作完整支持。
33. As a ChatGPT App user, I want 未验证的公开 UI 设置和内嵌终端能力被说明, so that 桌面主题不被误认为能控制全部终端渲染。
34. As a Chrome user, I want 主题采用合法 colors、tints 和 properties, so that 生成目录能被解析为预期主题。
35. As a Chrome user, I want 没有 NTP 图片时相关属性被标为不适用, so that 完整清单不会导致无需求的图片产物。
36. As a Chrome user, I want 两模式 canonical 目录和内部 ZIP 完整验证, so that frame 以外的篡改或缺失文件也会被发现。
37. As a Chrome user, I want 主题加载仍由我确认且内容字体不变, so that 工具保持原有激活与主题边界。
38. As a One-Tone user, I want Preview 展示所有新增受管设置并纳入 Plan Hash, so that Apply 只执行我确认的范围。
39. As a One-Tone user, I want 升级后的旧 Plan 不静默扩大写入范围, so that 新策略需要重新 Preview。
40. As a One-Tone user, I want 新增设置能够恢复原值或原来不存在的状态, so that 明确 Transaction Rollback 可完整撤销。
41. As a One-Tone user, I want 失败只补偿失败 Target 且恢复失败明确报告, so that 成功目标保留且错误不会被掩盖。
42. As a maintainer, I want 共享映射统一驱动生成和字段报告, so that 相同字段只有一份运行时定义。
43. As a maintainer, I want 无效键、重复库存、第三套固定主题和重复期望值被删除, so that 补齐字段不会继续累积维护负担。
44. As a maintainer, I want 使用现有 fixture、产物和 Transaction 测试边界, so that 回归检查可运行且不需要新框架。
45. As a One-Tone user, I want 配置匹配与真实渲染验收分开报告, so that 测试通过不会冒充桌面视觉通过。

## Implementation Decisions

- 复用现有 Palette、Field inventory、Target Adapter、实例发现和 Transaction 边界；不增加依赖、服务、数据库、通用设置框架或第二套运行时字段映射。
- Seed Color 必填契约不变；只更新公开示例绿。保留其他 Seeds 的回归输入，避免把示例选择变成配色算法的常量。
- 每个 Target 固定官方文档或源码证据基线，并与实际版本、公共 schema 或注册字段交叉核查。完整性检查须独立于生成映射本身；没有证据的字段不标 supported。
- Field inventory 区分 Color field、字体、外观行为、证据类型与处理策略，显示版本门槛、适用条件、生成值和实际能力。保留字段不能冒充已应用的新值。
- 微软完整公共字段集与 TRAE 可用字段集合分别判断。平台不适用、未注册、实验或未经验证的字段明确报告，不用软件相似性推导支持。
- 延续 Appearance-safe Palette、Mode coherence 和真实背景配对。普通正文、语义文字及选中态使用相应角色；普通相邻区域目标 1.2:1，交互边界目标 3:1，正文保留现有 7:1 基线，其他适用功能文字保持 4.5:1。
- 实心策略作用于窗口透明合成及受管背景覆盖。选区、diff、匹配和装饰性覆盖层仍遵守官方字段要求的 alpha，普通文字保持不透明；不能把所有 background 字段都机械写成不透明值。
- Windows 分别读取应用模式和 Shell 模式。高对比度使用官方 SystemParametersInfo/HIGHCONTRAST 能力；调用失败报告未确定，不伪造成功。
- Windows 加入透明效果关闭策略，注明所用配置机制的运行时与版本证据。AccentPalette、Afterglow 等 registry 机制不能统称官方稳定 schema。浅色任务栏能力按实际 Shell 模式报告，保持对比度安全的 Shell Accent。
- Windows 系统浅深模式、自动取色和高对比度保持不变；高对比度状态须显式影响能力报告，不以自定义主题覆盖其保护。每窗口 DWM 属性不扩展为遍历外部窗口的全局主题控制。
- Terminal 删除不受支持的 Scheme selectionForeground；Palette 的选择前景角色继续供 PSReadLine 等实际支持的入口使用，宿主选择前景效果独立验收。
- Terminal 窗口主题与 Scheme 均采用 Light/Dark 成对映射。取消受管固定 tabColor 覆盖，让活动双模式主题控制标签背景；仅保留两套实际使用的主题与 Scheme，删除第三套固定副本。
- Terminal 实心策略覆盖 defaults、各 Profile 和已有 unfocusedAppearance：关闭 Acrylic、按平台能力关闭 Mica、设置受管透明度为实心并清除受管背景图片覆盖。不可用或未知版本明确报告能力，不能仅保留旧值却宣称完整实心。
- Terminal 字体对象中的 face、size、weight、features、axes、cellWidth、cellHeight 及 padding、antialiasingMode、intenseTextStyle、cursorShape/Height、tab.showCloseButton/iconStyle 等非受管偏好保持原值，各字段门槛分别记录。原生前景修正与 PSReadLine 仍按既有能力发现和 PowerShell 7 范围处理。
- VS Code 对照完整公开颜色集扩展共享映射，补齐菜单、通知、Quick Input、Widget、diff、Chat、merge、notebook、debug、testing、终端选择等范围；移除未获公开字段证据的 panel.foreground。修正 ANSI 黑白槽位坍缩。
- VS Code/TRAE 继续使用原生 autoDetect 和扩展贡献的精确 Light/Dark 标签。保留字体、光标形状、终端渲染偏好、高对比度检测和主题偏好，不增加通用 UI 字体键、CSS 注入或透明窗口扩展。
- TRAE 只为当前版本可验证的标准 Workbench 与专属字段生成/验证；其余公开文档字段仍须出现在覆盖审计与限制说明中，不能静默遗漏。
- ChatGPT App 保持已验证 v1 运行时 schema 的适配边界，两模式实心窗口和高对比度策略继续使用，appearanceTheme 设为 system。公开 UI 说明不等于完整 TOML 配置契约。
- ChatGPT App 保留字体与未知配置；缺失必要 fonts 表只补空结构。完整支持的 semanticColors 表或键缺失时须补齐并验证；生成与 Verify 复用同一期望数据，避免只检查已有键的假完整性。
- Chrome 按固定公开解析器基线覆盖 24 个 colors 和 6 个 tints，包含遗漏的四种 background_tab、两种 frame_incognito、两种 tab_background_text_incognito 变体。删除无效的 omnibox_background_tint、omnibox_background_tab_switcher、incognito_tab、incognito_background、button_background_hover、separator；tints 补齐 frame_inactive、frame_incognito、frame_incognito_inactive。
- Chrome 使用 theme.properties 而非错误的 display_properties；公开属性为 ntp_background_alignment、ntp_background_repeat、ntp_logo_alternate。没有 NTP 背景图片时前两项标不适用，不为清单完整创建图片；logo 属性按模式处理。
- Chrome 不提供 theme manifest 字体、字号或全窗口透明度能力；不修改浏览器内容字体或 Preferences 来伪造支持。两个 canonical unpacked 目录继续由用户手动加载，ZIP 仅为内部产物。
- 删除 Terminal、VS Code、TRAE 中随后被共享映射覆盖的重复静态库存；Windows 字段分组使用完整实际值；Chrome Verify 改为完整受管 manifest 校验，覆盖两模式 canonical 目录和内部 ZIP。
- 新颜色字段、外观策略和版本能力在 Preview 中可见并进入 Plan Hash。旧 Plan 缺少升级所需的字段/策略证据时要求重新 Preview，不静默扩大历史授权；既有 Transaction 的明确 Rollback 继续可用。
- 每目标 Snapshot-before-write、原子写入、逐操作持久化、局部失败补偿和结果聚合保持不变。成功目标保留，补偿失败或没有成功目标时为 failed；混合成功和限制为 partial。
- Verify 继续只读，不 Snapshot、Apply、Restart 或 Rollback。新增设置可恢复原值和原来缺失状态；未知键及用户无关内容保持不变。
- 运行时行为落地时同步中英 README、Skill、目标矩阵、架构及测试契约；声明只能反映实际完成的能力。阶段性实现不能以常用字段覆盖宣称完整任务完成。

## Testing Decisions

- 最高验收边界复用既有 Plan → 目标配置/主题产物 → Transaction。通过输入 Seed、Target 与能力证据，观察产物、结构化结果及恢复状态；测试外部行为，不锁定私有 helper、数据结构组织或内部颜色搜索。
- 沿用现有 Palette/Plan、真实 Adapter 产物、临时文件、fake registry/desktop backend 和 Transaction 回归，不创建新的测试框架或测试运行时。
- 独立固定官方字段证据集与生成结果对照，发现遗漏、非法键、重复字段、版本误报和不适用字段误用。TRAE 的能力交集单独检查，不能只断言生成键等于自己的 mapping。
- 覆盖 Light/Dark 的全部适用受管颜色、透明约束、真实背景配对、语义文字区分和关键相邻区域。对代表性 Seeds 保留既有数值回归；示例色为 `#22C55E` 不替换所有历史输入。
- 对每个 Target 篡改一个非 frame 字段，Verify 必须报告不匹配。覆盖缺失产物、缺失语义键、两模式错配、实心策略偏离和未知键保留；Chrome 同时核查 canonical manifest 与内部 ZIP。
- Windows 测试覆盖应用/Shell 混合模式、高对比度 API 失败、任务栏真实能力限制与透明效果恢复；registry 写入成功不能自动成为视觉通过。
- Terminal 测试覆盖新旧/未知版本、边框/Mica 门槛、所有 Profile 与失焦覆盖、字体/非受管偏好保留、去除固定 Tab 覆盖和原生双模式跟随。选择前景不再作为 Scheme 支持字段断言。
- VS Code/TRAE 测试覆盖完整可用字段集合、alpha 必要性、平台不适用项、ANSI 黑白槽位和精确主题标签；现有字体与高对比度偏好保持不变。
- ChatGPT App 测试覆盖 system、两模式实心策略、必要 fonts 空结构、已有字体不变、缺失 semanticColors 补齐、未知键保留和不匹配 schema 的安全结果。
- Transaction 测试覆盖 Preview 不写目标、Plan Hash、旧 Plan 重新 Preview、Snapshot-before-write、逐操作持久化、失败补偿、恢复失败报告及完整 Rollback。新增字段原来不存在时也可恢复；历史回滚不能被新的 Apply 契约误阻断。
- CLI 未提供 Seed 仍失败；不新增字体参数或 appearance-file 入口。文档例子与声明按实际交付行为同步。
- 实施验证使用既有完整 pytest、Skill CLI help 与差异检查，只暂存本次任务修改；已有用户修改与暂存状态须保留。
- 本次规格发布不执行桌面应用、模式切换、重启或真实 SSH。fixture 和配置匹配与 Rendering acceptance 独立；真实 UI/SSH 未验项明确记录，不能声称视觉完整通过。

## Out of Scope

- 修改字体、字号、字重、字体特性，或新增字体配置入口；缺失的必要 fonts 空结构修复除外。
- 新增运行时默认主色、强制所有用户使用 `#22C55E`，或重写已有效的 Palette 算法。
- 修改 Windows 系统浅深模式、自动取色、高对比度、无关辅助功能、快捷键、启动设置及浏览器内容偏好。
- 猜测 TRAE 私有 AI 字段、ChatGPT App 未验证 TOML 字段或内嵌终端 ANSI 入口；修改 App bundle、渲染器或注入 CSS。
- 自动加载 Chrome 主题、自动重启应用、后台模式 watcher、远端配置修改或为无需求场景创建 NTP 图片。
- 引入新依赖、数据库、后台服务、复杂状态机、通用设置框架，或合并恢复语义不同的 Target Adapter。
- 保证任意程序指定的 ANSI/RGB/反色/弱化组合都能仅靠固定色表达标。
- 本次发布执行插件运行时修改、真实桌面 Apply、Git 提交、推送或合并。

## Further Notes

已发布：[GitHub Issue #22](https://github.com/MuZiJin701/zen-computer-marketplace/issues/22)，标签为 `ready-for-agent`、`enhancement`。

用户于 2026-10-05 通过 grill-with-docs 澄清上述需求，并明确要求以 to-spec 整理和发布。此次发布是开发任务的规格交付，运行时仍待实施；ready-for-agent 不代表代码或桌面验收已经完成。

当前 CLI 的 Seed Color 为必填，没有运行时默认绿。`#22C55E` 对应 Tailwind CSS v3 green-500；原示例 `#10B981` 对应 emerald-500。这里的“标准绿”指用户选择的本项目示例色，不声称行业通用唯一标准。[官方 palette](https://v3.tailwindcss.com/docs/customizing-colors)

2026-10-05 公开 VS Code 文档字段提取为 971 个 ID；现有映射 122 项，其中 121 项命中文档、初步差集 850 项，32 个文档字段存在明确透明约束。这是公开文档覆盖差，不是对每个安装版本可用性的证明。本机只读产品元数据为 VS Code stable 1.140.0，TRAE 产品 3.5.104、Workbench 基线 1.107.1；它们只作为调查记录，不写为跨机器运行时常量。[Theme Color Reference](https://code.visualstudio.com/api/references/theme-color)、[固定文档基线](https://github.com/microsoft/vscode-docs/blob/8889b0542cb2144fb53f5f53bd19c1395e2d9fa1/api/references/theme-color.md)

Windows 的现代主题设置不提供覆盖全部应用的统一字体字段；每窗口 DWM 属性和 legacy theme Metrics 不能当作全局主题覆盖。高对比度 API、Shell 模式和个性化能力需分别核查。[Windows 颜色](https://support.microsoft.com/en-us/windows/experience/personalization/personalize-your-colors-in-windows)、[SystemParametersInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow)、[HIGHCONTRASTW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-highcontrastw)、[theme 文件格式边界](https://learn.microsoft.com/en-us/windows/win32/controls/themesfileformat-overview)

Terminal 的固定稳定源码基线不支持 Scheme selectionForeground；原生主题设置支持成对 Light/Dark 选择。字体、透明度、背景与窗口能力按各自门槛核查。[Profile appearance](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance)、[Themes](https://learn.microsoft.com/en-us/windows/terminal/customize-settings/themes)、[v1.25.2733.0 schema](https://github.com/microsoft/terminal/blob/v1.25.2733.0/doc/cascadia/profiles.schema.json)、[Scheme parser](https://github.com/microsoft/terminal/blob/v1.25.2733.0/src/cascadia/TerminalSettingsModel/ColorScheme.cpp)

编辑器字体、集成终端字体及原生对比度修正属于外观核查清单，本需求保留现值。原生修正不保证所有最终渲染通过。[Terminal Appearance](https://code.visualstudio.com/docs/terminal/appearance)、[系统主题跟随](https://code.visualstudio.com/docs/configure/themes)、[固定编辑器选项](https://github.com/microsoft/vscode/blob/1.140.0/src/vs/editor/common/config/editorOptions.ts)、[固定终端选项](https://github.com/microsoft/vscode/blob/1.140.0/src/vs/workbench/contrib/terminal/common/terminalConfiguration.ts)、[固定主题选项](https://github.com/microsoft/vscode/blob/1.140.0/src/vs/workbench/services/themes/common/themeConfiguration.ts)

TRAE 官方公开主题选择与编辑器设置，未找到专属 AI 完整颜色 schema。OpenAI 官方 Settings 公开颜色、UI/code 字体、字号、translucent sidebar、contrast 与 pointer cursor 等 UI 设置，未建立对应桌面 TOML 完整契约。[TRAE 设置](https://docs.trae.cn/ide_ide-settings)、[OpenAI Settings](https://learn.chatgpt.com/docs/reference/settings)

Chrome 固定公开解析器基线支持 24 个 colors、6 个 tints 和三个 properties，现实现有八个公开颜色缺漏及六个无效颜色键。它没有 theme manifest 字体或全窗口透明度字段；固定源码基线仍需与实际安装版本交叉核查。[Chrome themes](https://developer.chrome.com/docs/extensions/develop/ui/themes)、[固定 Chromium parser](https://github.com/chromium/chromium/blob/77270bd36581caca2ab02fe4526cc921560ad089/chrome/browser/themes/browser_theme_pack.cc)

共享 Palette、Field inventory 单一事实源、Mode coherence、系统模式保持及事务安全的现有 ADR 继续适用。此规格扩展外观字段核查，取代此前保留 ChatGPT App appearanceTheme 的目标策略，改为已明确选择的 system；不修改历史决策原文或把目标行为描述成既有实现。示例色是可逆选择，无需独立 ADR。

现有环境完整 pytest 基线为 **168 passed**；规格导航、敏感路径检查与 Git 差异检查已通过。基线通过不证明上述功能已实现，也不证明真实桌面或 SSH 渲染通过。

## 实施状态（2026-10-05）

上述发布记录为实施前历史。本次运行时按规格扩展显式公开字段映射、版本能力、实心策略、字体与未知偏好保留及完整只读 Verify；Appearance policy/实际能力进入 Plan Hash，旧 Plan 重新 Preview，历史事务恢复保持独立。清单覆盖为 971 个公开编辑器 ID，与已核查 1.107.1/1.140.0 注册集相交后分别生成 896/957 项；透明约束进一步核查为 35 项（32 必须、3 建议），不把调查差集或开发机版本视为所有机器的能力。

固定来源、适用性、回归与真实 UI/SSH 未验项见 [实施证据](../theme-field-coverage-evidence.md)、[架构](../architecture.md)、[测试契约](../testing.md) 和 [ADR 0010](../adr/0010-evidence-backed-appearance-policy.md)。外部 Issue 未更新；没有桌面 Apply、重启、安装或推送。实现/fixture 通过不代表最终视觉验收完成。
