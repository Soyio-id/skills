---
name: fix-vulnerabilities
description: "Fix multiple dependency vulnerabilities across multiple repos. Parses Vanta-style vulnerability entries, groups by repo, creates a single fix branch per repo, applies all fixes, verifies compatibility, and creates PRs after user approval. Use when the user says '/fix-vulnerabilities' or asks to fix vulnerabilities across repos."
---

# Fix Multi-Repo Vulnerabilities

Resolve dependency vulnerabilities across multiple repositories from a batch of vulnerability entries.

## Input

The user provides one or more vulnerability entries, typically in Vanta format:

```
[Vanta] [github] [<repo-name>] npm-<package> <vulnerable-range>/<CVE-ID>
```

Examples:
```
[Vanta] [github] [soyio-rn-sdk] npm-minimatch < 3.1.3/CVE-2026-26996
[Vanta] [github] [soyio-docs] npm-minimatch >= 9.0.0, < 9.0.6/CVE-2026-26996
[Vanta] [github] [privacy-center] npm-minimatch >= 9.0.0, < 9.0.6/CVE-2026-26996
```

### Special case: Consolidated repos (aliases)

Some repos that Vanta reports have been consolidated into monorepos. When parsing, remap these repo names to their monorepo equivalent:

- `soyio-docs-bot-action` → `soyio-docs-bot` (now lives in `soyio-docs-bot/bot/`)
- `soyio-docs-indexer-action` → `soyio-docs-bot` (now lives in `soyio-docs-bot/indexer/`)
- `privacy-center` → `embeds` (now lives in `embeds/apps/privacy-center/`)

If aliases appear in the same batch, merge their vulnerabilities under the monorepo during the grouping phase and keep the affected app path for validation. For example, `privacy-center` findings should be grouped under `embeds` and validated with `pnpm --filter privacy-center ...` commands.

### Special case: AWS/infrastructure entries

Entries like `[Vanta] [aws] [aws] faraday:2.13.4/CVE-2026-25765` refer to gems detected in the production infrastructure. These should be treated as vulnerabilities in the `soyio` repo (check `Gemfile` / `Gemfile.lock`). The version shown (e.g., `2.13.4`) is the **currently installed** version, NOT the fixed version. Ask the user for the fixed version before proceeding.

### Parsing

The input format may vary. Extract the following from each entry:
- `repo_name`: the repository name (e.g., `soyio-rn-sdk`)
- `package_name`: the vulnerable package (e.g., `minimatch`), stripping the `npm-` or `gem-` prefix
- `vulnerable_range`: the range of vulnerable versions (e.g., `>= 9.0.0, < 9.0.6`)
- `cve_id`: the CVE identifier (e.g., `CVE-2026-26996`)
- `package_manager`: inferred from prefix (`npm-` → NODE, `gem-` → RUBY)

## Workspace context

The workspace root is the parent directory of this skill's location. Repos are sibling directories in the workspace root. Read the workspace instructions (`AGENTS.md` and, when present, `CLAUDE.md`) plus the target repo's local instructions to understand:
- Which repos exist and their package managers
- The main branch name for each repo (default `main`, except `soyio` which uses `master`)
- Lint/build commands for each repo or workspace app
- Monorepo routing details such as `privacy-center` living in `embeds/apps/privacy-center`

## Workflow

**Before starting, present the full grouped plan to the user and wait for explicit approval before making any changes.** If an `EnterPlanMode` tool is available, use it. Otherwise, present the plan as text output and ask the user to confirm before proceeding.

### Phase 1: Parse and group

1. Parse all vulnerability entries from the input
2. Deduplicate: same repo + same package + same vulnerable range = one fix
3. Apply repo aliases before grouping so each finding has a resolved repo directory and optional app path.
4. Group by resolved repo: `{ repo_dir, app_path?, vulnerabilities: [{ original_repo_name, package_name, vulnerable_range, cve_id, package_manager }] }`
5. Present the grouped plan to the user:
   - List each resolved repo with its vulnerabilities
   - Show the affected app path when a finding maps into a monorepo such as `embeds/apps/privacy-center`
   - Show the main branch for each repo
   - Show the branch name that will be created: `fix/vulnerabilities-<date>` (e.g., `fix/vulnerabilities-2026-03-23`)
   - If a repo has only one vulnerability, use `fix/<package_name>-vulnerability` instead

