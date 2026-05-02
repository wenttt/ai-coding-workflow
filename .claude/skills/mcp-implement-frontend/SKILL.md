---
name: mcp-implement-frontend
description: Implement frontend code for a Jira ticket whose design was approved. Reads design + existing components/styles, writes new/modified frontend files matching project conventions. Stage 2 (frontend) of the pipeline.
---

# mcp-implement-frontend

Sister skill of `mcp-implement-backend`, for frontend tickets.

## Bash-free contract

Same MCP tools as backend. No npm, no shell.

## Input contract

Identical shape to `mcp-implement-backend`. The Agent picks this skill (vs backend) based on:
- Jira labels (`frontend`, `ui`)
- Design's `affected_modules` paths (`src/components/`, `src/pages/`, `src/styles/`, etc.)

## Phases

### Phase 1: Read the design + design log

Same as backend.

### Phase 2: Survey the frontend codebase (brownfield)

Read the existing code paying attention to:
- **Framework**: React / Vue / Svelte / Solid — match it
- **Styling**: CSS modules / Tailwind / styled-components / vanilla — match it
- **State management**: Redux / Zustand / Context / Pinia — match it
- **Component pattern**: function vs class, hooks usage, prop typing conventions
- **Test framework**: Jest / Vitest / Testing Library — implies what tests look like
- **Routing**: file-based / config-based — implies where new pages go
- **Design tokens**: colors, spacing, typography defined in a theme — must use them, not magic numbers

### Phase 3: Find a reference component

Don't write a new component from scratch. Find the closest existing component that does something similar (`find_relevant_modules` with the relevant feature keywords) and use it as a structural template. Match its imports, naming, file layout.

### Phase 4: Plan

```
Plan:
- New file: src/pages/Login/OAuthButton.tsx
- Modified: src/pages/Login/index.tsx — wire up OAuth flow
- Untouched: src/components/Button/ — reused as-is, design says no new button variants
- New design tokens needed: NONE — reusing theme.colors.brand.primary
- New deps needed: NONE — using existing oauth-client lib
```

### Phase 5: Write

Style consistency rules:
- New components match the directory layout of similar existing components
- File names follow project convention (`PascalCase.tsx` / `kebab-case.tsx` / etc.)
- Imports follow the existing import order convention
- Prop types defined in the same style as nearby components

### Phase 6: Self-check

`git_diff` and look for:
- Did you add inline styles when the project uses CSS modules?
- Did you hardcode colors instead of using design tokens?
- Did you create a new component when an existing one would have worked?
- Did you import a library not already in the project deps?

### Phase 7: Commit + push

Same as backend. Branch: `impl/{jira_key}-{slug}-fe`.

### Phase 8: Operation log

Same schema as backend. Frontend-specific things to surface:
- Components added / modified
- Whether design tokens were respected
- Accessibility considerations addressed (or skipped, with reason)
- Responsive breakpoints handled
- Localization strings added (if i18n is in use)

`what_i_could_not_do` for frontend often includes:
- Animation polish — basic implementation done, motion/timing left for design refinement
- Loading / error / empty states — base case done, comprehensive state matrix not covered
- Accessibility audit — manual ARIA but not automated test pass

Be honest about these. Stage 4 has a `mcp-quality-audit` companion (uses `audit` skill ideas) that catches some of this.

### Phase 9: Report

Tell user the branch, the components touched, and any design deviations.

## Honesty principle

Frontend has more "is this pixel-perfect?" judgment than backend. If a Figma is referenced in the design and you couldn't access it, say so. Don't approximate based on the design doc's prose alone — flag in `what_i_could_not_do`.
