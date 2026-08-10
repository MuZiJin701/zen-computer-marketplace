# ChatGPT App 主题 Target 迁移开发说明

## Problem Statement

用户希望通过 One-Tone 统一 ChatGPT Windows/macOS 桌面 App 的界面主题，但当前实现把该目标命名为 `codex`，容易与 Codex CLI/TUI 混淆。用户明确只讨论 ChatGPT App；CLI 主题已经由 Windows Terminal 配置处理，不纳入本需求。

当前 ChatGPT App 仍可从用户的 `config.toml` 读取桌面主题配置，但公开配置文档主要描述 Codex CLI 的 `tui.theme` 语法高亮主题，没有把桌面 App 的外观字段作为稳定公开配置契约。因此实现必须以当前已验证的 App 运行时 schema 为边界，并在 schema 不匹配时安全失败。

此外，已有 Plan 以 `codex` 作为 Target 名称。该名称与新语义不兼容，不能通过兼容层继续解释或自动迁移。

## Solution

将用户可见的 Target 从 `codex` 重命名为 `chatgpt-app`，明确它只表示 ChatGPT 桌面 App。保留现有 Preview → Apply → Verify → Rollback 流程和 `config.toml` 原子写入路径：Preview 生成包含 ChatGPT App 的 Plan，Apply 由 ChatGPT App Adapter 更新已验证的浅色/深色主题表，Verify 对比当前配置，Rollback 仅恢复该 Transaction 的快照。

旧 Target 名称 `codex` 的 Plan 不做兼容和迁移，加载时拒绝。清理范围仅限 Skill runtime 的 `plans/*.json`；不删除 `transactions/`、快照、`config.toml` 或其他用户文件。

## User Stories

1. As a ChatGPT App user, I want the supported target to be named `chatgpt-app`, so that it is clear the target is the desktop App rather than Codex CLI.
2. As a ChatGPT App user, I want CLI/TUI theme configuration excluded, so that applying the desktop theme does not unexpectedly alter my terminal workflow.
3. As a ChatGPT App user, I want Windows Terminal configuration excluded from this target, so that its already-configured theme remains the source of truth for terminal presentation.
4. As a user running Preview, I want `chatgpt-app` to appear in the target inventory, so that I can select the desktop App explicitly.
5. As a user running Preview without explicit targets, I want the default target set to use `chatgpt-app`, so that the App is included without relying on the obsolete name.
6. As a user running Preview, I want the generated Plan to identify the ChatGPT App target, so that the Plan is understandable before Apply.
7. As a user running Apply, I want the existing Plan hash and target validation to remain enforced, so that an altered or unintended Plan cannot modify the App configuration.
8. As a user running Apply, I want the ChatGPT App Adapter to update `config.toml` atomically, so that an interrupted write cannot leave a truncated configuration file.
9. As a user running Apply, I want unknown configuration keys preserved, so that unrelated ChatGPT App settings survive a theme change.
10. As a user running Apply, I want both Light and Dark theme tables updated together, so that switching the App appearance does not reveal a stale half-applied palette.
11. As a user running Apply, I want the current appearance mode and unrelated appearance preferences preserved, so that theme application does not force light or dark mode.
12. As a user whose installed App schema differs from the verified schema, I want the operation to fail closed or report `skipped`, so that unsupported fields are never guessed or written.
13. As a user running Verify, I want verification to compare the current App configuration with the Plan without changing files, so that verification is safe to repeat.
14. As a user running Rollback, I want only the selected Transaction's snapshot restored, so that unrelated transactions and settings remain untouched.
15. As a user with old Plans, I want Plans using `codex` to be rejected explicitly, so that an incompatible Plan cannot silently target the wrong application.
16. As a maintainer, I want the adapter's external Target and schema identity separated from the legacy module name, so that internal reuse does not preserve an incorrect user-facing contract.
17. As a maintainer, I want inventory metadata and field capability status to describe ChatGPT App, so that reports and documentation agree with the actual target.
18. As a maintainer, I want tests at the existing Plan-to-Adapter-to-configuration seam, so that the end-to-end contract is protected without UI automation.
19. As a maintainer, I want old runtime Plan files removed only from the Skill-local `plans` directory, so that cleanup cannot erase transaction history or user configuration.
20. As a maintainer, I want the documentation to distinguish ChatGPT App from Codex CLI, so that future changes do not reintroduce the naming ambiguity.
21. As a user, I want the feature to remain reversible, so that I can recover the previous ChatGPT App theme if the result is undesirable.
22. As a user, I want partial or failed target results reported according to the existing transaction rules, so that I can tell whether the App change actually completed.

