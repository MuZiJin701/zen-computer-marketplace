# Zen Computer Marketplace Domain Context

Zen Computer Marketplace 是面向极简、有序电脑使用场景的跨 Agent Skill 市场。当前专注于 `zen-one-tone-windows`——把同一 Seed Color 统一到受支持 Windows Target 的可验证、可回滚主题工具。

## Language

### Color language

**Seed Color**  
用户选择的源颜色，作为主题统一的起点和产品语义中的主色。  
_Avoid_: 随机主题色、默认主色

**Palette**  
由 Seed Color 派生的一组颜色角色，而不是一组按界面字段随意生成的颜色。  
_Avoid_: 颜色字典、字段颜色

**Theme anchor**

Seed Color 在 Palette 中保留的身份和色相来源，用于生成 Accent 和主题强调状态；它不要求直接铺满大面积 Surface。

_Avoid_: 所有背景必须使用的颜色

**Tonal surface**

围绕 Theme anchor 的低饱和、分明明度层级的背景角色，用于大面积界面区域；它保留主题色相但不复制 Seed Color 的完整饱和度。

_Avoid_: 把 Accent 直接当作所有背景

**Mode-independent tonal surface**

由 Seed Color 直接派生、与系统浅/深应用模式无关的低饱和中深调表面角色，用于 Windows 壁纸、桌面底色、非活动标题栏和 Antigravity Hub 底色等原生只支持单一色值的表面；它保留主题色相并保证桌面白色图标文字的可读性，同时通过同色系明度错位使非活动标题栏与壁纸和活动标题栏各自保持清晰边界。

_Avoid_: 直接铺满未降饱和的原始 Seed Color、在无后台监听时绑定当前应用模式导致切模式后校验失配

**Seed-driven native theme**

One-Tone 仅向宿主原生动态主题引擎提供 `Seed Color`（或编码后的原生颜色种子）与系统浅/深跟随开关，具体的浅色与深色表面层级和前景色对比度由宿主运行时算法（如 Chromium Material 3 `kTonalSpot`）自行派生，不由 One-Tone 逐字段生成或验算 24 色色板。

_Avoid_: 把原生派生主题当成逐字段校验的静态色板、声称已验收宿主内置算法的文字对比度

**Appearance-safe Palette**

同时满足文字可读性、视觉层级区分和极简舒适度（Zen）的 Palette；它严格保证正文 `7:1` 与功能/语义文字 `4.5:1`，在 OKLCH 中提供通透浅色与沉稳深色表面层级，区分柔和结构边框与高对比交互焦点边界，保持 Accent 色相身份，避免主色与代码语义色撞车，并禁止普通角色无理由坍缩为纯黑或纯白。

_Avoid_: 只通过对比度检查的 Palette、把所有装饰边框都强制高对比度

**Structural border**

用于分隔面板、卡片、标题栏和列表区域的低存在感结构分隔线；它在相邻背景上保持可见层级，但不要求达到交互控件的 `3:1` 高对比度门槛。

_Avoid_: 焦点边框、强强调色边框

**Interactive boundary**

用于焦点环、活动强调控件、主要按钮边框或明确交互态的视觉边界；它需要保持高辨识度（`>= 3:1`），与低存在感的 Structural border 分开。

_Avoid_: 所有面板分割线

**Visual role**  
Palette 中描述一种稳定视觉语义的角色，例如 surface、surface_subtle、surface_raised、foreground、selection 或 border。  
_Avoid_: 某个应用的临时颜色、每个字段一个颜色

**Adjacent UI region**  
在同一视图中视觉上相邻、需要彼此分辨的背景区域，例如工具栏与内容区、活动标签与非活动标签、面板与编辑器。  
_Avoid_: 任意两个颜色、所有颜色必须不同

**Color field**  
某个 Target 主题中接受颜色或色调的字段；是否可用由该 Target 的版本和字段证据决定。

_Avoid_: 所有配置项

**Appearance field**

