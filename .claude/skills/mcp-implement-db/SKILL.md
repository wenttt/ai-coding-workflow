---
name: mcp-implement-db
description: Implement database changes for a Jira ticket — schema design, migrations, indexes, queries. Either as primary skill (DB-only ticket) or supplementary alongside backend (when a feature touches schema). Stage 2 (db) of the pipeline.
---

# mcp-implement-db

For database changes — schema, migrations, indexes, queries. Often invoked as a supplementary skill alongside `mcp-implement-backend` when a feature requires schema changes.

## Bash-free contract

MCP tools only — no `psql`, no `mongo`, no migration CLI. The MCP server can run migration scaffolding tools via subprocess if your project uses one (alembic, prisma migrate, etc.); ask via tools rather than running the CLI yourself.

Tools you'll need:
- `read_repo_file`, `list_repo_files`, `find_relevant_modules` — find existing models/migrations
- `write_repo_file` — write migration files + model changes
- `read_operation_logs` — see design and prior stages
- `git_*` — branch, add, commit, push
- `write_operation_log`

## Phases

### Phase 1: Read the design

Pay attention to:
- Frontmatter `affected_modules` — should include DB-related paths (e.g., `src/models/`, `migrations/`)
- Body section on data model — what tables/collections, what fields, what constraints

If the design is silent on schema specifics for a clearly schema-affecting feature, **stop**. Status `failed`, ask user to revise design.

### Phase 2: Survey existing schema

- Look at existing migrations: directory, naming convention, format
- Look at existing models: ORM (SQLAlchemy / Prisma / Mongoose / Drizzle / etc.)
- Look at existing tables: column conventions (uuid vs autoincrement, timestamps, soft deletes)

Match conventions exactly. Schema inconsistency is much costlier than code inconsistency — schema is forever.

### Phase 3: Plan

```
Plan:
- New table: oauth_sessions
  - id: uuid (project standard)
  - user_id: uuid, FK to users.id, ON DELETE CASCADE
  - provider: text NOT NULL
  - access_token: text NOT NULL (encrypted at rest — see project's encryption convention)
  - refresh_token: text NULL
  - expires_at: timestamptz NOT NULL
  - created_at: timestamptz DEFAULT now()
- Indexes:
  - oauth_sessions(user_id) — for lookup
  - oauth_sessions(expires_at) — for cleanup
- Migration: 20260502_001_add_oauth_sessions.py (alembic) or equivalent
- Model: src/models/oauth_session.py
- Rollback path: drop table (no data preservation needed for new feature)
```

### Phase 4: Write the migration first

ALWAYS migration before model changes. The migration is the source of truth for schema; the model is a runtime view of it.

- Match the project's migration framework (alembic / prisma / etc.)
- Include both upgrade AND downgrade paths
- Reference the Jira key in the migration file's docstring
- For data migrations: be careful with assumptions about row count

### Phase 5: Update models

Then update / add the ORM models to match the migration.

### Phase 6: Update affected queries

If existing queries need to JOIN to the new table (or filter by new column), update them in the same commit. The migration + queries should be atomic.

### Phase 7: Self-check

Things to verify before committing:
- Migration is idempotent if re-run? (alembic handles via revision IDs)
- Indexes don't shadow existing ones?
- No `DROP COLUMN` / `DROP TABLE` without data backup mention in the design?
- Foreign key cascade behavior matches what the design implies?
- Locking concerns: large `ALTER TABLE` on hot tables — flag in `what_i_could_not_do` if applicable

### Phase 8: Commit + push

```python
git_create_branch(f"impl/{jira_key}-db", from_ref="main")
git_add([migration_path, model_path, ...])
git_commit(f"db: add oauth_sessions table ({jira_key})")
git_push(...)
```

### Phase 9: Operation log

Schema-specific fields to surface:
- `outputs.migrations_added` — list of migration files
- `outputs.tables_added`, `tables_modified`, `tables_dropped`
- `outputs.indexes_added`
- `engineering_decisions` should cover:
  - Why this index design (and not another)
  - Why this column type (e.g., `text` vs `varchar(255)`)
  - Why these constraints (NOT NULL, FK behavior)
  - Encryption / PII handling decisions
- `what_i_could_not_do` should cover:
  - Production data migration timing (lock implications)
  - Backfill of historical data (if applicable)
  - Read replica lag concerns

### Phase 10: Report

Tell user:
- Branch name
- Migration ID and what it does
- Tables touched
- Anything in "What I could not do" — especially production migration concerns

## Failure modes

- **Design vague on schema** → Stop. Status `failed`. Force a design revision.
- **Migration would lock a hot table for >a few seconds in prod** → Don't proceed; status `failed`. Suggest a phased migration plan in the next step. The DBA / on-call needs to know.
- **Conflicting migrations** (someone else's PR has a same-numbered migration) → Stop. Status `failed`. Ask user to coordinate.

## Honesty principle

Don't write a migration "and we'll figure out the data backfill later." If backfill is needed and you don't know how, that's a `what_i_could_not_do` and a hard stop on shipping until resolved. Schema is the one place where "we'll iterate" can be very expensive.
