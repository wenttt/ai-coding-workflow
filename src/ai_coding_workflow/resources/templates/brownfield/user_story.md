---
jira_key: "{{ jira_key }}"
mode: brownfield
ticket_type: user_story
ac:
  - "{{ ac_1 }}"
  - "{{ ac_2 }}"
affected_modules:
  - "{{ module_1 }}"
risk_level: low | medium | high
---

# Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: User Story (brownfield)

## Story

**As a** {{ user_persona }}
**I want** {{ capability }}
**So that** {{ value }}

## Background / Current state

What does this part of the system do today? Reference specific files / modules.
Pull from `find_relevant_modules` results.

## Acceptance criteria

In `GIVEN / WHEN / THEN` form. The frontmatter `ac` array MUST mirror this list
in plain text — Stage 4 (`mcp-test-write`) reads from frontmatter to generate
test cases.

1. **GIVEN** {{ precondition }}
   **WHEN** {{ action }}
   **THEN** {{ outcome }}

2. ...

## Implementation outline

How this fits into the existing architecture. Files to add, files to modify,
key abstractions to reuse.

- New file(s):
  - `src/.../foo.py` — purpose
- Modified file(s):
  - `src/.../bar.py` — change
- Reused patterns:
  - `src/common/retry.py` decorator
  - existing `errno` table conventions

## Affected modules (machine-readable: see frontmatter)

List paths the implementation will touch. Update `affected_modules` in the
frontmatter to match — Stage 3 self-review compares the actual diff against
this list.

## Edge cases & non-goals

- Edge cases handled: ...
- Explicit non-goals: ...

## Testing strategy

What tests will Stage 4 write? Unit / integration / E2E balance.

## Open questions

Anything Stage 1 cannot decide alone — call out for the reviewer.