Target 的主题颜色、字体、透明度或外观行为字段。字段出现在清单中不代表工具会修改它；保留、受管修改与不支持是不同的处理方式。

_Avoid_: 所有应用设置、列出即应用

**Appearance policy**

某次 Preview 明确记录并纳入 Hash 的受管外观策略，说明实心窗口、原生系统模式跟随和保留字体/系统偏好的处理边界；策略升级要求新的 Plan，不能静默扩大旧 Plan 的授权。

_Avoid_: 通用配置系统、后台主题监控

**Solid appearance**

受管窗口使用自身不透明背景，并关闭已验证入口中的 Acrylic、Mica、窗口透明合成及背景图片覆盖；编辑器选择、Diff 和匹配等装饰叠层仍可保留官方要求的 alpha。

_Avoid_: 所有颜色 alpha 都为 255、修改字体或高对比度

**Example Seed Color**

文档和命令示例使用的参考主色，不是省略颜色输入时自动选择的默认值。

_Avoid_: 默认绿色、强制主色

**Field Evidence Matrix**

按 Target、Mode、界面状态和相邻区域记录 Color field 的公开来源、实际语义与可读性证据，用于决定字段映射和验收；它不直接规定颜色值。
_Avoid_: 主题颜色抄录表、截图集合

**Dense primary text**

Light Mode 中需要连续阅读或快速辨认的普通文字，例如编辑器/终端正文、命令行输出、表格内容、导航标签和常规控件标签；它不包括选中态、禁用态或装饰性文字。
_Avoid_: 所有前景色、强调文字

**Terminal functional text**

终端中承载阅读、操作或状态信息的文字，包括正文、语法/ANSI 彩色文字、路径、状态栏、输入占位提示和选中态文字；纯装饰图案不属于此范围。

_Avoid_: 仅默认前景色、把装饰图案当作功能文字、把所有功能文字都称为 Dense primary text

**Native foreground correction**
终端宿主按实际背景修正难以区分的前景色的原生能力；能力可用不代表所有输出已达到功能文字的对比度要求。

_Avoid_: 修改程序输出、完整渲染通过证明

**Configuration match**
当前 Target 配置与 Plan 的受管字段一致，是 Verify 的检查结果。

_Avoid_: 真实界面通过、所有终端文字可读

**Rendering acceptance**
在明确宿主、程序、Mode、Seed 和本地或真实 SSH 会话中，对最终显示的功能文字进行数值检查与视觉复核。

_Avoid_: 用配置匹配或录制输出代替真实渲染

**Git decoration**
文件或资源管理器旁显示的版本控制状态标记，例如 added、modified、untracked、ignored 或 conflicting；它是语义状态文字，不等同于普通文件名或 Dense primary text。

_Avoid_: 把所有 Git 状态当作普通前景色、把 Git decoration 当作私有字段

**Inline prediction**
Shell 在用户已输入命令后、命令尚未接受前显示的预测补全文字；它由 Shell/命令行编辑器提供，不等同于 shell prompt、命令输出或 Windows Terminal Scheme 的普通 foreground。

_Avoid_: 提示符、命令输出、ANSI 语义文字

**Neutral primary text**

供 Dense primary text 使用的低色度、接近中性的文字角色；它可以脱离 Seed Color 的色相，以保持阅读清晰度，而 Seed Color 身份由 Tonal surface、Accent 和语义状态保留。
_Avoid_: 带主题色的所有文字、纯黑兜底

**Prediction foreground**
专供 Inline prediction 和未选中列表预测使用的可辨识文字角色；它由 Seed Color 派生，可使用受控色相偏移，但必须在实际预测背景上保持可读性，并与 Neutral primary text 保持可验证的感知距离。
_Avoid_: 直接复用 muted_foreground、Terminal foreground 或固定机器颜色

**Accent color**

Windows 或应用用于强调控件、链接、标题栏和边框的用户可见颜色。它可以存在于浅色和深色系统模式中。

_Avoid_: 任务栏一定会显示的颜色

**Taskbar accent display**

