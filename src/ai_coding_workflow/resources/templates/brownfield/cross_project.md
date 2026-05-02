---
jira_key: "{{ jira_key }}"
mode: brownfield
ticket_type: epic
is_cross_project: true
affected_projects:
  - project_key: "{{ proj_a }}"
    github_repo: "{{ owner }}/{{ repo_a }}"
    role: "backend"
  - project_key: "{{ proj_b }}"
    github_repo: "{{ owner }}/{{ repo_b }}"
    role: "frontend"
implementation_order:
  - "{{ proj_a }}"  # backend first
  - "{{ proj_b }}"  # frontend after
contract:
  type: openapi  # openapi | protobuf | graphql | typescript
  source_of_truth_path: "contracts/{{ jira_key }}.yaml"  # where the contract lives
  api_endpoints:
    - method: POST
      path: /api/v1/{{ resource }}
      request_schema_ref: "#/components/schemas/{{ Resource }}Request"
      response_schema_ref: "#/components/schemas/{{ Resource }}Response"
      error_codes: [400, 401, 404, 500]
ac:
  - "{{ ac_1 }}"
affected_modules: []  # filled per repo by Stage 2
risk_level: medium | high  # cross-project usually >= medium
---

# Cross-Project Design: {{ ticket.summary }}

> Jira: [{{ jira_key }}]({{ ticket.url }})
> Type: Epic — affects multiple repos. Contract-first design.

## Goal

What user-visible capability is being added. State at the level of "user can do X" — both repos serve this single user goal.

## Affected projects + roles

| Project key | Repo | Role | Workspace |
|---|---|---|---|
| {{ proj_a }} | {{ owner }}/{{ repo_a }} | backend | (filled per developer) |
| {{ proj_b }} | {{ owner }}/{{ repo_b }} | frontend | (filled per developer) |

## Implementation order

Backend first → frontend second. Reason:
- Backend defines the contract (endpoints, schemas)
- Frontend consumes the contract (typed client)
- If reversed, frontend is built blind and likely needs rework

If a different order is right for this ticket (e.g., frontend mocks first), justify here:
**Order rationale:** _(default OK or override + reason)_

## Contract (single source of truth — non-negotiable)

This section is the contract. Both implementations MUST conform exactly. If either side wants to deviate, the contract changes here first, then both repos update.

### Endpoints

```yaml
# OpenAPI 3.0 fragment
paths:
  /api/v1/{{ resource }}:
    post:
      summary: <one line>
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/{{ Resource }}Request'
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/{{ Resource }}Response'
        '400': { description: Validation error }
        '401': { description: Unauthorized }
        '500': { description: Server error }

components:
  schemas:
    {{ Resource }}Request:
      type: object
      required: [field_a]
      properties:
        field_a:
          type: string
          example: "..."
        field_b:
          type: integer
          nullable: true
    {{ Resource }}Response:
      type: object
      required: [id, status]
      properties:
        id: { type: string }
        status: { type: string, enum: [pending, completed, failed] }
        created_at: { type: string, format: date-time }
```

### Error codes

| Code | Meaning | Frontend handling |
|---|---|---|
| 400 | Validation failed | Show inline errors per field |
| 401 | Auth expired | Redirect to login |
| 500 | Server error | Show banner, log, retry available |

### Versioning

- Contract changes that break existing consumers → bump path version (`/api/v2/...`).
- Additive changes (new optional fields) → backward-compatible, no version bump needed.

### Where the contract lives in the repo

`{{ contract.source_of_truth_path }}` — both repos reference this file. Backend generates handlers from it; frontend generates client types from it.

## Per-repo implementation outline

### Backend ({{ repo_a }})

- New file(s):
  - `src/api/{{ resource }}.py` — endpoint handler
  - `src/domain/{{ resource }}.py` — business logic
- Modified file(s):
  - `src/router.py` — register new route
- Generated from contract:
  - Request/response Pydantic models from `contracts/{{ jira_key }}.yaml`
- Tests:
  - Unit: handler with mocked domain
  - Contract: live endpoint vs OpenAPI schema validation

### Frontend ({{ repo_b }})

- New file(s):
  - `src/api/{{ resource }}.ts` — typed API client
  - `src/components/{{ Resource }}Form.tsx` — UI
- Modified file(s):
  - `src/routes.ts` — new page route
- Generated from contract:
  - TypeScript types from `contracts/{{ jira_key }}.yaml`
- Tests:
  - Unit: component with mocked API
  - Contract: client builds correct request, parses sample response

## Risk + rollback

- Deploy order: **Backend first**. Frontend deploy after backend is live + smoke-tested.
- Feature flag: gate the frontend usage behind `FEATURE_{{ JIRA_KEY }}_ENABLED` so frontend can ship before user-facing exposure.
- Rollback: disable flag → frontend falls back to legacy path. Backend remains deployed (additive, safe).

## Acceptance criteria

(Mirror in frontmatter `ac`. Stage 4 reads frontmatter to write tests in BOTH repos.)

1. **GIVEN** ... **WHEN** ... **THEN** ...
2. ...

## Cross-project test plan

| Test | Where | Verifies |
|---|---|---|
| Backend unit tests | {{ repo_a }} | Handler logic |
| Backend contract test | {{ repo_a }} | Endpoint conforms to OpenAPI |
| Frontend unit tests | {{ repo_b }} | Component renders + handles states |
| Frontend contract test | {{ repo_b }} | Client builds + parses per OpenAPI |
| **E2E integration** | staging env | Frontend → backend → DB full round-trip |

The E2E integration is the only test that cannot pass with mocks. It must run against deployed (staging) versions of both.

## Open questions

- ...
