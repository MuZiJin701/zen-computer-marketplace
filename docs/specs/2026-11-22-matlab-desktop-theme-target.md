# Windows MATLAB 桌面主题 Target 开发说明

## Problem Statement

Windows 上的新版 MATLAB（R2025a 及以上 Web 桌面架构）支持原生 `Light` / `Dark` / `System` 主题与按模式独立保存的内容区/语法配色，但目前不在 One-Tone 的受支持 Target 矩阵内。用户在统一 Windows、Terminal、编辑器与其他桌面客户端的主题后，MATLAB 的编辑器、命令行和工作区仍保持默认配色。

同时，MATLAB 的桌面外壳（Toolstrip、顶部标题区、侧边栏）写死在安装包内置的 `themes.json` 中，Windows CLI 的 `-batch` 模式禁止写设置，且运行中的 `MATLAB.exe` 在退出时会用内存配置树覆盖外部对 `matlab.mlsettings` 的修改。因此需要一套严格遵守 One-Tone 只读 Preview/Verify、不改安装包、防运行态覆盖、字段级可回滚契约的独立 Adapter。

## Solution

新增独立 Target `matlab`（加入默认 9 个 Target 列表），面向已验证的 `>= R2025a`（首版实测基线为 `R2026a`）Windows MATLAB 桌面端，直接对用户设置包 `matlab.mlsettings`（OPC ZIP）执行原子读写：

- **Preview**：严格只读，按确定性优先级解析并冻结唯一 `Active Target instance`（Release、设置文件路径、schema 校验结果）并纳入 Plan Hash。
- **Apply**：先执行 `Live-process write guard`；确认无运行中 `MATLAB.exe` 后，先 Snapshot（保存完整 `.mlsettings` 备份 + 受管字段原始存在性与原值），再原子写入 `MATLABTheme = "System"`、双模式 `DesktopColors` / `SyntaxHighlightingColors`（含 `HighlightCurrentLineColor` 与 `LineColor`）及 Light 单键 RGB 同步值，并维护 `metadata/filesystemManifest.xml`。
- **Verify**：严格只读，逐项核对 `matlab.mlsettings` 内的受管字段、JSON 键值、Light RGB 单键与 `filesystemManifest.xml`；因窗口 Chrome 不可修改，校验通过时固定报告 `partial` 与 `rendering_verification = untested`。
- **Rollback**：先执行 `Live-process write guard`（若 MATLAB 运行中直接报 `failed` 阻断）；安全时在当前 `matlab.mlsettings` 上执行**字段级精准还原**（原值写回、原先缺失的键/文件/manifest 条目清除），保留 Apply 之后用户在 MATLAB 中产生的新布局与最近文件历史。

## Implementation Decisions

- **默认 Target 与版本/Schema 边界**：
  - 将 `matlab` 加入默认 Target 列表；未安装、旧版 Java 桌面（`<= R2024b`）、尚未首次启动生成 `matlab.mlsettings`、或 `fsroot/schema.json != "com.mathworks/settings/jsonschema/1-1-0"` / 缺少有效 OPC manifest 的实例均安全 `skipped`。
  - 明确标注为 **verified runtime schema**（`matlab-mlsettings-v1`，实测基线 `R2026a`），不伪称 MathWorks 公开文件格式承诺。
- **实例发现优先级（冻结进 Plan）**：
  1. 显式覆盖：`ONE_TONE_MATLAB_SETTINGS`（直接指向 `matlab.mlsettings`）或 `MATLAB_PREFDIR`（指向含 `matlab.mlsettings` 的目录）；
  2. 注册表 `HKLM\SOFTWARE\MathWorks\MATLAB\*`（读取 `MATLABROOT` 与 `<MATLABROOT>\VersionInfo.xml`）结合 `%APPDATA%\MathWorks\MATLAB\R20*`，按版本号从新到旧选取最新一个 `>= R2025a` 且存在有效 `matlab.mlsettings`（且归档内部声明的 `release` 与目录/注册表版本一致）的实例；
  3. 所有冻结路径规范化为绝对路径；包含 `matlab` 的 Plan 必须携带冻结的 `target_instances["matlab"]`（`load_plan()` 缺失时报错，CLI `build_target_adapters()` 不回退实时发现），运行时同时校验未重定向的绝对路径（拒绝符号链接/目录联接重定向）与目标 `release` 一致性，不凭空伪造新的 `matlab.mlsettings` 文件。