Windows Shell 把 Accent color 显示到开始菜单和任务栏的能力；Windows 仅在 Shell 为深色模式（`SystemUsesLightTheme = 0`）时原生支持并保留该开关。为在浅色应用环境下也原生保住任务栏主题色，One-Tone 采用 Windows 原生自定义模式（将 `SystemUsesLightTheme` 设为深色 `0`，同时保持用户 `AppsUseLightTheme` 不变），并在 Rollback 时恢复原始值。

_Avoid_: 绕过设置在浅色 Shell 下强写后被系统重置、修改用户应用深浅模式

**Windows Shell active tile**

Windows 快速设置、开始菜单、任务栏和活动标题栏中承载白色系统图标的强调色区域；它与微软 8 槽 `AccentPalette` 协同工作，基础 Shell Accent 以 WCAG 图形/图标 `3:1` 对比度保护白色图标，兼顾主色还原度与图标清晰度。

_Avoid_: 只校验 AccentPalette 注册表回读、把整个 8 槽压成单一暗色

**Desktop wallpaper state**

Windows Explorer 通过现代 `IDesktopWallpaper` 接口实际生效的多屏壁纸路径与底色状态，而非仅指旧版注册表 `Control Panel\Desktop\WallPaper` 的回读值；壁纸与桌面底色使用基于 Seed Color 的 Mode-independent tonal surface，多屏快照和回滚按屏幕分别保留与恢复。

_Avoid_: 仅以注册表壁纸路径代替真实桌面状态、多屏只备份主屏

### Target language

**Marketplace**  
仓库级的 Plugin 安装索引，登记可安装的 Plugin 及其来源。

**Plugin**  
由 Agent 宿主安装的发布单元，包含 Skill 及其随包资源。宿主可通过 Marketplace 或直接从插件包安装。

**Skill package**  
包含指令、参考资料及配套运行时的能力单元，可以独立安装，也可以随 Plugin 分发。

**Agent 宿主**

安装和调用 One-Tone Skill 的 Agent 客户端。宿主支持描述的是分发与调用能力，Target 描述的是可统一主题的应用或系统。

**Target**  
一个独立的主题集成：Windows、Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT desktop app、Antigravity desktop app、MATLAB desktop app 或 Chrome。
_Avoid_: 应用（当 Windows 系统也在讨论范围内时）

**ChatGPT desktop app**
当前 ChatGPT Windows/macOS 桌面产品，包含 Chat、Work 和 Codex 视图；本项目的 `chatgpt-app` Target 只管理桌面 App 的用户界面主题，不管理 Codex CLI/TUI。
_Avoid_: Codex CLI、Windows Terminal 主题

**Antigravity desktop app**
Google Antigravity 2.0 桌面客户端（Target 标识符 `antigravity`），通过 `~/.gemini/config/config.json` 的 `userSettings.themeMode`、`customThemeSeedsLight`、`customThemeSeedsDark` 以及 `%APPDATA%\Antigravity\app_storage.json` 的 `hubSurfaceBackgroundColor` 管理浅色/深色自定义主题种子与模式无关的 Hub 表面背景色。
_Avoid_: Antigravity IDE、浏览器插件

**Antigravity IDE**
基于 VS Code Workbench 的 Antigravity IDE 桌面编辑器（Target 标识符 `antigravity-ide`），与 VS Code、TRAE 共享同一套 VS Code 家族扩展主题与 `settings.json` 受管机制。
_Avoid_: Antigravity 2.0 桌面客户端

**MATLAB desktop app**
R2025a 及以上采用新 Web 桌面架构的 Windows MATLAB 客户端（Target 标识符 `matlab`），通过用户设置包 `matlab.mlsettings` 管理浅色/深色双模式内容区与语法配色及系统主题跟随；工具条、标题区和侧边栏等窗口 Chrome 属于不可修改的安装包内置样式（`unsupported`），图窗主题（`GraphicsTheme`）保持用户原值。
_Avoid_: MATLAB 旧版 Java 桌面（<= R2024b）、MATLAB 绘图主题、修改安装包 themes.json

