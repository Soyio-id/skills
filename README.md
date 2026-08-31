# Soyio Skills

Small skill library for Soyio teams.

## Structure

- `skills/` contains each skill in its own directory.
- Every skill directory includes a `SKILL.md` file.

## Current skills

- `commit-work` - Create clean, logically scoped commits with strong messages.
- `create-production-pr` - Open a production promotion PR from `main`/`master` to `production`, using the repo template, included PR list, and Linear issue links.
- `create-pr` - Open a review-ready PR with `gh`, template alignment, Linear issue links, and checks.
- `create-worktree` - Create an isolated repo worktree for a branch or PR review.
- `patch-vulnerabilities` - Run a recurring vulnerability sweep from the Vanta API: fix OS, gem, and npm packages, deactivate unfixable findings, open PRs, and post a Slack summary.
- `prepare-security-prs` - Triage dependency security PRs and apply minimal safe fixes.
- `using-git-worktrees` - Set up isolated worktrees with directory and safety verification.

## Install skills

- Install all skills from this repo:

```bash
npx skills add soyio-id/skills --all
```

- Install one skill:

```bash
npx skills add soyio-id/skills@commit-work
```

- Install another skill:

```bash
npx skills add soyio-id/skills@prepare-security-prs
```

- Install globally without prompts:

```bash
npx skills add soyio-id/skills@commit-work -g -y
```

## Add a new skill

1. Create `skills/<skill-name>/`.
2. Add `skills/<skill-name>/SKILL.md`.
3. Keep each skill focused on one workflow.

## Contributing

- See `CONTRIBUTING.md` for naming, structure, and PR guidelines.
