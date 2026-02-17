---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification
---

# Using Git Worktrees

## Overview

Git worktrees create isolated workspaces sharing the same repository, allowing work on multiple branches simultaneously without switching.

Core principle: systematic directory selection plus safety verification equals reliable isolation.

Announce at start: "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Directory selection process

Follow this priority order.

### 1) Check existing directories

```bash
ls -d .worktrees 2>/dev/null
ls -d worktrees 2>/dev/null
```

If found, use that directory. If both exist, `.worktrees` wins.

### 2) Check AGENTS.md

```bash
grep -i "worktree.*director" AGENTS.md 2>/dev/null
```

If preference is specified, use it without asking.

### 3) Ask user

If no directory exists and no AGENTS.md preference:

No worktree directory found. Where should I create worktrees?

1. .worktrees/ (project-local, hidden)
2. ~/.config/superpowers/worktrees/<project-name>/ (global location)

Which would you prefer?

## Safety verification

### For project-local directories (.worktrees or worktrees)

Verify directory is ignored before creating a worktree:

```bash
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

If not ignored:
1. Add appropriate line to `.gitignore`
2. Commit the change
3. Proceed with worktree creation

Why critical: prevents accidentally committing worktree contents to repository.

### For global directory (~/.config/superpowers/worktrees)

No `.gitignore` verification needed because it is outside the project.

## Creation steps

### 1) Detect project name

```bash
project=$(basename "$(git rev-parse --show-toplevel)")
```

### 2) Create worktree

```bash
case $LOCATION in
  .worktrees|worktrees)
    path="$LOCATION/$BRANCH_NAME"
    ;;
  ~/.config/superpowers/worktrees/*)
    path="~/.config/superpowers/worktrees/$project/$BRANCH_NAME"
    ;;
esac

git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

### 3) Run project setup

Run the repo's standard setup command for the new worktree.

Discovery order:
1. `AGENTS.md` in the repo
2. `README.md` or docs
3. Tooling hints (for example: `Makefile`, `package.json` scripts, language manifests)

Use the smallest bootstrap command that makes the workspace runnable. If none is documented, skip and report it.

```bash
# Example only. Use repo-specific commands.
# <setup-command>
```

### 4) Verify clean baseline

Run tests to ensure the worktree starts clean:

```bash
# Example only. Use repo-specific command.
# <baseline-test-command>
```

If tests fail, report failures and ask whether to proceed or investigate.

If tests pass, report ready.

### 5) Report location

Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>

## Quick reference

| Situation | Action |
|-----------|--------|
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check `AGENTS.md`, then ask user |
| Directory not ignored | Add to `.gitignore` and commit |
| Tests fail during baseline | Report failures and ask |
| No setup instructions found | Skip setup and report |

## Common mistakes

### Skipping ignore verification

- Problem: worktree contents get tracked and pollute git status.
- Fix: always run `git check-ignore` before creating a project-local worktree.

### Assuming directory location

- Problem: creates inconsistency and violates project conventions.
- Fix: follow priority order: existing directory, then `AGENTS.md`, then ask.

### Proceeding with failing tests

- Problem: cannot distinguish pre-existing issues from new regressions.
- Fix: report failures and get explicit permission to continue.

### Hardcoding setup commands

- Problem: breaks on projects using different toolchains.
- Fix: discover commands from `AGENTS.md` and repo docs, then run repo-specific setup.

## Example workflow

You: I'm using the using-git-worktrees skill to set up an isolated workspace.

[Check .worktrees/ - exists]
[Verify ignored - git check-ignore confirms .worktrees/ is ignored]
[Create worktree: git worktree add .worktrees/auth -b feature/auth]
[Run npm install]
[Run npm test - 47 passing]

Worktree ready at /Users/username/myproject/.worktrees/auth
Tests passing (47 tests, 0 failures)
Ready to implement auth feature

## Red flags

Never:
- Create a worktree without ignore verification for project-local directories
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous
- Skip `AGENTS.md` checks

Always:
- Follow priority: existing directories, then `AGENTS.md`, then ask user
- Verify ignore rules for project-local directories
- Auto-detect and run project setup
- Verify a clean test baseline
