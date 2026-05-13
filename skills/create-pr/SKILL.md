---
name: create-pr
description: "Create a clear, review-ready pull request with gh CLI. Gather context from commits, diff, and Linear when available; follow repository templates; push safely; and return the PR URL with merge guidance."
---

# Create Pull Request

## Goal
Open a high-quality PR that is easy to review and safe to merge:
- includes only intended changes
- uses a clear title and useful body
- follows repo PR template when present
- links related Linear issues with the correct magic words
- reports final PR status and next actions

## Inputs
- `base_branch` (optional, default: repo default branch)
- `is_draft` (`true/false`, default: `false`)
- `title_hint` (optional)
- `extra_context` (optional: issue links, rollout notes, risks)

## Safety rules
1) Never create a PR from `main`/`master` directly.
2) Never include unrelated unstaged/uncommitted changes.
3) Do not rewrite branch history unless explicitly requested.
4) If history rewrite is required, use `--force-with-lease` only.
5) If a PR already exists for the branch, do not create a duplicate.

## Workflow
1) Check prerequisites
   - `gh auth status`
   - `git status --short --branch`
   - `git branch --show-current`

2) Determine base branch
   - Prefer user input.
   - Otherwise use repo default branch:
     - `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`

3) Review branch content
   - `git log --oneline origin/<base_branch>..HEAD`
   - `git diff --stat origin/<base_branch>...HEAD`
   - Confirm scope is coherent and PR-ready.

4) Discover related Linear issues
   - Use Linear MCP when it is available.
   - Search the branch name, commits, title hint, and `extra_context` for issue IDs such as `SOYIO-20`.
   - If issue IDs are found, verify them with Linear MCP and capture their titles/statuses.
   - If no issue IDs are found and Linear MCP is available, search Linear using branch/title/commit keywords.
   - If Linear MCP is unavailable, use only explicit issue IDs already present in local context and state that Linear lookup was unavailable.
   - Never invent issue IDs.

5) Ensure branch is pushed
   - If no upstream: `git push -u origin HEAD`
   - Otherwise: `git push`

6) Build PR content
   - Title: concise, outcome-focused; Conventional Commit style preferred.
   - Body:
      - If `.github/pull_request_template.md` (or equivalent) exists, follow it exactly.
      - Otherwise include: context, summary, testing, risk/rollback, related issue.
      - Put related Linear issues in the most relevant template section, or add `## Linear` when there is no obvious section.
      - Link each Linear issue with an allowed magic word followed by the ID, for example `closes SOYIO-20`.
      - Use a closing magic word only when this PR fully completes the issue.
      - Use a non-closing magic word when this PR is partial, preparatory, informational, or only related.

Allowed closing magic words:
`close`, `closes`, `closed`, `closing`, `fix`, `fixes`, `fixed`, `fixing`, `resolve`, `resolves`, `resolved`, `resolving`, `complete`, `completes`, `completed`, `completing`, `implements`, `implemented`, `implementing`.

Allowed non-closing magic words:
`ref`, `refs`, `references`, `part of`, `related to`, `contributes to`, `toward`, `towards`.

7) Create or reuse PR
   - Check existing PR first:
      - `gh pr view --json url,number,state 2>/dev/null`
   - If existing PR found, return it and summarize status.
   - If no PR exists, create it:

```bash
gh pr create --title "<title>" --body "<body>" --base <base_branch>
```

For draft PR:

```bash
gh pr create --title "<title>" --body "<body>" --base <base_branch> --draft
```

8) Post-create checks
   - `gh pr view --json url,number,title,state,mergeStateStatus,reviewDecision`
   - Report CI/review state and what remains before merge.

## Validation
- Prefer smallest relevant checks before PR creation (lint/unit/targeted tests).
- Include test commands and concise outcomes in the PR body.
- Verify every Linear issue link uses one allowed magic word followed by the issue ID.
- If checks were not run, state why and call it out explicitly.

## Output format
Return:
- PR number + URL
- base/head branches
- draft or ready status
- merge/check state
- test summary (commands + results)
- related Linear issue links
- recommendation: ready for review, wait for CI, or needs follow-up

## Error handling
- If working tree is dirty, ask to commit or stash first.
- If no commits ahead of base, report no PR needed.
- If `gh` auth fails, instruct to run `gh auth login`.
- If creation fails due to permissions, report exact error and next step.