- **受管字段、对比度保底与保留项**：
  - `matlab.appearance.MATLABTheme` → `"System"`。
  - `matlab.colors.DesktopColors`（`light` / `dark` JSON）：`BackgroundColor`（`surface`）、`ForegroundColor`（`foreground`，在 `BackgroundColor` 与 `HighlightCurrentLineColor` 上 `>= 7:1`）。
  - `matlab.colors.SyntaxHighlightingColors`（`light` / `dark` JSON，共 19 项）：`CodeColor`、`NormalColor`、`KeywordColor`、`CommentColor`、`StringColor`、`UnterminatedStringColor`、`SystemCommandColor`、`ValidationSectionColor`、`SyntaxErrorColor`、`ErrorColor`、`WarningColor`、`HyperlinkColor`、`CodeAnalyzerWarningColor`、`CodeAnalyzerInfoColor`、`AutofixHighlightColor`、`VariableHighlightColor`、`VariablesWithSharedScopeColor`、`HighlightCurrentLineColor`、`LineColor`；全部语法/命令行/Code Analyzer 文字色在 `BackgroundColor`、`HighlightCurrentLineColor`、`AutofixHighlightColor` 与 `VariableHighlightColor` 四个背景上均满足 `>= 4.5:1`。
  - Light 单键 RGB（`int32 [1,3]`）同步：`matlab.colors.*`（7 项）、`matlab.colors.commandwindow.*`（3 项）、`matlab.colors.programmingtools.*`（5 项）、`matlab.editor.displaysettings.HighlightCurrentLineColor`、`matlab.editor.displaysettings.linelimit.LineColor`（与 Light JSON 使用同一组经对比度保底的色值）。
  - **单次读取与严格校验**：每次操作单次读取 `matlab.mlsettings` 字节流并在内存中校验与构建；`Apply` 核验当前输入与本事务 `Snapshot` 记录的 `snapshot_sha256` 一致，并在 `os.replace` 前先完成最终进程枚举再复核路径未重定向与磁盘字节一致（杜绝 Snapshot 与 Apply 间及最终枚举期间的并发篡改）。严格校验 ZIP 成员唯一性（拒绝同名重复成员）、`mwcorePropertiesReleaseInfo.xml` 中的 `<release>`（非法或空值直接拒绝，不回退到目录名）、`filesystemManifest.xml`（根标签、子项属性、唯一性与目标文件存在性）及所有已存在的受管 `settings.json` 分组形态（含严格布尔 `hasValue`、`isVector` 标量/向量标志与值编码校验）；损坏档案 fail-closed 拒绝覆盖，对已锁定有效实例事后损坏时 `Verify` 报 `failed`（而非 `skipped`），且强制要求每个受管项 `hasValue = true` 与 `isVector` 匹配。
  - **保留项**：`matlab.appearance.figure.GraphicsTheme`、字体配置、所有功能开关（`HighlightCurrentLine`、`ShowLine`、`HighlightAutofixes`、`AutomaticallyHighlightVariables`、`ShowVariablesWithSharedScope`）以及所有无关设置键。
  - **不支持项**：窗口 Chrome（Toolstrip、顶部 Header、侧边栏、标签页等内置 `themes.json` 令牌），固定 `unsupported`，不修改安装目录。
