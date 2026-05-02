---
jira_key: "{{ jira_key }}"
mode: brownfield
ticket_type: epic
ac:
  - "{{ ac_1 }}"
affected_modules:
  - "{{ module_1 }}"
risk_level: medium | high
sub_tasks:
  - jira_key: "{{ child_1 }}"
    title: "{{ ... }}"
---

# Epic Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: Epic (brownfield) — adding a substantial feature to an existing system

## Goal

What does this Epic accomplish? Business or technical outcome at the system level.

## Current architecture (relevant portions)

Diagram or prose covering only the parts touched by this Epic.

## Proposed architectural change

What changes shape vs. what fits within the existing shape.

## Sub-task breakdown

Each sub-task should be small enough to be a single PR.

| Order | Jira key | Title | Affected modules |
|---|---|---|---|
| 1 | ... | ... | ... |
| 2 | ... | ... | ... |

Mirror in frontmatter `sub_tasks` so downstream automation can sequence.

## Acceptance criteria (Epic-level)

Higher-level than per-sub-task. What success looks like across the whole Epic.

## Cross-cutting concerns

- Migrations / data backfills:
- Feature flags:
- Telemetry / observability:
- Security review:
- Performance impact:

## Risk + phasing

How the Epic rolls out. Which sub-task can ship independently. What flag gates it.

## Open questions
