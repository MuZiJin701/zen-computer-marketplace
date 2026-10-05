# Domain docs

This is a single-context repository. The root CONTEXT.md is the canonical domain glossary, serving the role called GLOSSARY.md by the engineering skills.

## Before exploring

1. Read the root CONTEXT.md.
2. Read relevant files in docs/adr/.
3. Read the relevant development specification in docs/specs/ when working on a request.
4. Read docs/architecture.md or docs/testing.md when the task changes runtime boundaries or verification.

Use the terms defined in CONTEXT.md for issue titles, plans, hypotheses, tests and implementation discussion. If a needed term is missing or ambiguous, record the ambiguity for domain-modeling before inventing a synonym.

## Writing domain docs

- Update resolved domain terms in CONTEXT.md, including when using domain-modeling or grill-with-docs. Use this existing glossary instead of creating a second GLOSSARY.md.
- Keep terms and relationships in the glossary. Keep feature decisions and acceptance criteria in docs/specs/, module seams in docs/architecture.md, and verification contracts in docs/testing.md.
- Record durable architectural decisions in numbered docs/adr/ files following docs/adr/README.md. Ordinary implementation changes do not need placeholder ADRs.
- If a proposal contradicts an accepted ADR, name the conflict and the reason for reconsidering it instead of silently overriding the decision.

## Layout

~~~text
CONTEXT.md                 # canonical domain glossary
docs/
  agents/                  # engineering-skill configuration
  adr/                     # architecture decision records
  specs/                   # development specifications
  architecture.md          # implementation boundaries
  testing.md               # verification contract
~~~

The current package boundary is intentional: each Skill owns its distributable runtime and the root project owns the test harness. Do not move runtime code merely to shorten the path.
