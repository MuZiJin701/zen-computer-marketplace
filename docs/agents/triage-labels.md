# Triage Labels

Use these canonical triage state roles and GitHub label strings:

| Role | GitHub label | Meaning |
| --- | --- | --- |
| needs-triage | needs-triage | Maintainer needs to evaluate the issue |
| needs-info | needs-info | Waiting on the reporter for more information |
| ready-for-agent | ready-for-agent | Fully specified and ready for an agent |
| ready-for-human | ready-for-human | Requires human implementation |
| wontfix | wontfix | Will not be actioned |

When a skill mentions a triage role, use the corresponding label string from this table.

Category roles use the existing bug and enhancement labels. Each triaged issue carries exactly one category role and one state role; other labels may remain.

When changing state, remove the previous state label and add the selected state label, preserving category and unrelated labels. If an issue already has conflicting state roles, report the conflict and ask the maintainer before updating it.