**Live-process write guard**
对在退出时会用内存配置树覆盖磁盘文件的 Target（如 MATLAB desktop app 与 Chrome desktop browser），在 Apply 与 Rollback 写盘前及 `os.replace` 前校验目标进程已退出并拒绝盲写的安全边界；当进程枚举失败（`unknown`）或关闭后进程仍未退出时按 fail-closed 同样阻断写入。
_Avoid_: 在进程状态未知或未退出时盲写、后台监听同步

**Managed process shutdown**
仅在写操作阶段（Apply、`sync` 与 Rollback，严禁用于 Preview、Detect 或 Verify）针对受 `Live-process write guard` 保护的 `chrome` 与 `matlab` 进程执行的默认受管关闭流程：先发送温和关闭信号（最多等待 3 秒），超时仍未退出再强制结束进程，并经 `Live-process write guard` 复核已退出后才写入磁盘；写完后不自动重新打开应用，若进程枚举失败或未能退出则 fail-closed 阻断写入。
_Avoid_: 在只读阶段关闭进程、状态未知时执行强杀、写完后擅自重启应用

**Chrome desktop browser**
Windows 版 Google Chrome 桌面浏览器（Target 标识符 `chrome`，实测基线 Chrome 158）。One-Tone 不再生成 Manifest V3 双套扩展主题，也不修改 `Secure Preferences`、`Sync Data/LevelDB`、`account_values` 或猜测 Edge/Brave 等其他 Chromium 浏览器；而是配合 `Managed process shutdown` 与 `Live-process write guard` 离线原子更新活跃 Profile 的 `Preferences`（写入 `browser.theme.user_color2`、`color_variant2 = 1` `kTonalSpot`、`color_scheme2 = 0`、`follows_system_colors = false`、`extensions.theme.id = "user_color_theme_id"`，清理 `is_grayscale2`、`extensions.theme.pack`、`autogenerated.theme.color`、新标签页背景键 `ntp.custom_background_dict` / `ntp.custom_background_local_to_device` 与 `browser.theme.saved_local_theme`，并在存在 Chrome Sync 时自动执行 `Chrome theme sync isolation`），实现单配置随系统浅/深实时热切换的 `Seed-driven native theme` 及字段级 Rollback。
_Avoid_: MV3 静态双插件、静默安装扩展、修改 Sync 数据库或 `account_values`、按相似应用猜测 Edge/Brave 兼容性

**Chrome theme sync isolation**
仅针对已启用或已配置 Chrome Sync（或存在 `browser.theme.saved_local_theme`）的 Google Chrome 活跃 Profile，在不修改 `Secure Preferences`、`Sync Data/LevelDB` 与 `account_values`、也不开启“由组织管理”企业策略的前提下，将 `sync.keep_everything_synced` 设为 `false`（若此前开启全量同步则把未显式关闭的其他标准同步数据类型保留为 `true`）、关闭 `sync.themes`（以及存在的 `sync.data_type_status_for_sync_to_signin.themes`）并移除 `browser.theme.saved_local_theme`；使 Chrome 保留书签/密码/扩展等其余同步项的同时不再在启动时用云端旧主题或 `StopSyncing()` 保存的默认主题覆写离线 `Preferences` 改色。未启用 Sync 的纯本地 Profile 保持不创建 `sync` 节点，`Verify` 严格校验隔离状态，`Rollback` 按字段级精确还原。
_Avoid_: 保留 `saved_local_theme` 只关 `sync.themes`、仅离线重置默认主题并保持 `sync.themes = true`、在纯本地 Profile 凭空写入 `sync`、改动 `Secure Preferences`/`account_values`/企业策略

**Standard editor configuration priority**
对于 VS Code、TRAE 和 Antigravity IDE，工具优先解析并使用 C 盘标准配置目录（`%APPDATA%\<Editor>\User\settings.json` 与 `~/.<editor>/extensions`）作为主目标实例；若同一可执行文件旁已存在 Scoop 便携版 `data/` 目录或启动器目录，工具同步镜像写入、快照、校验和回滚该目录，避免因启动入口不同而漏加载主题，同时不修改或破坏 Scoop 目录结构。
_Avoid_: 强制迁移 Scoop 目录、仅写便携目录

