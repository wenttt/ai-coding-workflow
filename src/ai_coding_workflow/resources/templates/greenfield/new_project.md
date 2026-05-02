---
jira_key: "{{ jira_key }}"
mode: greenfield
ticket_type: epic
risk_level: high
proposed_stack:
  language: "{{ e.g. Python 3.12 }}"
  framework: "{{ e.g. FastAPI }}"
  database: "{{ e.g. PostgreSQL }}"
  cache: "{{ e.g. Redis }}"
  deployment: "{{ e.g. Kubernetes }}"
  ci: "{{ e.g. GitHub Actions }}"
ac:
  - "{{ ac_1 }}"
affected_modules: []   # empty for greenfield until first scaffold
sub_tasks:
  - jira_key: "{{ child_1 }}"
    title: "{{ ... }}"
---

# Greenfield Project Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: New Project (greenfield) — building from zero

## Project goal

What problem does this new project solve? Why a new project rather than adding
to an existing one?

## Requirements summary

Pulled from the Jira ticket + linked tickets + comments. Synthesize into:

- Functional requirements:
- Non-functional requirements (NFR): performance, latency, availability, scale
- Constraints: company standards, security policies, existing infra to integrate with

## Tech stack decision

The single most important section in this document. Each row must have rationale.

| Dimension | Recommended | Alternatives considered | Rationale |
|---|---|---|---|
| Language | ... | ... | ... |
| Framework | ... | ... | ... |
| Database | ... | ... | ... |
| Cache | ... | ... | ... |
| Async runtime | ... | ... | ... |
| API style | REST / GraphQL / gRPC | ... | ... |
| Auth | ... | ... | ... |
| Deployment | ... | ... | ... |
| CI/CD | ... | ... | ... |
| Testing | ... | ... | ... |

Mirror the recommended row in the frontmatter `proposed_stack` for downstream stages.

## High-level architecture

ASCII or mermaid. Show the major modules, data flows, external systems.

```
[client] ─→ [api gateway] ─→ [service A] ─→ [DB]
                          ↘  [service B] ─→ [cache]
```

## Module breakdown

| Module | Purpose | Key responsibilities |
|---|---|---|
| `src/api/` | HTTP layer | request validation, auth |
| `src/domain/` | Business logic | core rules, orchestration |
| `src/infra/db/` | Data access | repository pattern, migrations |
| `src/infra/external/` | External integrations | retry, circuit breakers |
| `src/common/` | Cross-cutting | errno, logging, config |
| `tests/` | Tests | unit + integration |

## Project skeleton (for `bootstrap_project` MCP tool)

```
{{ project-name }}/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   └── {{ package }}/
│       ├── __init__.py
│       ├── api/
│       ├── domain/
│       ├── infra/
│       └── common/
├── tests/
└── .github/workflows/
    └── ci.yml
```

## Phasing / sub-task breakdown

Greenfield projects almost always need to be sequenced.

| Phase | Sub-task | Deliverable |
|---|---|---|
| 1 | Skeleton + first endpoint | Smoke test passes |
| 2 | DB layer + first model | Read/write works |
| 3 | Auth | Tokenized requests |
| 4 | Core feature A | First user can use it |
| ... | ... | ... |

## Acceptance criteria (project-level)

What "done" looks like for the whole greenfield Epic.

## Open decisions to defer until later

Things that DON'T need answering right now but should be revisited.
