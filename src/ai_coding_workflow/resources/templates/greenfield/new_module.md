---
jira_key: "{{ jira_key }}"
mode: greenfield
ticket_type: task
risk_level: medium
proposed_stack:
  language_in_repo: "{{ e.g. matches existing }}"
  framework_in_repo: "{{ matches existing }}"
ac:
  - "{{ ac_1 }}"
affected_modules:
  - "{{ new_module_path }}"
---

# Greenfield Module Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: New Module within an existing monorepo (partial-greenfield)

## Why a new module (not extending existing code)

Greenfield within a brownfield repo is a meaningful design choice. State the case:
- Bounded context: this module owns ___ which doesn't fit cleanly into existing modules
- Coupling control: keeping it separate prevents ___
- Tech reason: needs different runtime / different deps / different lifecycle than the rest

If the case is weak, this should probably be a brownfield extension, not a new module.

## Module placement

```
existing-repo/
├── existing-module-a/
├── existing-module-b/
└── {{ new-module }}/   ← this design
    ├── ...
```

## Module structure

```
{{ new-module }}/
├── README.md
├── src/
│   └── ...
├── tests/
└── ...
```

## Boundaries / interfaces

What's the public surface of this module? How do other modules call it? Sync /
async / events?

- Inbound: ...
- Outbound: ...
- Shared types: ...

## Acceptance criteria (mirror in frontmatter `ac`)

## Risks

- Coupling pull: which existing modules will be tempted to bypass the boundary?
- Test isolation: can this module be tested without the rest of the monorepo running?

## Open questions