**Theme registration**

Target 记录主题扩展或主题包，使其出现在可选择的主题清单中；仅有本地主题产物并不算注册成功。注册成功需要登记、登记指向的主题产物、贡献的主题标签和目标设置形成一致证据。注册成功不代表该主题已经成为当前活动主题。

_Avoid_: 已自动生效

**Active Target instance**
由同一个启动器/可执行文件、用户数据目录和扩展目录组成的 Target 配置实例。同一台机器可以有多个实例；不能仅凭用户名、固定盘符、安装管理器或默认目录猜测活动实例。

_Avoid_: 当前用户目录、唯一安装

**Theme activation**

Target 将已注册的主题明确设为当前活动主题；Light/Dark 变体是否自动切换由 Target 和用户偏好决定。

_Avoid_: 扩展已安装

**Window opacity mode**

ChatGPT App 决定窗口 chrome 使用实心绘制或透明合成的外观设置；透明合成的系统背板不属于当前 Palette 可控制字段。One-Tone 的 Canonical theme 必须在每个 Mode 写入并校验实心窗口模式，以保证窗口 chrome 使用主题 surface。

_Avoid_: Theme surface、只影响侧边栏的颜色设置

**Theme typography**

ChatGPT App 浅色和深色主题各自的 UI 字体与代码字体设置；主题完整性判断必须要求每个 Mode 存在 `fonts` table，但不要求 Tool 生成 `ui` 或 `code` 值，也不能仅以颜色字段匹配断言主题有效。

_Avoid_: 与主题无关的未知键、由颜色工具擅自选择的字体

**Canonical theme artifact**

面向用户的唯一推荐主题产物；同一 Mode 的压缩包、兼容别名和事务内部副本不属于可选主题。

_Avoid_: 每个生成文件都是一个主题

**Skill-local runtime root**

由 Skill 自身安装目录解析出的固定运行时根目录；默认的 `.one-tone`、Plan、Transaction 和生成产物都位于该目录下，与 Agent 当前工作目录无关。

_Avoid_: 当前命令所在目录

**Field inventory**  
某个 Target 在指定版本基线下应覆盖的 Appearance field 清单，是字段核查、测试和 Verify 的依据；公开字段与已验证运行时字段分别标明证据边界。

_Avoid_: 可能存在的字段、未经验证的私有字段

**Capability status**  
某个字段在实际 Target 上的状态：supported、applied、verified、failed、unsupported 或 not-applicable。公开文档清单与实际注册/平台条件共同决定适用性；字段出现在公开清单不自动成为 installed-version support。
_Avoid_: 用 Target 总体状态掩盖字段差异

**Mode**  
用户可见的浅色或深色主题变体。Mode 只描述同一 Seed Color 的呈现变体，不等于 Windows 应用深浅开关；工具保持用户的应用深浅模式（`AppsUseLightTheme`），仅将 Windows 外壳（`SystemUsesLightTheme`）设为深色以原生承载任务栏主题色，并在 Rollback 时恢复。
_Avoid_: 强制切换应用深浅、运行模式

**Mode coherence**

同一 Seed Color 的 Light 与 Dark 变体共享色相、区域层级和主题身份，浅色模式保持通透干净的明亮表面，深色模式保持深邃沉稳的暗色表面。支持双模式的 Target（Windows Terminal、VS Code、TRAE、Antigravity IDE、ChatGPT App、Antigravity 桌面端、MATLAB 桌面端和 Chrome 浏览器）默认自动跟随 Windows 应用模式（`AppsUseLightTheme`）切换 Light/Dark。
_Avoid_: 压暗浅色表面以迁就窄跨度、把 Terminal 默认锁定为单一深色

### Workflow language

