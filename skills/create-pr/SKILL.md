---
name: create-pr
description: "Create a clear, review-ready pull request with gh CLI. Gather context from commits and diff; link the PR's Linear issue from trusted sources (branch name or explicitly provided ID) and confirm any inferred issue with the user before linking; never put a closing magic word on an unrelated or follow-up issue; follow repository templates; push safely; and return the PR URL with merge guidance."
---

# Create Pull Request

## Goal
Open a high-quality PR that is easy to review and safe to merge:
- includes only intended changes
- uses a clear title and useful body
- follows repo PR template when present
- links the PR's related Linear issue(s) with the correct magic word, confirming inferred issues and never putting a closing magic word on an unrelated or follow-up issue
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

4) Determine the PR's Linear issue(s)
   - The PR should reference only issues it actually relates to. Never link an unrelated or follow-up issue with a closing magic word, and confirm anything that is not explicit before linking it.
   - Trusted sources (treat as the PR's own issue; link without extra confirmation):
     - The branch name (e.g. `feature/soyio-287-...` → `SOYIO-287`).
     - An issue ID the user stated is what this PR resolves or addresses — in `title_hint`, `extra_context`, or the conversation (e.g. "resolvamos el issue ABC-123"). A mere mention of an issue is NOT enough; the user must indicate it is this PR's issue. If the user mentions an issue as a follow-up, dependency, or someone else's work, it is not a trusted source — treat it as inferred (or omit it).
   - If trusted sources disagree (e.g. the branch name and the user names different issues), do not link both blindly — confirm with the user which issue(s) this PR resolves.
   - Treat the PR's own issue as completed (closing magic word) unless the user indicates this PR only partially addresses it.
   - Inferred sources (candidates only — never link without confirming with the user first):
     - Issue IDs found in commit messages or free-form `extra_context`.
     - Issues returned by a Linear MCP keyword search on the branch/title/commits.
   - For each inferred candidate, ask the user whether it belongs to this PR and, if so, whether the PR completes it (closing magic word) or is only related/partial (non-closing magic word). Drop any candidate the user does not confirm.
   - If no issue is found in any source, ask the user whether the PR is related to a Linear issue and, if so, which one. Not every PR comes from an issue — if the user says there is none, proceed without a Linear link.
   - When Linear MCP is available, use it to verify identified issues (title/status).
   - Never invent issue IDs.

5) Ensure branch is pushed
   - If no upstream: `git push -u origin HEAD`
   - Otherwise: `git push`

6) Build PR content
   - Title: concise, outcome-focused; Conventional Commit style preferred.
   - Body:
      - If `.github/pull_request_template.md` (or equivalent) exists, follow it exactly.
      - Otherwise include: context, summary, testing, risk/rollback, related issue.
      - Put the PR's Linear issue(s) in the most relevant template section, or add `## Linear` when there is no obvious section.
      - Link each confirmed issue with an allowed magic word followed by the ID, for example `closes SOYIO-20`.
      - Use a closing magic word only when this PR fully completes that issue.
      - Use a non-closing magic word when this PR is partial, preparatory, or only related to that issue.
      - Never link an issue that was not confirmed per step 4, and never put a closing magic word on an unrelated or follow-up issue. To note a follow-up without Linear acting on it, write it as plain prose without the issue ID.
      - Use the magic words from `Magic words reference`.

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
- Verify every Linear issue link uses one allowed magic word followed by the issue ID, that inferred issues were confirmed with the user, and that no unrelated or follow-up issue carries a closing magic word.
- If checks were not run, state why and call it out explicitly.

## Magic words reference
Closing magic words:
`close`, `closes`, `closed`, `closing`, `fix`, `fixes`, `fixed`, `fixing`, `resolve`, `resolves`, `resolved`, `resolving`, `complete`, `completes`, `completed`, `completing`.

Non-closing magic words:
`ref`, `references`, `part of`, `related to`, `contributes to`, `towards`.

## Output format
Return:
- PR number + URL
- base/head branches
- draft or ready status
- merge/check state
- test summary (commands + results)
- related Linear issue link(s) (or a note that the PR has no related issue)
- recommendation: ready for review, wait for CI, or needs follow-up

## Error handling
- If working tree is dirty, ask to commit or stash first.
- If no commits ahead of base, report no PR needed.
- If `gh` auth fails, instruct to run `gh auth login`.
- If creation fails due to permissions, report exact error and next step.