### Phase 2: Fix vulnerabilities (repo by repo)

**Before starting, save the current working directory.** All repo work must use absolute paths or `cd` into the repo and `cd` back. After completing ALL repos, return to the original working directory so the user's shell location is unchanged.

For each repo, in sequence:

#### Step 1: Setup branch

```bash
cd <workspace_root>/<repo_dir>
git checkout <main_branch>
git pull
git checkout -b <branch_name>
```

- For consolidated apps such as `privacy-center`, perform git operations in the monorepo root (`<workspace_root>/embeds`) and keep track of the affected app path (`apps/privacy-center`). Do not modify the deprecated standalone `privacy-center` repo unless the user explicitly asks for it.

#### Step 2: Detect package manager

Determine the package manager from workspace instructions or by checking for lockfiles in the resolved repo root:
- `yarn.lock` → yarn
- `pnpm-lock.yaml` → pnpm
- `package-lock.json` → npm
- `Gemfile.lock` → bundler

#### Step 3: For each vulnerability in this repo

##### Analyze the dependency

**NODE:**
- Check the relevant `package.json` for a direct dependency. In a monorepo app, check the app manifest first (for example `embeds/apps/privacy-center/package.json`) and then note whether overrides/resolutions are managed at the repo root.
- Run the appropriate `why` command to understand the dependency tree:
  - yarn: `yarn why <package_name>`
  - pnpm: `pnpm why <package_name>`
  - npm: `npm explain <package_name>`
- Identify which installed versions fall within the vulnerable range
- If the package is transitive, identify which direct dependency or dependencies introduce it

**RUBY:**
- Check `Gemfile` for direct dependency
- Check `Gemfile.lock` for installed version
- If the gem is transitive, inspect `Gemfile.lock` to identify the parent gem or gems that introduce it

##### Apply the fix

**NODE — Direct dependency:**
- Update the version specifier in `package.json` (`dependencies` or `devDependencies`) to the minimum fixed version (first version outside the vulnerable range)
- **Important:** If the vulnerable package appears as both a direct dependency AND a transitive dependency, always update the direct specifier first. Do NOT rely solely on an override/resolution — if the override is later removed, the stale direct specifier would reintroduce the vulnerability.
- Run install command

**NODE — Transitive dependency (not a direct dependency):**
- First identify the direct dependency that introduces the vulnerable package and try the smallest non-breaking update of that direct dependency. Stay on the same major version unless a broader change is clearly required and approved.
- Re-run `yarn why`, `pnpm why`, or `npm explain` after the direct dependency bump to verify whether the vulnerable transitive dependency is gone or now resolved to a fixed version.
- Only if the direct dependency bump does not solve the issue safely, add a resolution/override to force the fixed version.
- **Critical:** The resolution must target the same major version line. If vulnerable range is `>= 9.0.0, < 9.0.6`, resolve to `^9.0.6`, NOT to `^10.x`. If vulnerable range is `< 3.1.3`, resolve to `^3.1.3`, NOT to `^9.x`.
- In workspaces, place the override/resolution in the manifest where that package manager expects it, which is often the repo root manifest rather than the app manifest.
- Different package managers use different mechanisms:
  - **yarn (v1)**: `"resolutions"` in `package.json`. **NEVER use wildcard `"**/package"` when the same package exists across multiple major version lines** (e.g., minimatch 3.x AND 9.x). Yarn 1 resolutions are path-based, not version-based — a wildcard like `"**/minimatch": "^3.1.4"` catches ALL ranges (including `^9.x`) and forces them all to 3.x, silently downgrading consumers. Instead:
     1. Run `yarn why <package>` to identify each consumer and its required major version
     2. Add one scoped resolution per consumer path, targeting the correct major: `"**/<consumer>/package": "^<fixed-for-that-major>"`
     3. After `yarn install`, verify in `yarn.lock` that each range resolves to its own major line (not grouped with another major)
  - **pnpm**: `"pnpm.overrides"` in `package.json` (e.g., `"pnpm": { "overrides": { "<package>": "^<fixed>" } }`)
  - **npm**: `"overrides"` in `package.json`
- Run install command

**RUBY — Direct dependency:**
- Update version constraint in `Gemfile`
- Run `bundle update <package_name> --conservative`

