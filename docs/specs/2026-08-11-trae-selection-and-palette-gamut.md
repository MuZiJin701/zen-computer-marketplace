# TRAE selection readability and Palette gamut preservation

Status: ready-for-agent

## Problem Statement

When a Markdown Preview takes keyboard focus in TRAE, the Explorer becomes an inactive tree. The generated Light theme supplies `list.inactiveSelectionForeground` but not its paired background. TRAE therefore falls back to its own pale inactive-selection background, while retaining One-Tone's light selection text. The selected filename in the supplied report is only about `1.06:1`, so it is effectively unreadable. The same incomplete pairing exists for the list focus state.

The report that a green theme looks blue is partly perceptual and partly an unhandled palette edge case. For Seed Color `#10B981`, the generated Tonal surfaces retain the Seed hue (about 162 degrees) but deliberately reduce chroma to a muted green-grey; the source color itself is an emerald/teal green, not a yellow-green. Near-neutral text roles also lean cool by design so Dense primary text remains readable. Those choices are consistent with the existing Appearance-safe Palette decision.

There is nevertheless a shared Palette defect for some bright yellow/orange Seeds: direct sRGB channel clipping can shift a Light Accent far enough from the Seed hue for Plan validation to reject the Palette. This means the tool does not silently apply an incorrect palette, but valid user colors remain unusable.

## Solution

Complete the public VS Code list/tree state pairs used by TRAE and VS Code. Inactive selected items and focused items must use the existing `selection_background` together with the existing `selection_foreground`; their contrast is assessed as a pair, rather than against a host fallback color. Add the fields to the Field inventory so generated artifacts and Verify use the same supported coverage.

Preserve the current Palette semantics: Tonal surfaces and Accent stay in the Seed Color's hue family; Dense primary text remains neutral and readability-first. Do not retune green surfaces simply because `#10B981` is visually cool after chroma reduction.

Replace out-of-gamut sRGB channel clipping in Palette conversion with deterministic gamut mapping that reduces chroma only as needed while retaining the requested OKLCH hue and lightness as closely as the target gamut permits. A valid high-chroma Seed must generate a coherent Plan rather than fail only because a Light Accent was clipped into another hue family.

## User Stories

1. As a TRAE user, I want a selected Explorer item to remain readable after a Markdown Preview receives focus, so that I can identify the selected file.
2. As a VS Code user, I want inactive selected list/tree items to have an explicit foreground/background pair, so that host fallback colors cannot invalidate the theme.
3. As an editor user, I want focused list items to have their own explicit background pairing, so that keyboard navigation stays readable.
4. As a user, I want the normal, active, inactive and focused selection states to remain visually coherent, so that changing focus does not change a filename from legible to washed out.
5. As a user, I want the Seed Color's Tonal surfaces to retain its hue family, so that a unified theme remains recognizably based on my chosen color.
6. As a user choosing `#10B981`, I want a muted emerald surface rather than an unexplained arbitrary blue shift, so that low-chroma surfaces remain predictable.
7. As a user, I want neutral reading text to remain high contrast even when my Seed Color is saturated, so that long Markdown and code sessions remain comfortable to read.
8. As a user choosing a bright yellow or orange Seed, I want a usable Palette and Plan, so that gamut limits do not make part of the color range unavailable.
9. As a user, I want Accent, border and selection colors to remain in my Seed's hue family after conversion to displayable RGB, so that emphasis colors do not become another color.
10. As a maintainer, I want the Field inventory to include every supported list/tree field, so that generated themes and verification reports cannot disagree on coverage.
11. As a maintainer, I want selection-state tests to exercise the generated theme artifact, so that a missing field fails without requiring a live TRAE installation.
12. As a maintainer, I want palette tests to cover a full hue sweep and a known warm-color regression, so that a green-only fix cannot leave yellow/orange Seeds unusable.
13. As a maintainer, I want the existing Preview, Apply, Verify and Rollback contracts unchanged, so that readability and color fixes do not weaken theme safety.
14. As a user, I want TRAE-specific private UI to remain unsupported unless it can be discovered and verified, so that One-Tone does not guess undocumented fields.

