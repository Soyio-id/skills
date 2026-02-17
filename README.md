# Soyio Skills

Small skill library for Soyio teams.

## Structure

- `skills/` contains each skill in its own directory.
- Every skill directory includes a `SKILL.md` file.

## Current skills

- `commit-work`
- `prepare-security-prs` - Prepare Security PRs

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
