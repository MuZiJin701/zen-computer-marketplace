# Field mapping, editor instance, and evidence-report seams

Status: ready-for-agent

## Problem Statement

One-Tone can generate a Target artifact and separately report a Field Evidence Matrix whose Visual roles are inferred from field names. That splits one field's meaning across generated output, inventory heuristics, and tests. The Terminal inline-prediction mapping demonstrates the resulting drift: the artifact uses `prediction_foreground`, while the inventory reports `muted_foreground`.

VS Code and TRAE also spread Active Target instance resolution across command orchestration, Plan serialization and validation, and the editor adapter. Preview, Apply, Verify and Rollback must use one resolved instance, yet their conversion rules are not concentrated at one seam.

Finally, Apply and Verify do not consistently return a complete Field Evidence Matrix. Some adapters assemble reports directly while Verify supplies missing data defensively. Users and callers should receive the same evidence contract when they need to understand a change or its verification.

## Solution

For the first implementation slice, make explicit Target-local field mappings the single source for public VS Code/TRAE and Terminal Color fields. Each mapping records the public field, its Visual role, visual region and evidence metadata, then derives both the generated Target output and the Field Evidence Matrix. This replaces role-name guessing for these Targets without forcing unrelated Targets into a premature shared schema.

Move VS Code/TRAE Active Target instance discovery, Plan conversion, validation and rehydration behind a focused EditorSpec module. Preview saves the resolved editor instance; Apply and Verify replay only that instance. Missing or incomplete persisted paths are safely skipped rather than rediscovered.

Complete Apply and Verify AdapterResult metadata at the transaction seam. Adapters provide their actual field capability status and generated values; the existing inventory reporting module adds the common Field Evidence Matrix and grouped report. Plan format and Plan Hash remain unchanged.

## User Stories

1. As a One-Tone user, I want every reported supported Terminal prediction field to name the Visual role actually written, so that Preview and Verify explain the applied theme accurately.
2. As a VS Code user, I want public editor color fields and their Visual roles to come from one source, so that the generated theme and Field Evidence Matrix cannot drift.
3. As a TRAE user, I want the same field coverage rules as the shared VS Code-family Target, so that supported public fields behave consistently without guessing TRAE-private fields.
4. As a user, I want Preview to bind an editor Target to the exact Active Target instance it found, so that later Apply does not change a different installation or profile.
5. As a user, I want Apply to safely skip an editor Target when its saved instance is unavailable, so that it does not silently choose a new path.
6. As a user, I want Verify to explain each Target with a Field Evidence Matrix, so that I can distinguish supported, applied, verified and unsupported capability status.
7. As a user, I want Apply and Verify to return the same evidence shape, so that automation does not need command-specific parsing rules.
8. As a user, I want Target-specific generated values to remain tied to the Target that produced them, so that evidence does not claim values that were never written.
9. As a user, I want my saved Plan and its hash to remain valid through this implementation change, so that an approved Preview does not need to be recreated solely for an internal refactor.
10. As a maintainer, I want an explicit public field-to-Visual-role mapping, so that adding or correcting a field changes artifact generation and evidence in one place.
11. As a maintainer, I want editor instance discovery priorities to be tested through one interface, so that environment override, launcher, portable, standard and ambiguity rules cannot diverge across workflow stages.
12. As a maintainer, I want a saved editor instance to be rehydrated without consulting new environment values, so that Active Target instance safety is maintained by a direct regression check.
13. As a maintainer, I want transaction output to enrich Apply and Verify results once, so that adapters do not repeat report and group assembly.
14. As a maintainer, I want the Terminal and VS Code-family mappings to remain Target-local where their shapes differ, so that a generic abstraction does not conceal schema differences.
15. As a maintainer, I want actual public field changes to exercise the generated Target artifact and its report together, so that a mismatch fails deterministically without a live desktop.
16. As a maintainer, I want existing Snapshot, Apply, Verify and Rollback safety behavior retained, so that architecture work cannot weaken rollback guarantees.
17. As a user, I want undocumented TRAE-specific UI to remain unsupported, so that One-Tone does not infer compatibility from a similar editor Target.
18. As a user, I want no background process or rediscovery during Apply and Verify, so that a Plan remains a deterministic description of the action I approved.

## Implementation Decisions

