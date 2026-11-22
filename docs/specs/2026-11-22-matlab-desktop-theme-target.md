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
  2. 注册表 `HKLM\SOFTWARE\MathWorks\MATLAB\*`（读取 `MATLABROOT` 与 `<MATLABROOT>\VersionInfo.xml`）结合 `%APPDATA%\MathWorks\MATLAB\R20*`，按版本号从新到旧选取最新一个 `>= R2025a` 且存在有效 `matlab.mlsettings` 的实例；
  3. 不凭空伪造新的 `matlab.mlsettings` 文件。
- **受管字段与保留项**：
  - `matlab.appearance.MATLABTheme` → `"System"`。
  - `matlab.colors.DesktopColors`（`light` / `dark` JSON）：`BackgroundColor`（`surface`）、`ForegroundColor`（`foreground`，正文 `>= 7:1`）。
  - `matlab.colors.SyntaxHighlightingColors`（`light` / `dark` JSON，共 19 项）：`CodeColor`、`NormalColor`、`KeywordColor`、`CommentColor`、`StringColor`、`UnterminatedStringColor`、`SystemCommandColor`、`ValidationSectionColor`、`SyntaxErrorColor`、`ErrorColor`、`WarningColor`、`HyperlinkColor`、`CodeAnalyzerWarningColor`、`CodeAnalyzerInfoColor`、`AutofixHighlightColor`、`VariableHighlightColor`、`VariablesWithSharedScopeColor`、`HighlightCurrentLineColor`、`LineColor`。
  - Light 单键 RGB（`int32 [1,3]`）同步：`matlab.colors.*`（7 项）、`matlab.colors.commandwindow.*`（3 项）、`matlab.colors.programmingtools.*`（5 项）、`matlab.editor.displaysettings.HighlightCurrentLineColor`、`matlab.editor.displaysettings.linelimit.LineColor`。
  - **保留项**：`matlab.appearance.figure.GraphicsTheme`、字体配置、所有功能开关（`HighlightCurrentLine`、`ShowLine`、`HighlightAutofixes`、`AutomaticallyHighlightVariables`、`ShowVariablesWithSharedScope`）以及所有无关设置键。
  - **不支持项**：窗口 Chrome（Toolstrip、顶部 Header、侧边栏、标签页等内置 `themes.json` 令牌），固定 `unsupported`，不修改安装目录。
- **运行态防覆盖守卫（`Live-process write guard`）**：
  - 通过可注入的进程检测函数检测 `MATLAB.exe`（Windows 下只读进程枚举）。
  - Apply 遇到运行中 `MATLAB.exe` 返回 `skipped`（附关闭提示），不破坏其他 Target；Rollback 遇到运行中 `MATLAB.exe` 返回 `failed`（禁止静默成功）。
  - Preview 与 Verify 不受进程运行阻断，保持严格只读。
- **字段级 Rollback 与原子写**：
  - 写入时使用同目录临时 `.mlsettings.tmp` + `os.replace` 原子替换。
  - Rollback 仅还原 Snapshot 记录的受管键（恢复原值或删除原缺失键；若某个受管 `settings.json` 组原本不存在且还原后已无剩余键，同步移除该文件并恢复 `filesystemManifest.xml` 为原有目录/缺失状态），保留事务之后新增的无关设置。
- **Appearance policy 升级**：
  - 在 `APPEARANCE_POLICY` 中记录 `matlab` 策略并升级 revision，旧 Plan 需重新 Preview，历史事务 Rollback 保持独立。

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
