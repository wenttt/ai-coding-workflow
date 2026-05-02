---
jira_key: "{{ jira_key }}"
mode: brownfield
ticket_type: task
ac:
  - "{{ ac_1 }}"
affected_modules:
  - "{{ module_1 }}"
risk_level: low | medium | high
---

# Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: Task (brownfield)

## What

Concrete one-paragraph description of what this task changes. No story framing.

## Why

Business or technical motivation. If a bug, link the incident / repro.

## Current state

What the code does today. Specific file:line references.

## Proposed change

Diff-level outline (without writing the actual code yet):
- File X: do A
- File Y: do B

## Acceptance criteria (mirror in frontmatter `ac`)

1. ...

## Affected modules (mirror in frontmatter)

- `path/to/module/`

## Risk + rollback

What's the blast radius if this goes wrong?
What's the rollback plan?

## Testing strategy

## Open questions