- The first slice covers only the VS Code/TRAE and Terminal Targets, the recent change hot spots and the Targets with a confirmed field-role drift. Windows, Chrome and ChatGPT App retain their current implementation.
- Each covered Target owns an explicit mapping for its public Color fields. A mapping entry records the field, Visual role, visual region, text classification where applicable, paired background role, opacity policy and evidence metadata needed by the Field Evidence Matrix.
- Generated VS Code/TRAE colors and Terminal scheme/profile colors derive from their Target-local field mappings. Target-specific calculations remain inside the Target implementation.
- Covered Target inventory entries derive from the explicit mapping. Remove field-name role guessing for those Targets; role guessing must not remain as a fallback for a field covered by a mapping.
- Do not introduce a generic cross-Target mapping base class, protocol or resolver. Retain two Target-local implementations unless direct extraction proves a small shared data shape is natural.
- Add a focused EditorSpec module adjacent to the VS Code-family adapter. It owns editor discovery priority, ambiguity reporting, serialized Plan representation, persisted-instance validation and rehydration.
- Keep the Plan's heterogeneous `target_instances` storage format and its hash inputs unchanged. EditorSpec owns its portion of that format; it does not create a repository-wide Target instance type system.
- Preview persists only its resolved editor instance. Apply and Verify replay that saved instance and skip when it is missing, malformed or unavailable; they do not consult new environment overrides or guess a replacement instance.
- Keep Terminal's PSReadLine discovery and persistence inside the Terminal adapter. ADR-0009 intentionally treats it as a Terminal sub-capability, not an editor instance or a new top-level Target.
- At the transaction seam, enrich Apply and Verify AdapterResult metadata using the existing inventory reporting module. Adapters return field capability status and genuine generated values only; the common report adds the Field Evidence Matrix and visual-region groups.
- Detect, Snapshot and Rollback retain operation-specific metadata and do not manufacture generated values or a full Apply/Verify evidence report.
- Preserve all existing Target, Palette, Plan, Snapshot, transaction, partial-result and rollback semantics. This is a locality refactor with one confirmed drift repair, not a change to user-visible workflow stages.
- Existing ADR-0001, ADR-0003 and ADR-0009 remain authoritative. No new ADR is needed because this work concentrates their existing implementation rules rather than changing a hard-to-reverse product decision.

## Testing Decisions

- Test the highest existing seams: generated VS Code/TRAE and Terminal outputs, saved Plan replay, and transaction-visible Apply/Verify results. Do not test private mapping iteration or helper implementation details.
- Add an output-and-evidence parity regression for every first-slice public field. It must prove that the emitted value uses the mapped Visual role and that the Field Evidence Matrix reports the same role and evidence.
- Include the Terminal inline-prediction regression explicitly: the generated profile output and report must both use `prediction_foreground`.
- Add VS Code-family artifact regressions that prove the same mapping supplies generated colors and the reported Field Evidence Matrix for both VS Code and TRAE.
- Add EditorSpec behavior regressions for environment override, launcher arguments, portable layouts, standard layouts, ambiguous instances and safe skipped resolution. Reuse the existing CLI/editor-instance test patterns.
- Add a Plan replay regression that changes environment inputs after Preview and proves Apply/Verify use only the saved editor instance. A missing or incomplete saved instance must be skipped rather than rediscovered.
- Add transaction contract regressions asserting Apply and Verify provide the same Field Evidence Matrix and groups for equivalent field capabilities, while Detect/Snapshot/Rollback preserve their operation-specific reports.
- Retain existing Plan integrity, Palette, adapter lifecycle, transaction compensation and rollback tests. The refactor must not weaken hash validation, Snapshot-before-mutation, per-Target compensation or status aggregation.
- Run the repository's standard test suite, the Skill CLI help check and `git diff --check` before handoff. Real desktop validation is not required for the refactor but any available Terminal/VS Code/TRAE check may supplement fixture evidence.

## Out of Scope

- Migrating Windows, Chrome or ChatGPT App field generation or inventory into the new mapping approach.
- Changing the Plan schema, Plan Hash inputs, Palette roles, Mode coherence, field capability meanings or transaction storage format.
- Rediscovering editor paths during Apply, Verify or Rollback.
- A repository-wide Target resolver, cross-Target mapping framework, new background process, database or dependency.
- Treating Cursor or undocumented TRAE-specific UI fields as supported.
- Changing Windows system mode, AutoColorization, Chrome activation behavior, PSReadLine key bindings or Terminal's top-level Target model.
- Creating a new ADR or changing domain glossary terminology for this implementation-only concentration.

## Further Notes

- The field mapping module is intended to be deep: callers request generated output or evidence through a small interface while Target schema detail remains local.
- The EditorSpec seam is real because VS Code and TRAE share the same Active Target instance rules. Terminal intentionally remains separate because its persisted shell capability has a different shape.
- Apply and Verify are the evidence-bearing operations. Keeping Detect, Snapshot and Rollback narrower avoids expanding their interface with values that are not meaningful for those operations.