- **运行态防覆盖守卫（`Live-process write guard`）与幂等回滚语义**：
  - 通过显式 Win32 ctypes 原型的只读进程枚举检测 `MATLAB.exe`（可注入测试）；在入口和临时 ZIP 写完、`os.replace` 前各检查一次（最终枚举结束后再做路径与字节复核），`Process32NextW` 结束必须返回 `ERROR_NO_MORE_FILES`（错误码 `0` 或其他枚举错误均按 **fail-closed** 阻断写入并清理临时文件）。
  - Apply 遇到运行中或状态未知的 MATLAB 返回 `skipped`（`changed = false`，附关闭提示）；Apply 在写入前因校验/并发变更中止时返回 `failed`（`changed = false`，标记 `aborted_before_write = true`）。事务引擎明确区分写入前中止与写入后失败，不对未写入目标触发 `auto_rollback`（防止补偿回滚覆盖并发修改）；Rollback 遇到运行中或状态未知的 MATLAB 返回 `failed`（禁止静默成功）。
  - 多目标事务 Rollback 时，对原事务中从未写入变更的目标（含 `skipped` 与 `aborted_before_write`）以及此前已验证恢复的目标记为 `skipped`（重试回滚不覆盖已恢复目标的后续新偏好；若所有目标均无待回滚改动则报 `FAILED`）；`latest_transaction_id()` 跳过无改动或已全部自动补偿的失败事务，避免阻断 `rollback --latest`。
  - Preview 与 Verify 不受进程运行阻断，保持严格只读。
- **快照路径绑定的子键级 / 字段级 Rollback 与原子写**：
  - 写入时使用同目录临时 `.mlsettings.tmp` + `os.replace` 原子替换。
  - Rollback 以 Snapshot 记录的绝对 `settings_path` 为准（拒绝被符号链接/目录联接重定向后的快照路径，以及传入绑定到不同路径的同版本 Adapter 或元数据冲突，直接报 `failed` 拒绝写入），仅还原 Snapshot 记录的受管键与 `DesktopColors` / `SyntaxHighlightingColors` 内部受管子键（并兼容旧版不含 `kind`/`modes` 的快照升级为子键级还原），保留事务之后新增的无关设置与表内非受管颜色。
- **Appearance policy 升级**：
  - 在 `APPEARANCE_POLICY` 中记录 `matlab` 主题与对比度保底策略并将 revision 升级至 `2026-11-22.v8`，旧 Plan（含 `v7`）需重新 Preview，历史事务 Rollback 保持独立。

## Testing Decisions

- 全程使用 fixture 构造的 OPC ZIP `matlab.mlsettings` 与注入式实例/进程检测后端，**默认测试绝不启动 MATLAB、绝不触碰本机 `%APPDATA%\MathWorks\MATLAB`**。
- 单元测试与集成测试覆盖：
  - 实例发现优先级（显式路径、`MATLAB_PREFDIR`、多版本取最新 `>= R2025a`、旧版 `<= R2024b` 与未初始化/坏包安全 `skipped`）；
  - Preview 只读且生成完整 `field_capabilities` / `field_inventory` / `target_instances`；
  - Apply 写入全部双模式 JSON 与 Light RGB 单键，同步更新 `metadata/filesystemManifest.xml`，保留 `GraphicsTheme`、开关与无关设置，结果报 `partial`；
  - Verify 只读校验（全匹配报 `partial`，篡改任一受管键/manifest 报 `failed`）；
  - `Live-process write guard`（进程运行中 Apply 报 `skipped` 且不改盘、Rollback 报 `failed` 且不改盘）；
  - 字段级 Rollback（精确恢复原值与原缺失键，同时保留 Apply 之后写入的 `RecentFileList` 等无关设置，且 Rollback 后 Verify/回读确认）；
  - CLI 端到端 `preview` / `apply` / `verify` / `rollback`、`uv run pytest`、`one-tone --help` 与 `git diff --check`。

## Out of Scope

- MATLAB R2024b 及更早的旧版 Java Swing 桌面（`matlab.prf`）。
- 修改 MATLAB 安装目录或内置 `toolbox/matlab/ui_themes/resources/themes.json`。
- 修改 `Figure Theme`（`GraphicsTheme`）、绘图色板、字体或编辑器功能开关。
- 自动启动、重启或强制终止 `MATLAB.exe` 进程。
- 生成或调用 `matlab-color-theme-extensions` 的 `.p` 导入脚本。
- 真实 GUI 窗口截图/视觉对比度自动验收（报告 `rendering_verification = untested`）。

## References

- [ADR 0016](../adr/0016-matlab-desktop-mlsettings-target.md)
- [Windows MATLAB 桌面主题支持评估](../matlab-theme-support-evidence.md)
- [CONTEXT.md](../../CONTEXT.md)
