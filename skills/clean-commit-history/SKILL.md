---
name: clean-commit-history
description: Clean up commit history by folding uncommitted changes into the appropriate recent commits via fixup and autosquash rebase, then force-push. Use when uncommitted changes logically belong to recent commits and the history needs tidying before review.
user_invocable: true
---

Clean up the current branch's commit history by incorporating uncommitted changes into the correct recent commits.

## Procedure

### 1. Assess current state

- Run `git status` to check for uncommitted changes (staged + unstaged + untracked).
- If there are NO uncommitted changes, stop and inform the user.
- Run `git log --oneline <base-branch>..HEAD` to see the branch's commits (detect base branch from tracking info or the repository's default branch, e.g. `main` or `master`).
- If there is only one commit on the branch, there is nothing to fixup into — just amend that commit with the pending changes and force-push.

### 2. Analyze and assign

- Read the diff of uncommitted changes (`git diff` and `git diff --cached`).
- For each hunk or logically related group of changes, determine which existing commit it belongs to based on:
  - Same file modified in that commit.
  - Same logical concern (e.g., a test fix belongs with its source fix).
  - Follow the cohesion rules from the commits skill (`~/.claude/skills/commits/SKILL.md`).
- If some changes don't fit any existing commit, plan a new commit for them.
- **If the assignment is large, complex, or ambiguous** (many files, multiple target commits, unclear ownership): enter plan mode, present the assignment, and wait for approval.
- **If the assignment is straightforward** (few changes, obvious target commits): briefly state the assignment and proceed to execution without plan mode.

### 3. Execute fixups

For each group of changes mapped to an existing commit:

1. Stage only the relevant files/hunks (`git add <files>` or `git add -p` if partial).
2. Create a fixup commit: `git commit --fixup=<target-commit-sha>`.
3. Repeat until all changes are committed.

If any changes need a new commit, create it normally following the commit format from the commits skill.

### 4. Autosquash rebase

Run: `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <base-commit>~1`

- `GIT_SEQUENCE_EDITOR=true` auto-accepts the rebase todo since `--autosquash` already reorders fixups.
- If the rebase fails with conflicts:
  - Read the conflicting files and assess whether the resolution is trivial (e.g., adjacent line changes, whitespace, obvious ordering).
  - If trivial: resolve the conflict, stage the files, and continue the rebase with `git rebase --continue`.
  - If ambiguous or non-trivial: stop, show the conflict to the user, and ask how to proceed.

### 5. Force push

Run: `git push --force-with-lease`

- NEVER use `--force`. Always use `--force-with-lease` to avoid overwriting others' work.
- If the push is rejected, stop and inform the user.

## Safety rules

- NEVER operate on `master` or `main` branches. If the current branch is `master` or `main`, stop and warn.
- NEVER skip git hooks (`--no-verify`).
- Always use `--force-with-lease`, never `--force`.
- For complex or ambiguous assignments, get user approval before making changes.

## Important

- Never add AI authorship metadata (no "Co-authored-by: Claude").
- Follow commit format and cohesion rules from the commits skill (`~/.claude/skills/commits/SKILL.md`).
