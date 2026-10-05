# Architecture

## Marketplace shape

The repository root is the Marketplace. It contains the Marketplace manifest, shared active documentation, the root test harness and one or more Plugin packages.

~~~text
.
├─ .agents/plugins/marketplace.json
├─ plugins/
│  ├─ README.md
│  └─ <plugin-name>/
│     ├─ .codex-plugin/plugin.json
│     ├─ README.md
│     └─ skills/
│        └─ <skill-name>/
│           ├─ SKILL.md
│           ├─ agents/
│           ├─ references/
│           ├─ scripts/
│           └─ runtime project
├─ tests/
│  ├─ README.md
│  ├─ marketplace/
│  └─ plugins/<plugin-name>/skills/<skill-name>/
│     └─ runtime/
├─ docs/
│  ├─ agents/
│  ├─ specs/
│  ├─ adr/
│  ├─ architecture.md
│  └─ testing.md
├─ CONTEXT.md
└─ pyproject.toml
~~~

The Plugin is the installable envelope. The Skill is the independently distributable capability. A Skill runtime belongs inside its Skill package; it must not depend on the Marketplace root or another Plugin.

## Runtime seams

- Plan Palette generation is the highest shared Seam for Seed Color, Mode and Visual role calculation.
- Each Target Adapter is the next Seam for mapping public Color fields to Palette roles and for Detect, Snapshot, Apply, Verify and Rollback.
- Transaction persistence is the safety Seam; it records each Target operation and keeps compensation local to the failed Target.
- Field inventory is the documentation and testing Seam; it defines expected coverage without coupling tests to private implementation helpers.
- Marketplace metadata is the installation Seam; it points to Plugin envelopes but does not contain runtime logic.
- Desktop workflow is the highest seam for `zen-desktop-zero`: it resolves the current user's Resolved desktop, creates a Preview Plan, applies confirmed delete/move operations, verifies the result and keeps a transaction ledger for explicit file-move rollback.
- Toolchain workflow is the highest seam for `zen-scoop-toolchain`: it preflights the fixed Scoop root, detects the Core toolchain baseline, applies confirmed Scoop-first installation with winget fallback and verifies source/path conformity.

Do not add a shared runtime or cross-Plugin import layer until two Plugins genuinely need the same behavior. Reuse repository tooling and documentation conventions, not hidden runtime coupling.

## Responsibilities

- Marketplace manifest: list installable Plugin envelopes.
- Plugin envelope: provide Codex metadata and own its Skills.
- Skill package: provide instructions, references, launcher and runtime for one capability.
- Root test harness: run repository-wide marketplace, Plugin, Skill and runtime tests.
- Palette: generate explicit Light/Dark Visual roles, preserve Mode coherence across one Seed Color, limit corresponding large-area OKLCH lightness difference to `0.35`, and validate text, region contrast and cross-Mode appearance.
- Plan: serialize Seed Color, light/dark Mode Palettes, Target selection and field capability expectations with an integrity hash. `palettes` is the only persisted Palette representation; the selected `mode` is the default lookup mode, not a system-mode switch.
- Storage: validate safe path components and perform atomic persistence.
- Transaction: journal Apply operations with JSON-safe report values, preserve Snapshots and coordinate compensation.
- Target Adapters: map public field inventories to Palette roles, resolve one Active Target instance during Preview, and report field-level capability.
- The Terminal Adapter also owns an optional Shell/PSReadLine sub-capability: Preview discovers the PowerShell 7 `pwsh` Profile and public prediction color fields, while Apply/Verify/Rollback use the Plan-persisted inputs and preserve unrelated Profile content. Default discovery excludes Windows PowerShell; explicit executable overrides must also verify as Core >= 7. Missing PowerShell 7 skips the prediction sub-capability, without changing the user's default Terminal Profile.
- Terminal native foreground correction is discovered from the executable version resource during Preview (including a Scoop shim's resolved executable). Windows Terminal >= 1.16 supports `adjustIndistinguishableColors = always`; unknown/older versions preserve that setting and report partial. Resolved executable, version and capability are persisted in the hashed Terminal instance; Apply/Verify do not probe another host. Defaults, every Profile and existing unfocused appearances share the generated Scheme and correction policy. JSON restoration uses the existing atomic text writer; Profile write failure fails the Target and invokes transaction compensation.
- Explicit Light/Dark Palette `foreground` now enforces 7:1 on `surface`; the legacy omitted-Mode generator retains its existing contract. Terminal black uses `surface`, white/brightWhite use `foreground`, and brightBlack uses `muted_foreground`, protecting primary/white text on black backgrounds and reverse pairs. A single ANSI table cannot satisfy every program-selected pair; native correction is not a guarantee of the acceptance thresholds.
- Configuration matching and rendering acceptance are independent. Terminal and ChatGPT App results carry `rendering_verification = untested`. The App's embedded xterm reads its own CSS color tokens; the verified desktop TOML schema exposes no supported full ANSI/minimum-contrast setting. It remains unsupported without editing application bundles or guessing private fields. Local program configuration is added only after a named/versioned program is reproduced and a supported configuration seam is found.
- Editor instance resolution: discover candidate settings and extension paths read-only, persist the selected paths in the Plan, and make Apply/Verify use that same path set.
- CLI: expose Preview, Apply, Verify and Rollback without bypassing the workflow, and emit recursively JSON-safe machine-readable reports.
- Workstation Plugin runtime: remain self-contained per Skill; use structured `ok`, `partial`, `failed` and `skipped` results, safe path validation and atomic Plan/Transaction persistence without importing another Plugin's runtime.

## Test layout

Tests mirror the distribution hierarchy:

- marketplace tests validate the manifest and cross-package indexes;
- Plugin tests validate the Codex envelope;
- Skill tests validate the distributable Skill package;
- runtime tests live below the matching Plugin and Skill so a future Plugin cannot accidentally reuse another Plugin's fixtures or assumptions.

## Structure audit

### Correct choices

- The Marketplace manifest is separate from Plugin metadata.
- Each Plugin has its own envelope and Skills directory.
- The `zen-one-tone-windows` Plugin owns the complete One-Tone Skill runtime.
- The `zen-desktop-zero` and `zen-scoop-toolchain` Plugins each own one independent workstation Skill and its runtime.
- The root harness is not packaged as a runtime distribution.
- Tests can exercise the Skill source without being shipped with it.

### Costs kept explicit

- The Skill path is deep because the distribution boundary is real.
- The root harness and Skill runtime have separate uv projects; commands must name which project they target.
- Plugin-specific runtime tests are more verbose in exchange for locality and future multi-Plugin isolation.
- Workstation tests use temporary directories and fake desktop, process and installer backends; real deletion, elevation, process termination and package installation remain separate risk boundaries.

### Rules for future Plugins

1. Add one direct child under plugins.
2. Add one local Plugin envelope and README.
3. Put every Skill under that Plugin's skills directory.
4. Keep each Skill runtime self-contained.
5. Add matching tests under tests/plugins/<plugin>/skills/<skill>/.
6. Register only the Plugin envelope in the Marketplace manifest.
7. Do not move shared code into a root runtime until a second real implementation needs it and the seam has been reviewed.
