---
name: start-parity-workspace
description: Create or reuse a coordinated Soyio parity workspace across soyio, soyio-dashboard, and privacy-center, then start the matching local runtimes.
---

# Start Parity Workspace

## Overview

Use this skill when local parity matters across `soyio`, `soyio-dashboard`, and `privacy-center`.

Good fits:
- verify auth, redirects, or iframe flows across apps
- spin up matching local origins for a coordinated feature
- open peer repos that should share one `WORKTREE_ID`

Announce at start: "I'm using the start-parity-workspace skill to set up a coordinated Soyio parity workspace."

## Inputs

Preferred input: one workspace id, for example `local-parity-smoke`.

If the workspace id is missing:
- if the current checkout is already a linked worktree and exposes `WORKTREE_ID`, reuse that value
- otherwise ask the user for a workspace id

If the harness offers a structured question tool, use it. Only fall back to plain text questions when the harness question tool is unavailable.

## Repo assumptions

This skill is for the shared Soyio workspace containing:
- `soyio`
- `soyio-dashboard`
- `privacy-center`

Use the same workspace id in all three repos.

## High-level flow

1. Determine the shared workspace id.
2. Inspect whether matching worktrees already exist in each repo.
3. Reuse existing matching worktrees where present.
4. Create missing peers with repo-local `bin/worktree-add` when available.
5. Start the runtimes in the right order.
6. Report the local URLs and cleanup command.

## Detection and reuse

For each repo:

```bash
git -C <repo-root> worktree list --porcelain
```

Look for a linked worktree under `.worktrees/<workspace-id>`.

- If it exists, reuse it.
- If it does not exist and the repo has `bin/worktree-add`, create it:

```bash
bin/worktree-add <workspace-id>
```

- If `bin/worktree-add` is missing, fall back to:

```bash
git check-ignore -q .worktrees/
mkdir -p .worktrees
git fetch origin "$(git remote show origin | awk '/HEAD branch/ {print $NF}')"
git worktree add ".worktrees/<workspace-id>" -b "<workspace-id>" "origin/$(git remote show origin | awk '/HEAD branch/ {print $NF}')"
```

If `.worktrees/` is not ignored, stop and ask the user to add it to `.gitignore` first. Use the repo's default branch as the base for missing peer worktrees unless the user explicitly asks for something else.

## Startup order

Start `soyio` first, then the frontend apps.

### soyio

Run from the linked worktree:

```bash
bin/worktree-up -d
```

If the user does not want `portless`, use `USE_PORTLESS=0 bin/worktree-up -d`. Otherwise rely on the repo helper to auto-start the proxy when needed.

### soyio-dashboard

Run from the linked worktree:

```bash
bin/worktree-up
```

### privacy-center

Run from the linked worktree:

```bash
bin/worktree-up
```

If the user only wants peer worktrees created but not started, do not auto-start them. Ask once before starting if that was not explicit. Use the harness question tool when available.

## Env reporting

After creation or startup, run `bin/worktree-env` in each repo when available and report the key values:
- `soyio`: `APPLICATION_HOST`
- `soyio-dashboard`: `DASHBOARD_APP_ORIGIN`, `VITE_API_URL`
- `privacy-center`: `PRIVACY_CENTER_APP_ORIGIN`, `VITE_API_URL`, `VITE_ACTION_CABLE_URL`

Aggregate those repo-scoped values into one parity summary so the user gets one copy-pasteable set of URLs for the whole workspace.

## Cleanup

For the full parity workspace, prefer the tracked cleanup command from `soyio`:

```bash
bin/workspace-rm <workspace-id>
```

Add `--purge-data` only when the user explicitly wants the linked-worktree Docker volumes removed.

## Safety rules

- Never mix different workspace ids across the three repos.
- Never assume fixed localhost ports; prefer `bin/worktree-env` output.
- Reuse an existing matching worktree instead of creating duplicates.
- Warn clearly if the task only changed `soyio`, or if dashboard/privacy worktrees were intentionally skipped or could not be started, because parity still needs verification in those cases.

## When not to use this skill

- The task only needs one repo in isolation.
- The user is just reviewing one PR or one branch.

In those cases, use `create-worktree` instead.
