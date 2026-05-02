---
jira_key: "{{ jira_key }}"
mode: brownfield
ticket_type: sub_task
parent_jira_key: "{{ parent_key }}"
ac:
  - "{{ ac_1 }}"
affected_modules:
  - "{{ module_1 }}"
risk_level: low | medium | high
---

# Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }}) (sub-task of [{{ parent_key }}](...))
> Type: Sub-task (brownfield)

## Scope

This sub-task is one slice of the parent. Make scope explicit so the implementation
doesn't drift.

- In scope:
- Out of scope (handled by other sub-tasks):

## Inherited context from parent design

Reference the parent's design doc. Don't re-derive things already decided there.
- Parent design: `docs/designs/{{ parent_key }}.md`
- Decisions inherited: ...

## Implementation outline

## Acceptance criteria (mirror in frontmatter `ac`)

## Affected modules (mirror in frontmatter)

## Open questions