**RUBY — Transitive dependency:**
- First identify the parent gem that introduces the vulnerable gem and try the smallest conservative update of that parent gem. Stay on the same major version unless a broader change is clearly required and approved.
- Re-check `Gemfile.lock` after the parent gem bump to verify whether the vulnerable transitive gem is gone or updated to a fixed version.
- Only if the parent gem update does not solve the issue safely, add a direct constraint for the vulnerable gem and run `bundle update <package_name> --conservative`.

**Install commands by package manager:**
- yarn: `yarn install`
- pnpm: `pnpm install`
- npm: `npm install`

#### Step 4: Verify compatibility

After applying ALL fixes for this repo:

1. **Check resolved versions** are correct:
    - yarn: `yarn why <package_name>`
    - pnpm: `pnpm why <package_name>`
    - npm: `npm explain <package_name>`
    - bundler: `grep '<package_name>' Gemfile.lock`

2. **Run lint/build** to ensure nothing breaks. Use the commands from workspace instructions for the specific repo or app. For `privacy-center` findings routed into `embeds`, validate with the privacy-center workspace commands such as `pnpm --filter privacy-center lint`, `pnpm --filter privacy-center typecheck`, and `pnpm --filter privacy-center build`.

3. **If a check fails:**
   - If the current approach was a direct dependency or parent dependency bump, decide whether a scoped override/resolution or direct constraint is the appropriate fallback
   - Try scoped resolutions instead of global ones
   - Or find the minimum compatible fixed version
   - Re-run verification
   - If still failing, document the issue and ask the user how to proceed

#### Step 5: Report results for this repo

After completing each repo, report:
- Which vulnerabilities were fixed
- What versions were resolved to
- Whether lint/build passed
- Any issues encountered

**Do NOT commit or push yet.** Leave the changes uncommitted so the user can review the diffs locally before proceeding.

**Version bump for SDK repos:** For `soyio-rn-sdk` and `soy-io-widget`, bump the `version` field in `package.json` (patch increment) as part of the fix. These are published packages, so the version must change for the fix to reach consumers.

### Phase 3: Commit, push, and create PRs (after user approval)

**Wait for the user to review the uncommitted changes and give explicit approval before committing, pushing, or creating PRs.** This is critical — the user needs to inspect the diffs while they are still uncommitted.

For each repo, once approved:

1. Stage only relevant files (repo root `package.json`, app `package.json`, lockfile, `Gemfile`, `Gemfile.lock`, as applicable)
2. Commit with message:
   - Single vulnerability: `fix(security): update <package> to <version> to fix <CVE>`
   - Multiple vulnerabilities: `fix(security): update vulnerable dependencies (<package1>, <package2>, ...)`
3. Push the branch:
   ```bash
   git push -u origin <branch_name>
   ```
4. Create a PR using `gh pr create`:

```bash
cd <workspace_root>/<repo_dir>
gh pr create --base <main_branch> --title "<title>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

**PR title format:**
- Single vulnerability: `fix(security): update <package> to fix <CVE>`
- Multiple vulnerabilities: `fix(security): update vulnerable dependencies`

**PR body** must be in Spanish and follow this structure:

```markdown
### Contexto

- <Why this change exists — reference CVEs and severity>

### Que se esta haciendo

- <Bullet points summarizing each fix>

### Verificacion

- <Lint/build results>
- <Version verification results>
```

Return all PR URLs to the user.

## Important Notes

- NEVER skip compatibility verification. A broken build is worse than a known vulnerability.
- Prefer updating the direct dependency or parent gem that introduces a vulnerable transitive package before adding overrides, resolutions, or direct constraints.
- When using resolutions/overrides, match the major version line of the vulnerable dependency. Do NOT jump major versions (e.g., 3.x vulnerable → resolve to 3.x fixed, not 9.x or 10.x).
- Use scoped resolutions when a global one would affect unrelated consumers on a different major version.
- Do NOT modify lockfiles manually — always use the package manager.
- NEVER delete and regenerate lockfiles from scratch (e.g., `rm pnpm-lock.yaml && pnpm install`). Always run the install command incrementally so the lockfile is updated in place.
- Process repos sequentially, not in parallel, to keep output readable.
- If a repo from the input does not exist in the workspace, stop immediately and ask the user to clone it before proceeding with any fixes. Do NOT skip it or continue with other repos.
- All PR content must be in Spanish.
- After all work is done (including PRs), `cd` back to the original working directory where the skill was invoked. The user's shell location must remain unchanged.
