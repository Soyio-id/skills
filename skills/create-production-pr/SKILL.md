---
name: create-production-pr
description: "Create a production promotion PR from main/master to production in an allowed repo or the current repo. Use the repo PR template when available, list included PRs and close only the issues those PRs completed (linked with a closing magic word), and generate a date-based title with production-only version suffixes."
---

# Create Production Pull Request

## Goal
Open a safe production promotion PR that:
- targets `production`
- uses `main` or `master` as the head branch
- follows the repository PR template when one exists
- lists the PRs included in the promotion as `- #123`
- closes only the issues that the included PRs completed (linked with a closing magic word), so the promotion moves them from "In Staging" to "Done"
- uses the title `Paso a produccion DD/MM/YY` with `v2`, `v3`, and so on only when needed

## Inputs
- `repo` (optional: use the repo declared for this skill; otherwise use the current repo)
- `head_branch` (optional: prefer explicit input; otherwise use `main`, then `master`)
- `base_branch` (optional, default: `production`)

## Example
```text
Use `create-production-pr` for `soyio-id/dashboard`.
Create a PR from `main` to `production`.
Use the repo PR template if present.
List included PRs as `- #123`.
```

## Safety rules
1. Only create PRs targeting `production`.
2. Never open a duplicate PR when an open PR already exists for the same `head` and `base` branches.
3. Do not guess a non-standard source branch; use explicit input if neither `main` nor `master` exists.
4. Title uniqueness is checked only against PRs targeting `production`.
5. If multiple PR templates exist and the correct one is unclear, stop and ask.

## Workflow
1) Check prerequisites
   - `gh auth status`
   - Determine the target repo:
     - Use `repo` if provided.
     - Otherwise use the current repo from `gh repo view --json nameWithOwner -q .nameWithOwner`.
   - Determine `base_branch`:
     - Default to `production`.
   - Determine `head_branch`:
     - Use explicit input when provided.
     - Otherwise prefer `main`, then `master`.

2) Verify branches exist
   - Confirm the repo is reachable:

```bash
gh repo view <repo> --json nameWithOwner,defaultBranchRef
```

   - Confirm `production` exists:

```bash
gh api repos/<repo>/branches/production >/dev/null
```

   - If `head_branch` is not provided, probe `main` first and then `master`:

```bash
gh api repos/<repo>/branches/main >/dev/null
gh api repos/<repo>/branches/master >/dev/null
```

3) Reuse an open production PR when one already exists
   - Check for an existing open PR from `<head_branch>` to `production`:

```bash
gh pr list --repo <repo> --state open --base production --head <head_branch> --json number,title,url
```

   - If one exists, return it instead of creating a new PR.

4) Discover included PRs
   - Compare the commits in `production...<head_branch>`:

```bash
gh api repos/<repo>/compare/production...<head_branch>
```

   - From the compare response, collect commit SHAs in order.
   - For each commit SHA, resolve associated pull requests:

```bash
gh api repos/<repo>/commits/<sha>/pulls
```

   - Keep only merged PRs.
   - Deduplicate PR numbers while preserving first appearance order.
   - Format the final list exactly like:

```markdown
- #124
- #130
```

   - If no PRs are found, stop and report that there are no merged PRs to promote.

5) Extract the issues completed by the included PRs
   - Do not search Linear by default.
   - Fetch each included PR's body to inspect its Linear links:

```bash
gh pr view <number> --repo <repo> --json number,title,body,headRefName,url
```

   - Collect ONLY the issues that an included PR linked with a closing magic word (for example `closes SOYIO-20`). These are the issues that moved to "In Staging" when the PR merged to `main`, and that this promotion moves to "Done".
   - Ignore any issue that appears only with a non-closing magic word, only in prose, or only inferred from titles/branches. Do not promote those — promoting them would mark unrelated or follow-up issues as Done.
   - Deduplicate the collected issue IDs, preserving first appearance order.
   - Use Linear MCP only when the user explicitly asks for Linear verification or lookup.
   - Never invent issue IDs.

6) Resolve the PR template
   - Check common template locations in this order:
     - `.github/PULL_REQUEST_TEMPLATE.md`
     - `.github/PULL_REQUEST_TEMPLATE/pull_request_template.md`
     - `.github/pull_request_template.md`
     - `docs/PULL_REQUEST_TEMPLATE.md`
     - `PULL_REQUEST_TEMPLATE.md`
   - Use the first unambiguous match.
   - If the repo has no PR template, use the fallback body containing the included PR list and any related Linear issue links.

7) Build the PR body
   - If a template exists, preserve its structure and insert the included PR list in the most relevant section.
   - Put the completed issues (from step 5) in the most relevant template section, or add `## Linear` when there is no obvious section.
   - If there is no obvious section for included PRs, append a section named `## PRs incluidas` followed by the list.
   - Link each completed issue with a closing magic word followed by the ID, for example `closes SOYIO-20`, so merging to `production` moves it from "In Staging" to "Done".
   - Only include issues collected in step 5 (linked by an included PR with a closing magic word). Never add issues that were only referenced, mentioned in prose, or inferred — including them would close unrelated or follow-up issues.
   - Use the closing magic words from `Magic words reference`.
   - If no template exists, the body should contain the PR list and, when present, the completed-issue links:

```markdown
## PRs incluidas
- #124
- #130

## Linear
closes SOYIO-20
closes SOYIO-21
```

8) Build the title
   - Use the current date in `DD/MM/YY` format.
   - Start with:

```text
Paso a produccion DD/MM/YY
```

   - Check existing PRs targeting `production` with the same date title pattern:

```bash
gh pr list --repo <repo> --state all --base production --search '"Paso a produccion DD/MM/YY" in:title' --json title,number,url
```

   - If there is no exact title match, use the base title.
   - If the base title already exists for a PR targeting `production`, use the next available suffix:
     - `Paso a produccion DD/MM/YY v2`
     - `Paso a produccion DD/MM/YY v3`
     - and so on

9) Create the PR
   - Use `gh pr create` with the chosen title, body, `production` base, and selected head branch.
   - Example:

```bash
gh pr create --repo <repo> --base production --head <head_branch> --title "<title>" --body "<body>"
```

## Validation
- Verify the compare range is non-empty before creating the PR.
- Verify the included PR list is deduplicated and ordered.
- Verify every Linear issue link uses a closing magic word followed by the issue ID, and that every linked issue was closed by an included PR (none are referenced-only, prose-only, or follow-up issues).
- Verify the final title is unique among PRs targeting `production`.
- Verify the created or reused PR targets `production`.

## Magic words reference
Closing magic words (the only ones used in production PRs, so merging to `production` moves issues to Done):
`close`, `closes`, `closed`, `closing`, `fix`, `fixes`, `fixed`, `fixing`, `resolve`, `resolves`, `resolved`, `resolving`, `complete`, `completes`, `completed`, `completing`.

Do not use non-closing/reference words (`references`, `part of`, `related to`, etc.) in a production PR. Issues that were not completed by an included PR must not appear at all.

## Output format
Return:
- repo
- PR number and URL
- base and head branches
- final PR title
- whether a repo template was used
- number of included PRs
- the included PR list
- completed-issue links (closes ...)

## Error handling
- If `gh` auth fails, instruct the user to run `gh auth login`.
- If `production`, `main`, or `master` cannot be found as needed, report the missing branch and stop.
- If there are multiple candidate templates, ask which one to use.
- If there are no commits or no merged PRs to promote, report that no production PR is needed.
