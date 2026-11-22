# Architecture Decision Records

Store durable architecture decisions here as numbered Markdown files, for example 0001-skill-runtime-boundary.md.

Create an ADR when a decision changes a module seam, persistence contract, target support boundary, or distributable package structure. Keep ordinary implementation notes in the relevant architecture or testing document instead.

Each ADR should record:

1. Context
2. Decision
3. Consequences
4. Status

Historical design and implementation notes are not automatically ADRs; promote only durable architectural decisions into this directory.

The accepted decisions about field coverage, the canonical Plan Palette set, user-facing theme coherence, system-mode following, workstation Plugin boundaries and evidence-backed Light text readability are recorded in 0001-theme-field-coverage-and-separation.md, 0002-plan-palette-single-source.md, 0003-user-facing-theme-coherence.md, 0006-mode-coherence-and-system-following.md, 0007-workstation-plugin-boundaries.md and 0008-light-text-evidence-and-readability.md.

[ADR 0010](0010-evidence-backed-appearance-policy.md) records pinned public/registered field intersections, hashed appearance-policy upgrades and independent historical Rollback. It implements the explicit system-following/solid appearance spec without rewriting earlier decision records.

[ADR 0012](0012-single-plugin-package-layout.md) records the single-plugin source layout and the boundary of the installable package.

[ADR 0013](0013-cross-agent-plugin-distribution.md) records the supported distribution channels and shared Skill package.

[ADR 0014](0014-windows-desktop-wallpaper-mode-matching-and-palette-refinement.md) records `IDesktopWallpaper` multi-monitor sync/verification, effective Windows mode matching without a daemon, OKLCH palette hierarchy/ANSI refinement, and the Terminal Light theme fix.

[ADR 0015](0015-windows-custom-mode-taskbar-zen-palette-and-adaptive-terminal.md) records Windows Custom Mode (`SystemUsesLightTheme = 0`, preserving `AppsUseLightTheme`) for native taskbar accent display, app-mode wallpaper matching, real 8-slot RGB0 `AccentPalette` with `>= 3:1` icon contrast, Zen palette layering/border refinement, system-following Windows Terminal with adaptive PSReadLine syntax colors, and cross-target reliability fixes.

[ADR 0016](0016-matlab-desktop-mlsettings-target.md) records adding the Windows MATLAB desktop (`matlab`, `>= R2025a`, baselined on `R2026a`) Target via offline atomic `matlab.mlsettings` updates, `Live-process write guard`, field-level Rollback, honest `partial` reporting (no installation bundle modification), and preserving `GraphicsTheme` and feature toggles.