## Implementation Decisions

- The canonical user-facing Target is `chatgpt-app`; `codex` is not an alias.
- The existing target registry, Plan validation, transaction flow, and adapter result contract remain the integration seam. No new orchestration layer is introduced.
- The ChatGPT App Adapter continues to read and atomically rewrite the user `config.toml` file, preserving unknown TOML keys and unrelated desktop settings.
- The adapter writes only the already verified ChatGPT App v1 theme fields: Light/Dark surface, ink, accent, contrast, and semantic color roles. It does not infer undocumented fields.
- Light and Dark tables use the same Seed-derived Tonal surface family and preserve mode coherence. Accent is used for emphasis backgrounds and borders, not as dense text.
- The adapter must keep the user's `appearanceTheme` and must not alter system light/dark mode, auto-colorization, or high-contrast settings.
- The AdapterResult runtime schema identity is renamed from the legacy Codex configuration schema identity to a ChatGPT App configuration schema identity. Plans do not carry this AdapterResult version; legacy Plans are rejected by their `codex` Target.
- Plan loading rejects a legacy `codex` Target with an explicit integrity error. No automatic Plan migration is added.
- Runtime cleanup, if files exist, is limited to explicit JSON files under the Skill-local `plans` directory. Transaction records, snapshots, configuration files, and files outside that directory are preserved.
- CLI/TUI theme settings and Windows Terminal theme settings are explicitly out of this Adapter's responsibility.
- Documentation uses “ChatGPT desktop app” for the product and “ChatGPT App” for the Target; “Codex CLI/TUI” is reserved for the excluded terminal product.
- The implementation does not depend on a public UI import/export API. A future API-based integration would require a separate specification.

## Testing Decisions

- Tests verify external behavior at the highest existing seam: target selection and inventory, Plan serialization and validation, Adapter preview/apply, atomic configuration preservation, Verify, and transaction behavior.
- Tests must assert that `chatgpt-app` is accepted and `codex` is rejected as a legacy Target.
- Adapter tests must cover both Light and Dark tables, all verified v1 color fields, preservation of unknown keys, preservation of appearance mode, and the expected structured result.
- Transaction tests must cover snapshot-before-write, successful rollback, failed or skipped target reporting, and configuration restoration.
- Cleanup tests, when runtime fixtures are present, must prove that only Skill-local `plans/*.json` files are removed and that transactions and configuration remain.
- No browser, Electron, or desktop UI automation is required for this change; the configuration seam is the acceptance boundary.
- Existing project validation remains authoritative: the full pytest suite, the Skill CLI help command, and `git diff --check`.

## Out of Scope

- Codex CLI/TUI appearance or syntax-highlighting themes.
- Windows Terminal theme configuration.
- ChatGPT web or mobile theme settings.
- UI automation, App restart automation, or automatic activation of a generated theme.
- Reverse engineering or guaranteeing undocumented ChatGPT App fields beyond the verified runtime schema.
- Import/export integration through a future `codex-theme-v1` or other UI-facing format.
- Automatic migration of old Plans, Transactions, snapshots, or user configuration.
- Deleting transaction history, snapshots, or any file outside the Skill-local `plans` directory.
- Changing the user's light/dark mode, auto-colorization, high-contrast setting, or system accent behavior.

## Further Notes

The official migration guidance describes the current Codex desktop experience as part of the ChatGPT desktop app, which is why the product-facing Target is renamed. The public Codex configuration reference documents `tui.theme` as syntax highlighting and does not establish the desktop appearance fields as a public contract. The current installed App runtime has a verified schema for the fields handled here; runtime verification remains the authority for whether Apply may proceed.

References:

- [OpenAI Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Help Center: Codex app update](https://help.openai.com/en/articles/20001276/)
- [OpenAI Codex configuration schema](https://learn.chatgpt.com/docs/config-schema.json)
