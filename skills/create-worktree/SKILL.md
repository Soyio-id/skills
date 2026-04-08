---
name: create-worktree
description: Create an isolated worktree for a new branch, existing branch, or PR review. Prefer repo-local worktree commands when they exist, and fall back to vanilla git worktrees otherwise.
---

# Create Worktree

## Overview

Use this skill when you need one isolated worktree in the current repo.

Good fits:
- start feature work without disturbing the current checkout
- review a pull request in isolation
- open an existing branch in a separate worktree

Default behavior: create only. Do not start the runtime unless the user asks, or unless you ask after creation and the user opts in.

Announce at start: "I'm using the create-worktree skill to set up an isolated worktree for this repo."

## Inputs

Accepted forms:
- `<branch-name>`
- `branch:<branch-name>`
- `pr:<number>`

If the target is missing, ask the user what they want:
1. `New branch`
2. `Existing branch`
3. `PR review`

If the harness offers a structured question tool, use it. Only fall back to plain text questions when the harness question tool is unavailable.

After creation, if the repo has `bin/worktree-up`, ask one follow-up question:
1. `Create only` (Recommended)
2. `Upstart now`

Use the harness question tool for this follow-up when available.

If the repo uses `portless` by default, treat `bin/worktree-up` as responsible for auto-starting the proxy when needed. Do not ask the user to start the proxy manually unless the repo scripts fail and explicitly require intervention.

## Discovery

1. Detect the repo root:

```bash
git rev-parse --show-toplevel
```

2. Detect repo-local helpers in this order:

```bash
ls bin/worktree-add bin/worktree-up bin/worktree-down bin/worktree-rm bin/worktree-env bin/worktree-run 2>/dev/null
```

3. Determine whether to use repo-aware mode or vanilla mode:
- **Repo-aware mode**: `bin/worktree-add` exists
- **Vanilla mode**: `bin/worktree-add` does not exist

## Branch selection rules

### New branch

- Use the requested branch name directly.
- Default start point: `HEAD`.
- If using repo-aware mode:

```bash
bin/worktree-add <branch-name>
```

- If using vanilla mode:

```bash
mkdir -p .worktrees
slug=$(printf '%s' "<branch-name>" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-')
slug=${slug#-}
slug=${slug%-}
git worktree add ".worktrees/${slug}" -b "<branch-name>" HEAD
```

### Existing branch

- If the branch exists locally, use it.
- If the branch is already checked out in another worktree, use `git worktree add --force` so the isolated review/setup still succeeds.
- If it exists only on `origin`, fetch it first:

```bash
git fetch origin "<branch-name>:<branch-name>"
```

- Then create the worktree using the local branch.

### PR review

- Create a local review branch named `review-pr-<number>`.
- Fetch the PR head into that branch:

```bash
git fetch origin "pull/<number>/head:review-pr-<number>"
```

- Then create the worktree for `review-pr-<number>`.

If the fetch fails, report it and stop. Do not guess a fallback branch name.

## Repo-aware mode

When `bin/worktree-add` exists:

1. Use it to create the worktree.
2. If `bin/worktree-env` exists, run it and capture the key env values.
3. If the user chooses `Upstart now` and `bin/worktree-up` exists, run it.
4. If `bin/worktree-rm` exists, mention it in the final output as the cleanup path.

Example commands:

```bash
bin/worktree-add review-pr-215
bin/worktree-env
bin/worktree-up
```

## Vanilla mode

Only use this mode when repo-local helpers are absent.

1. Prefer `.worktrees/` when it exists.
2. If `.worktrees/` does not exist, verify it is ignored before creating it:

```bash
git check-ignore -q .worktrees/
```

3. If `.worktrees/` is not ignored, add it to `.gitignore` and stop to let the user review that repo change separately.
4. Create the worktree with `git worktree add`.
5. Discover and run the smallest documented bootstrap command only if the user chose `Upstart now`.

## Output

Report:
- worktree path
- branch name
- whether the runtime was started
- the preferred cleanup command

Example final output:

```text
Worktree ready at /path/to/repo/.worktrees/review-pr-215
Branch: review-pr-215
Runtime: not started
Cleanup: bin/worktree-rm review-pr-215
```

## Safety rules

- Never create a worktree in the repo root.
- Never reuse an existing worktree path silently.
- Never start the runtime automatically without either an explicit user request or the post-create upstart answer.
- For PR review, prefer `review-pr-<number>` over using the PR head branch name directly.
- If the repo has its own worktree commands, prefer them over raw git commands.

## Soyio workspace note

Inside the Soyio multi-repo workspace, prefer this skill for one repo at a time.
Use `start-parity-workspace` instead when the user needs coordinated `soyio`, `soyio-dashboard`, and `soyio-embeds` worktrees.
