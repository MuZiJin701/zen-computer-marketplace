# ADR 0013: Distribute one One-Tone Skill across Agent hosts

## Status

Accepted (2026-11-18).

## Context

[ADR 0012](0012-single-plugin-package-layout.md) defines a single Plugin and independently installable Skill. One-Tone is distributed across Agent hosts with different native installation formats.

## Decision

Recommend the `skills` CLI for standalone Skill installation. Maintain native CLI plugin installation entry points for Codex, Claude Code, Antigravity, Grok Build and GitHub Copilot CLI. Share one repository-level Marketplace index at `.claude-plugin/marketplace.json` pointing to `./plugin` for Claude Code, Codex, Grok Build and Copilot CLI, while Antigravity installs `./plugin` directly from the repository URL. Inside `plugin/`, Codex, Antigravity, Grok Build and Copilot CLI share the Agent Plugins 1.0 manifest (`plugin/plugin.json`, with Codex presentation metadata under `extensions.com.openai`), and Claude Code uses `plugin/.claude-plugin/plugin.json`. All distribution channels deliver the one Skill and runtime in `plugin/skills/zen-one-tone-windows/`. Preserve explicit-only Skill invocation and the existing Codex installation identifiers.

## Consequences

Repository documentation and tests stay outside the Plugin. The test suite checks the Marketplace index and package manifests. Local client installation checks cover Codex, Claude Code and Antigravity. The maintainer can verify Grok Build and Copilot CLI on the intended client versions. Host support describes distribution and invocation. The Target matrix defines theme integration support.
