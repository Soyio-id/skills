---
name: prepare-security-prs
description: "Triage and prepare automated dependency security PRs for merge with minimal risk. Identify bot PRs that need intervention, resolve required issues only, refresh stale branches safely, detect superseded PRs, and keep diffs dependency-focused."
---

# Prepare Security PRs

## Overview
Triage and prepare automated dependency PRs for merge with minimal risk:
- identify dependency bot PRs that actually need intervention
- resolve comments/check failures only when needed
- refresh stale branches safely
- detect superseded PRs
- keep diffs minimal and dependency-focused

## Inputs
- `owner/repo`
- `bot_filters` (optional list, example: `dependabot[bot]`, `renovate[bot]`, `snyk-bot`)
- `stale_threshold` (default: `behind_by > 50`)
- `test_depth` (`none`, `targeted`, `full`; default: `targeted`)
- `allow_branch_rewrite` (`true/false`, default: `false`)

## Safety rules
1) Only touch PRs that are clearly dependency-update PRs.
2) Never introduce unrelated code changes.
3) Prefer the smallest possible diff (manifest + lockfile only when possible).
4) Never force-push unless branch cleanup is explicitly enabled.
5) If force-push is needed, use `--force-with-lease` only.
6) If a PR is superseded by base branch versions, recommend closing.
7) If uncertain, report and ask before risky actions.

## How to identify dependency bot PRs
Use one or more signals:
- PR author matches configured bot account.
- PR title matches common patterns: `Bump`, `Upgrade`, `Security update`.
- Labels include dependency/security labels.
- Files changed are mostly dependency manifests/lockfiles.

## Workflow
1) Discover candidate PRs

```bash
gh pr list --repo <owner/repo> --state open --limit 200 --json number,title,url,author,labels,headRefName,baseRefName,updatedAt,mergeable,mergeStateStatus,reviewDecision
```

2) Filter to dependency-update PRs
- Keep PRs that match identification signals.
- Exclude feature/fix PRs.

3) Gather health signals per PR
- CI checks status
- Actionable review comments
- Ahead/behind vs base
- Net diff scope (dependency-only or not)
- Whether update is already superseded in base

4) Classify each PR
- `ready`: mergeable, no actionable feedback, checks green/pending
- `needs_fix`: failing checks, review-requested fixes, bad constraints, missing lockfile
- `stale`: high `behind_by` or frequent base conflicts
- `superseded`: base already has same/newer secure version
- `noisy_history`: huge PR UI but tiny net merge diff

5) Act only where needed
- For `needs_fix`: apply minimal fix, update lockfile conservatively, run tests, push, comment.
- For `stale`: refresh from base, verify diff remains dependency-only, push, comment.
- For `superseded`: do not patch; comment recommendation to close.
- For `noisy_history`: if rewrite is allowed, rebuild branch from current base with only intended dependency patch, create one clean commit, force-push with lease, comment.

6) Validation strategy
- Use repo-appropriate commands.
- Prefer targeted tests first for upgraded package impact.
- Run full suite only when requested or risk is high.
- Include command and result summary in PR note.

7) Final report format
For each dependency PR, return:
- PR number and URL
- classification
- action taken (or no action)
- commit SHA (if updated)
- mergeability/check state
- recommendation: merge, wait for CI, close superseded, or manual review

## Heuristics (defaults)
- stale if `behind_by > 50`
- mildly behind (`<= 25`) is usually acceptable unless checks/reviews fail
- superseded if base already includes the same/newer target dependency version

## Definition of done
- only necessary dependency PRs were modified
- each modified PR has a clear update comment
- no unrelated files were changed
- final summary gives merge-ready guidance PR-by-PR
