---
name: create-pr
description: "Create a clear, review-ready pull request with gh CLI. Gather context from commits and diff; link the PR's Linear issue from trusted sources (branch name or explicitly provided ID) and confirm any inferred issue with the user before linking; never put a closing magic word on an unrelated or follow-up issue; follow repository templates; push safely; when the diff touches frontend, capture screenshots and upload them to the PR through the browser (gh CLI cannot upload images); offer to post the PR in #dev-flash-reviews on Slack (default: don't post); monitor the first CI run and bot reviews (Datadog, Greptile, Codex) and address failures and comments; and return the PR URL with merge guidance."
---

# Create Pull Request

## Goal
Open a high-quality PR that is easy to review and safe to merge:
- includes only intended changes
- uses a clear title and useful body
- follows repo PR template when present
- links the PR's related Linear issue(s) with the correct magic word, confirming inferred issues and never putting a closing magic word on an unrelated or follow-up issue
- shows UI changes with screenshots embedded in the PR body when frontend is involved
- reports final PR status and next actions

## Inputs
- `base_branch` (optional, default: repo default branch)
- `is_draft` (`true/false`, default: `false`)
- `title_hint` (optional)
- `extra_context` (optional: issue links, rollout notes, risks)
- `screenshots` (optional: paths to images the user already captured; skips capturing)

## Safety rules
1) Never create a PR from `main`/`master` directly.
2) Never include unrelated unstaged/uncommitted changes.
3) Do not rewrite branch history unless explicitly requested.
4) If history rewrite is required, use `--force-with-lease` only.
5) If a PR already exists for the branch, do not create a duplicate.
6) Screenshots must only show local/test/seed data. Never capture real personal data, customer data, tokens, or secrets.
7) Never enter GitHub credentials in the browser. If Chrome is not logged in to GitHub, ask the user to log in.
8) Never post to Slack without an explicit "yes" from the user in this conversation. No answer means no post.

## Agent tooling
This skill is shared by Claude Code, Codex, and OpenCode. Use whichever tool the current agent has for each capability:

| Capability | Claude Code | Codex | OpenCode / fallback |
|---|---|---|---|
| Drive the user's logged-in Chrome | `claude-in-chrome` (`find`/`read_page`, `file_upload`, `upload_image`, `javascript_tool`) | Chrome plugin (`chrome@openai-bundled`) | `browser-use` skill (CDP to the local Chrome; see its `uploads.md` and `screenshots.md`) |
| Ask the user | `AskUserQuestion` | ask in chat and wait | ask in chat and wait |
| Background wait | Bash `run_in_background` / `Monitor` | background shell loop, check back | background shell loop, check back |
| Slack | Slack MCP (`slack_search_channels`, `slack_send_message`) | Slack plugin (`slack@openai-curated`) | none: print the message for the user to paste |
| Address comments | `address-pr-comments` command / `address-github-comments` skill | `address-pr-comments` prompt / `address-github-comments` skill | `address-pr-comments` command / `address-github-comments` skill |

If a capability is missing in the current agent, use the fallback column or tell the user; never improvise with an unrelated tool.

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

5) Detect frontend changes and capture screenshots
   - Frontend is involved when the diff changes user-visible UI, e.g.:
     - files: `.tsx`, `.jsx`, `.vue`, `.svelte`, `.html`, `.erb`, `.haml`, `.slim`, `.css`, `.scss`, `.sass`, `.less`
     - dirs: `components/`, `pages/`, `app/` (Next.js), `views/`, `layouts/`, `styles/`, `public/`
     - UI config: Tailwind/theme/design tokens, i18n copy shown on screen
   - Not frontend: changes limited to tests, stories, types, or non-rendering utilities. If unsure, ask the user.
   - If not frontend, skip to step 6 and skip step 9.
   - If the user passed `screenshots`, use those and skip capturing.
   - Otherwise:
     - Identify the affected screens/routes from the diff. If the URL or state needed to reach them is not obvious, ask the user.
     - Reuse a running dev server if there is one; otherwise start the app with the project's dev script (Claude Code can use the `run` skill). Use seed/test data only.
     - Capture with the browser (see `Agent tooling`): open the screen, reach the changed state, and take a screenshot of each changed screen/state. Prefer focused viewport shots over full-page noise; add a mobile width when the change is responsive.
     - Add "before" shots only when the original is cheap to capture (e.g. the same screen on staging); otherwise "after" only.
     - Save PNGs under `.context/screenshots/` when the workspace has `.context/`, else a temp dir, with descriptive names (`login-form-error-state.png`).
   - If the app cannot be run or the screen cannot be reached, ask the user to provide screenshots or confirm skipping; if skipped, say so in the PR body under testing.

6) Ensure branch is pushed
   - If no upstream: `git push -u origin HEAD`
   - Otherwise: `git push`

7) Build PR content
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
      - If screenshots were captured, keep the template's screenshots section (or add `## Screenshots`) with a placeholder line; step 9 fills it.

8) Create or reuse PR
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

