# Contributing

Thanks for contributing to Soyio Skills.

## Skill format

- Create one folder per skill at `skills/<skill-slug>/`.
- Use short, discoverable kebab-case slugs.
- Add a single file: `skills/<skill-slug>/SKILL.md`.
- Include frontmatter at the top:

```md
---
name: your-skill-slug
description: "One-sentence purpose and when to use it."
---
```

## Writing guidelines

- Keep each skill focused on one workflow.
- Prefer explicit inputs, safety rules, and clear step-by-step actions.
- Keep commands copy-pasteable.
- Keep diffs minimal and avoid unrelated edits.
- Do not include secrets, tokens, or internal credentials.

## Pull request checklist

- Skill name and folder slug match.
- README updated under current skills when adding a new skill.
- Skill instructions are concise and actionable.
- No unrelated file changes.