## Implementation Decisions

- Use only public VS Code list/tree colors for this repair. Map inactive selection and focus backgrounds to the existing `selection_background`; keep their foregrounds paired with `selection_foreground`.
- Extend the existing Field inventory with the same public state backgrounds. Do not create a second field registry or a TRAE-only exception.
- Keep the current `selection_background`/`selection_foreground` Palette roles. The defect is an Adapter mapping and inventory omission, not a need for more palette roles.
- Keep low-chroma Tonal surfaces and neutral Dense primary text. Seed identity belongs in Tonal surfaces, Accent, borders, selections and semantic emphasis, while ordinary reading text remains readability-first.
- Gamut-map each requested OKLCH color into sRGB by finding the highest in-gamut chroma at the requested hue and lightness. Do not independently clamp red, green or blue channels, and do not add a color-library dependency.
- Apply gamut mapping at the shared Palette conversion seam so all generated color roles use the same behavior. The Adapter must not repair individual warm colors.
- Preserve the existing contrast, separation, mode-coherence and safe Plan validation rules. The warm-color change makes eligible colors satisfy those rules; it does not relax their thresholds.
- Keep all undocumented TRAE AI-panel fields and list icon variants out of scope unless installed-version evidence establishes support and behavior.
- The decisions refine the existing Appearance-safe Palette and Light-text readability ADRs; no new Palette role or new ADR is required.

## Testing Decisions

- Test the highest existing seams: generated Palette/Plan data and the generated VS Code-family theme artifact. Do not unit-test private color-search iteration or internal channel math.
- Add an artifact regression that asserts active, inactive and focus list/tree foreground/background pairs are present and that each generated pair meets the existing selection-text contrast target.
- Verify the Field inventory reports the two added public fields for the VS Code-family coverage used by TRAE.
- Retain existing normal sidebar text contrast checks to prove this change does not replace the sidebar's Dense primary text mapping.
- Add Palette regressions across evenly distributed saturated hue Seeds in both Modes. Large-area Tonal roles and Accent must stay within the existing hue-family tolerance after conversion.
- Add a bright yellow/orange regression that previously failed due to sRGB clipping; it must now create a valid coherent Plan while preserving contrast and region-separation checks.
- Reuse the repository's existing Palette, Plan and VS Code-family artifact test patterns. Add no browser automation, image-comparison framework, dependency or service.
- After fixtures pass, manually validate TRAE Light mode with a Markdown Preview focused: normal Explorer labels, inactive selected item and focused item must be readable. Capture this as a real-target acceptance check, not as a replacement for deterministic tests.
- Implementation verification runs the repository's standard test suite, the Skill CLI help check and `git diff --check`.

## Out of Scope

- Retuning the overall surface saturation or redefining `#10B981` as a warmer green.
- Forcing neutral primary text, links or semantic token text to take the Seed hue.
- TRAE private AI-panel colors, unverified icon variants and Markdown Preview webview styling.
- Changing Windows mode, automatic colorization, target discovery, Plan hashes, transactions, Snapshot behavior, Apply, Verify or Rollback semantics.
- Copying concrete colors from a built-in or third-party theme.
- Adding a color-management dependency, background process, new Palette role or a separate field-evidence registry.

## Further Notes

- The inactive-selection report is a pair mismatch: generated text was rendered over a TRAE fallback background. It is independent of the Palette's green hue behavior.
- `#10B981` generated Light surfaces are approximately 162 degrees in OKLCH, matching the Seed's approximately 162.5 degrees. Its cool appearance comes from intentional chroma reduction, not a measured blue hue drift.
- Bright warm colors expose a real shared conversion limitation. Correcting it at the Palette seam benefits every Target and avoids per-Adapter compensation.
- The real-target acceptance gate follows the existing distinction between deterministic fixture validation and visual rendering evidence.