9) Upload screenshots through the browser (frontend PRs only)
   - `gh` cannot upload images, so use GitHub's web uploader in the user's logged-in Chrome (see `Agent tooling`) to get `https://github.com/user-attachments/assets/...` URLs:
     1. Open the PR URL in a new tab. If GitHub shows a login page, stop and ask the user to log in.
     2. Locate the hidden `input[type=file]` of the new-comment box at the bottom of the PR conversation. Do not click the file input or the "Paste, drop, or click" link (it opens a native picker the agent cannot control).
     3. Set the PNGs (paths from step 5) on that input with the agent's upload tool (Claude: `file_upload`, keep each call under 10 MB, or `upload_image` with a fresh screenshot if the path is rejected; browser-use: CDP `DOM.setFileInputFiles` per its `uploads.md`).
     4. Wait until the comment textarea contains one `![...](https://github.com/user-attachments/assets/...)` line per image (uploads take a few seconds).
     5. Read the generated markdown from the textarea, then clear it. Never click "Comment".
   - Put the images in the screenshots section of the body, each with a short caption naming the screen/state. Use a two-column table for before/after pairs.
   - Apply the body with `gh pr edit <number> --body-file <file>` (write the body to a temp file to avoid shell quoting issues).
   - Verify: `gh pr view --json body` contains the asset URLs, and the PR page renders the images (screenshot the description in the browser).
   - If no browser tool is available or the upload fails twice, stop retrying: leave the local paths in your report, tell the user, and ask them to drag the images into the PR description.

10) Post-create checks
   - `gh pr view --json url,number,title,state,mergeStateStatus,reviewDecision`
   - Report CI/review state and what remains before merge.

11) Offer to post in #dev-flash-reviews (default: no)
   - Start step 12's watchers in the background first, so monitoring runs while waiting for the answer.
   - Ask the user whether to post the PR in Slack `#dev-flash-reviews`. Present "No" as the default/first option and include the exact message preview in the question.
   - Only post on an explicit yes. Any other answer, or no answer, means skip.
   - Message: one line, casual, like a teammate dropping a link. Format: `<PR_URL|short description> <emoji>`
     - Description: 2-8 words, mostly Spanish (English tech terms are fine), describing the outcome, not the implementation. Lowercase or sentence case, no trailing period, no Conventional Commit prefix.
     - Emoji: `:minions:` for PRs in the `agents` repo, `:prisma:` for PRs in the `prisma` repo; otherwise none unless obvious (e.g. `:vanta:` for Vanta compliance fixes).
     - Optional short casual aside in parentheses only when it gives reviewers useful context (e.g. "(queda en draft a propósito)").
     - Never add a summary paragraph, `+X / -Y`, file counts, Linear IDs, or bullet lists for a single PR. For several related PRs at once, use a one-line heading plus one bullet per PR (`• repo — <PR_URL|descripción>`).
     - Examples:
       - `<https://github.com/Soyio-id/agents/pull/208|Editar apps con chat y anotaciones> :minions:`
       - `<https://github.com/Soyio-id/soyio-iac-gcp/pull/9|cleanup IAC GCP>`
       - `<https://github.com/Soyio-id/soyio/pull/929|Optimización de los backend tests del CI (18m -> 6m)>`
   - If yes:
     - Find the `#dev-flash-reviews` channel ID with the agent's Slack tool, then send the message with link previews disabled (Claude Slack MCP: `unfurl_app_links: false`; other agents: turn off unfurl/link preview if the tool allows it). The GitHub preview card is noise in this channel.
     - Return the Slack message link.
   - If the agent has no Slack tool or it is not authenticated, print the message for the user to paste and say why it was not sent. Never post to another channel or via another tool.

12) Monitor the first CI run and bot reviews
   - Skip if the PR is a draft and the repo's bots don't review drafts; say so in the report.
   - CI: run `gh pr checks <number> --watch` in the background and wait for it to finish (Claude: `run_in_background` and wait for the notification instead of polling).
   - Bot reviews: Datadog, Greptile, and Codex post asynchronously, usually within ~10 min. Poll every ~2 min in the background, up to 20 min after PR creation, with:
     - `gh api repos/{owner}/{repo}/pulls/<number>/reviews`
     - `gh api repos/{owner}/{repo}/pulls/<number>/comments` (inline)
     - `gh api repos/{owner}/{repo}/issues/<number>/comments` (summary comments)
     - Match bot logins containing `datadog`, `greptile`, `codex` (e.g. `greptile-apps[bot]`, `chatgpt-codex-connector[bot]`).
     - Codex signals "no issues" with a 👍 reaction on the PR instead of a review: `gh api repos/{owner}/{repo}/issues/<number>/reactions`.
   - Done when all checks have finished and every bot that reviews this repo has posted (or the 20 min window ends; report which bots never showed up).
   - Do not trigger bots manually unless the user asks.

13) Address results
   - Failing checks: read logs with `gh run view <run-id> --log-failed`. Fix failures caused by this PR; report flaky or unrelated failures (with the failing job and error) instead of changing unrelated code.
   - Bot or human review comments: run `address-pr-comments` (fall back to the `address-github-comments` skill if unavailable) to fix relevant comments and resolve or justify the rest. If `address-pr-comments` is a user slash command/prompt the agent cannot invoke, follow its instructions directly: address and resolve remaining comments that are relevant to the current code; otherwise reply with a justification.
   - Never use `--no-verify` or force-push; follow the repo's normal commit/push flow.
   - If nothing failed and no actionable comments came in, report the PR as clean.

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
- screenshots: uploaded (count), skipped (why), or not applicable (no frontend)
- Slack: message link, or "not posted"
- first CI run and bot reviews: results per check/bot, what was fixed or addressed, what remains
- recommendation: ready for review, wait for CI, or needs follow-up

## Error handling
- If working tree is dirty, ask to commit or stash first.
- If no commits ahead of base, report no PR needed.
- If `gh` auth fails, instruct to run `gh auth login`.
- If creation fails due to permissions, report exact error and next step.
- If the app cannot be started for screenshots, report the error and ask the user to provide screenshots or skip.
- If the browser tool is not connected (e.g. Chrome remote debugging not allowed for browser-use) or GitHub is logged out, ask the user to fix it; do not retry blindly.