**Plan**  
用户在 Preview 阶段确认的 Seed Color、Mode、Target、Appearance policy 和字段能力预期。对于需要发现配置实例的 Target，Plan 还保存已解析且纳入 Hash 的可执行文件、设置文件、扩展目录及版本基线；Apply 与 Verify 必须使用同一组路径。历史 Transaction 的恢复不依赖重新加载 Plan。
_Avoid_: 临时配置、Apply 参数

**Transaction**  
一次 Apply 的持久化操作记录，包含每个 Target 的 Snapshot、Apply、Verify 和 Rollback 信息。  
_Avoid_: 全局状态

**Serialized report value**

Transaction 中用于说明 Target 字段状态、供用户和工具读取的值；它不等同于 Snapshot，也不承担精确恢复原始 Target 状态的职责。
_Avoid_: 把事务报告值当作 Snapshot

Serialized report value 必须能安全写入事务 JSON；二进制值使用不丢失信息的报告表示，但仍不承担 Snapshot 的恢复职责。

**Snapshot**  
修改某个 Target 前保存的原始状态，只能用于该 Transaction 的 Rollback。  
_Avoid_: 通用备份

**Preview**  
只产生 Plan 和检测结果的阶段，不改变 Target。  
_Avoid_: 试应用

**Apply**  
使用已验证 Plan 修改 Target 的阶段。  
_Avoid_: 直接同步

**Verify**  
只读取当前 Target，并按字段和 Visual role 与 Plan 对比的阶段。  
_Avoid_: 再次应用

**Rollback**  
使用明确 Transaction 的 Snapshot 或产物元数据恢复状态的阶段。  
_Avoid_: 撤销所有修改

**Partial**  
至少有一个 Target 或字段完成，同时存在 unsupported、用户操作、失败或未验证项的结果。  
_Avoid_: 大致成功

## Relationships

- Seed Color 生成 Palette。
- Palette 提供 Visual role。
- Target Adapter 把 Color field 映射到 Visual role。
- Git decoration 是 Target 的语义状态 Color field，使用语义文字 role 和实际相邻背景。
- Inline prediction 与 PSReadLine 核心语法配色属于 `terminal` Target 的可选 Shell/PSReadLine 子能力，Profile 位置和能力在 Preview 中发现，运行时按当前 Windows 应用模式（`AppsUseLightTheme`）自动切换浅/深配色，并受同一 Transaction 安全流程约束。
- Native foreground correction 属于终端宿主能力；Configuration match 与 Rendering acceptance 分别记录，SSH 的远端输出由本地宿主渲染。
- Field inventory 定义应核查的 Appearance field，其中 Color field 是颜色与色调子集。
- Plan 保存一次 Preview 的 Target 和 Mode 预期。
- Preview 为需要配置实例发现的 Target 解析唯一 Active Target instance（并对编辑器优先使用 C 盘标准配置目录，同时记录已存在的便携镜像目标）；Apply 与 Verify 不重新猜测路径。
- `MATLAB desktop app` 的 Apply 与 Rollback 经 `Managed process shutdown` 配合 `Live-process write guard` 约束，并在 Rollback 时按字段级精准还原受管设置，保留事务之后新增的无关偏好；Preview 与 Verify 保持严格只读。
- `Chrome desktop browser` 的 Apply 与 Rollback 经 `Managed process shutdown` 配合 `Live-process write guard` 约束，向冻结活跃 Profile 的 `Preferences` 写入基于 `Seed Color` 的 `Seed-driven native theme`（`kTonalSpot` + 系统跟随开关），清理新标签页自定义背景，并在存在 Chrome Sync 时自动执行 `Chrome theme sync isolation`（保留其余同步项、仅隔离主题同步并移除 `browser.theme.saved_local_theme`）；Verify 严格校验受管键与同步隔离状态，Rollback 按字段级精准还原全部受管键及被修改的同步偏好并保留事务之后新增的无关设置；Preview 与 Verify 保持严格只读。
- Transaction 记录一次 Apply 及其后续 Verify 或 Rollback。
