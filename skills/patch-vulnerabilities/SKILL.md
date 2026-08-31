---
name: patch-vulnerabilities
description: >
  Invoke this skill for any recurring vulnerability management run: fetch open vulnerabilities
  from the Vanta API, fix OS packages (Aptfile.security-patches), Ruby gems (Gemfile), or npm
  dependencies, deactivate unfixable vulnerabilities in Vanta with a brief reason (auto-reactivate
  when a fix exists), open PRs for all code changes, and send a Slack summary to #vulnerabilidades.
  Use this skill whenever the user says "run vulnerabilities", "fix this week's vulns", "patch
  vulns", "parchear vulnerabilidades", or anything that sounds like a periodic vulnerability sweep.
  Does not apply to one-off CVE investigation, exploratory scans, or security audits.
---

# Patch Vulnerabilities

Recurring vulnerability management: fetch → fix → deactivate → PR → notify.

All vulnerability data comes from the **Vanta API** (no Notion). Reads and writes go
through the bundled helper script, which authenticates with `~/.vanta-credentials.json`.

> **Worktree rule (ALL repos, no exceptions).** Whenever you enter a repo to fix
> vulnerabilities, **always create a git worktree** and do every edit there. Never switch
> the user's checked-out branch and never touch their uncommitted work. This applies to
> every repo (soyio and all others), regardless of what branch the repo is currently on or
> whether it has WIP.
>
> - **No existing open PR (default):** branch from the latest `origin/main`.
> - **Existing open PR found (Phase 0b):** check out that PR's branch and merge
>   `origin/main` into it, so new fixes land on the same PR.
>
> ```bash
> # New branch (no existing PR):
> git -C <workspace_root>/soyio fetch origin && \
>   git -C <workspace_root>/soyio worktree add <ws>/.worktrees/soyio-patch-vulnerabilities-<YYYY-MM-DD> origin/main
> # Existing PR branch:
> git -C <workspace_root>/soyio fetch origin && \
>   git -C <workspace_root>/soyio worktree add <ws>/.worktrees/soyio-patch-vulnerabilities-<YYYY-MM-DD> origin/<existing-branch>
> # any other repo (generic git, new branch):
> git -C <ws>/<repo> fetch origin && \
>   git -C <ws>/<repo> worktree add <ws>/.worktrees/<repo>-patch-vulnerabilities-<YYYY-MM-DD> -b patch-vulnerabilities-<YYYY-MM-DD> origin/main
> ```
>
> Worktrees live under `<workspace_root>/.worktrees/` (outside each repo tree, so they
> never show up as untracked files). Remove them with `git -C <repo> worktree remove …`
> once the PR is open.

---

## Constants

- **Vanta API base:** `https://api.vanta.com`
- **Vanta credentials:** `~/.vanta-credentials.json` (`{ client_id, client_secret }`)
- **Helper script:** `~/.claude/skills/patch-vulnerabilities/scripts/vanta.py`
- **Slack channel:** `#vulnerabilidades` (ID: `C094H86AXFW`)
- **Workspace root:** `/Users/mmc/Desktop/soyio/`
- **soyio repo path:** `<workspace_root>/soyio`
- **soyio main branch:** `main`
- **Docker image:** `soyio-web:dev` (built from `products/soyio/compose.yaml`)

### Helper script usage

```bash
SCRIPT=~/.claude/skills/patch-vulnerabilities/scripts/vanta.py

# List active vulnerabilities (JSON), enriched with the resolved repo/registry/host:
python3 "$SCRIPT" list --pretty
python3 "$SCRIPT" list --severity HIGH --sla-before 2026-06-30

# Deactivate unfixable vulns (one call, many ids). Auto-reactivates when fixable by default:
python3 "$SCRIPT" deactivate --reason "No hay fix disponible en Debian Trixie" --id <id1> --id <id2>

# Reactivate (undo / testing):
python3 "$SCRIPT" reactivate --id <id1>
```

Each `list` record includes: `id`, `cve`, `package`, `severity`, `source`
(`aws`|`github`|`gcp`), `assetType` (`CODE_REPOSITORY`|`CONTAINER_REPOSITORY`|`SERVER`),
`assetName`, `repo`, `registry`, `registryAccount`, `assetResolved`, `isFixable`,
`fixedVersion`, `remediateByDate`, `isDeactivated`, `externalURL`, `relatedUrls`.

---

## Phase 0 — Sync repos

Before making any changes, pull the latest `main` in every repo that may be touched. Stale local state causes merge conflicts when the PR branch is behind.

```bash
cd <workspace_root>/soyio && git checkout main && git pull origin main
```

Repeat for any other repo identified during Phase 1 (e.g. `prisma`, `soyio-embeds`). For repos where work will happen on a new branch (not a worktree), pull main **before** creating the branch. For soyio worktrees, `bin/soyio worktree add` already branches from the current HEAD, so pulling main first ensures the worktree starts from the latest commit.

---

## Phase 0b — Check for existing open PRs

Before fixing anything, check whether a previous run already has an open PR for each repo
that may be touched. This avoids creating duplicate PRs when a prior run's PR hasn't been
merged yet.

```bash
# For each repo that may receive fixes (determined after Phase 1 categorization,
# but query early so the information is ready).
# IMPORTANT: --head requires an EXACT branch name — it does NOT support prefix/glob
# matching. Use --search instead to find any open PR whose branch starts with the
# patch-vulnerabilities prefix:
gh pr list --repo Soyio-id/soyio --state open \
  --search "head:patch-vulnerabilities-" \
  --json number,title,headRefName,url
# Repeat for other repos (e.g. Soyio-id/agents, Soyio-id/soyio-embeds)
```

For each repo with an open PR:

1. **Record** the PR's `headRefName` (branch name), `url`, and `number`.
2. **Inspect what the existing PR already fixes.** Diff the PR branch against `main` to
   see which files changed and which packages were bumped:
   ```bash
   gh pr diff <number> --repo Soyio-id/<repo> --name-only
   # Then inspect specific files:
   git diff origin/main..origin/<headRefName> -- products/soyio/Aptfile.security-patches
   git diff origin/main..origin/<headRefName> -- products/soyio/package.json
   git diff origin/main..origin/<headRefName> -- products/soyio/Gemfile
   ```
3. **Build a "already addressed" set** of CVE+package combinations from the diff. A fix
   is "already addressed" if:
   - An OS package is already present in the PR's `Aptfile.security-patches` diff
   - A gem version bump already appears in the PR's `Gemfile` / `Gemfile.lock` diff
   - An npm resolution/dependency bump already appears in `package.json` / lockfile diff
   - A default-gem entry already appears in the PR's `Gemfile.default-gems` diff
4. In Phase 3, **skip fixes that are already addressed** — only apply what's new.
5. In Phase 5, **push to the existing branch** instead of creating a new PR (see below).

If **no open PR exists** for a repo → proceed normally (new branch, new PR).

---

## Phase 1 — Fetch & categorize

1. Fetch active vulnerabilities from Vanta (already excludes deactivated ones).
   **Default scan window = up to one week ahead:** only pull findings whose SLA is overdue
   or falls within the next 7 days, by passing `--sla-before` = today + 7 days:
   ```bash
   python3 ~/.claude/skills/patch-vulnerabilities/scripts/vanta.py list --pretty \
     --sla-before "$(date -u -v+7d +%Y-%m-%d 2>/dev/null || date -u -d '+7 days' +%Y-%m-%d)"
   ```
   - This focuses each recurring run on what's due this week. If the user asks for a wider
     range, pass a later `--sla-before` (or omit it to scan everything).
   - Deactivated and fixed vulns are already excluded (fixed ones drop off on rescan).

2. **Deduplicate:** same `cve` + same `package` + same resolved repo/asset → one entry.
   Vanta emits one vulnerability per asset, so a CVE can appear many times. Keep the full
   list of `id`s for each unique entry — a single deactivate call covers all of them.

3. **Route each vulnerability by `assetType`** (this replaces the old Notion source field
   and card title):

   - **`CODE_REPOSITORY`** (`source: github`) → the repo in `repo` (`org/name`). Map the
     `name` to a local repo dir, applying aliases:
     `soyio-docs-bot-action` → `soyio-docs-bot`; `soyio-docs-indexer-action` → `soyio-docs-bot`;
     `privacy-center` → `soyio-embeds`.
     The following repos map directly to their directory name under `<workspace_root>`:
     `agents` → `agents` (pnpm, standalone repo — not part of the soyio monorepo);
     `soyio-lambdas` → `soyio-lambdas` (Go, standalone repo — AWS Lambda functions).
     Determine package type from `package`:
     `npm-…` → npm, `rubygems-…` → ruby gem, `go-…` → go module.
     **If the repo dir is absent under `<workspace_root>` → uncorrelated** (do not fix/deactivate).

     **Manifest resolution (monorepo-aware).** The `soyio` repo is a monorepo with
     multiple independent lockfiles and Gemfiles across `products/`, `sdks/`, `packages/`,
     and `docs/`. A CODE_REPOSITORY finding only tells you the *repo*, not *which manifest
     inside the repo* is vulnerable. To find the exact file:

     1. Extract the Dependabot alert number from `externalURL` (the trailing integer in
        `…/dependabot/<number>`).
     2. Query the GitHub API for the manifest path:
        ```bash
        gh api repos/<org>/<repo>/dependabot/alerts/<number> \
          --jq '.dependency.manifest_path'
        ```
     3. Record the returned path (e.g. `sdks/soyio-widget/package.json`,
        `sdks/soyio-rn-sdk/example/app/Gemfile.lock`, `products/soyio/yarn.lock`).
        This is the file you must check and fix — **not** the monolith's lockfile.

     Batch all Dependabot API calls for efficiency. When the same CVE + package appears in
     multiple manifests, each manifest is a separate fix target.

     **Critical:** never assume a CODE_REPOSITORY vulnerability lives in `products/soyio/`.
     Always resolve the manifest path first and verify the version in *that specific file*.

   - **`CONTAINER_REPOSITORY`** (`source: aws`/`gcp`) → look up `assetName` in this
     container → monorepo-part mapping table. The following are **in monorepo scope** —
     never treat them as uncorrelated:
     - `soyio/soyio-fargate` → `soyio` monolith (Rails, Debian Trixie).
     - `soyio-production` → `soyio` monolith (the **production environment** of the Rails
       `soyio` image; same codebase/image as fargate, different env).
     - `soyio/soyio-mcp-server` → `packages/soyio-mcp-server` in the `soyio` monorepo
       (Node.js, Debian Bookworm). Package type is always `npm` (no OS-level patching;
       the Dockerfile only installs `libgnutls30` as a one-off apt upgrade).

     For the monolith containers (`soyio/soyio-fargate`, `soyio-production`):
     dpkg-style `package` (`libxml2:…`, `openssl`, …) → `os_package`;
     ruby-ecosystem name or found in `Gemfile.lock` → `ruby_gem`; `npm-…` → npm.
     - Any *other* container repo not listed above → **uncorrelated**.

   - **`SERVER`** (`source: aws` — EC2 hosts, Elastic Beanstalk autoscaling groups,
     Twingate instances, etc.) → **always uncorrelated**. These are host-level OS findings
     with no repo/monorepo part to patch; never fix or deactivate them here.

4. **Present three buckets to the user before making any changes:**
   - **Fixable** — grouped by fix type (`os_package` / `ruby_gem` / `npm`) and repo.
   - **Unfixable** — will be deactivated in Vanta (Phase 4).
   - **Uncorrelated** — not tied to any repo/monorepo part (SERVER hosts, unmapped
     container repos, github repos not present locally). Never fixed or deactivated —
     reported in the Slack summary (Phase 6) so a human addresses them.
     - **SLA warning:** because these are skipped, explicitly **warn about any whose SLA
       is overdue or approaching**. The helper's `list` output includes `daysUntilSla` and
       `slaDueSoon` (true when overdue or within 14 days). Surface the `slaDueSoon` ones
       first — with `daysUntilSla` and severity — both when presenting to the user and in
       the Slack summary, so the owner can act before the deadline.

---

## Phase 2 — Check fixability

Vanta's `isFixable` / `fixedVersion` fields are a strong first signal, but confirm against
the ecosystem source before fixing:

### OS packages (Debian Trixie)
Fetch `https://security-tracker.debian.org/tracker/<CVE>`. If a fixed version exists for `trixie` → **fixable**. Otherwise → **unfixable**, go to Phase 4.

### Ruby gems
Check the installed version **in the specific `Gemfile.lock` identified by the manifest
path** (Phase 1), then look up the patched version on rubygems.org or the CVE advisory. If
a fix exists → **fixable**. Pay attention to major-version constraints — the same gem may
be at a safe version in one Gemfile and at a vulnerable version in another (e.g.
`products/soyio/Gemfile.lock` may have `activesupport 8.0.5` while
`sdks/soyio-rn-sdk/example/app/Gemfile.lock` has `activesupport 7.0.10`). Each manifest
is checked independently.

### npm packages
Check `package.json` + run `yarn why` / `pnpm why` **in the directory of the manifest
identified in Phase 1** to understand the dep tree. A package may already be fixed in one
workspace package but still vulnerable in another (e.g. `vite 7.3.2` in
`products/soyio/yarn.lock` but `vite 7.2.6` in `sdks/soyio-widget/package.json`). Look up
the patched version upstream. If a fix exists → **fixable**.

### Persistent CONTAINER_REPOSITORY findings ("already fixed in code")

When a container vulnerability keeps reappearing in Vanta despite the `Gemfile.lock`,
`package-lock.json`, or `pnpm-lock.yaml` already showing the patched version on `main`
(and deployments having happened), the vulnerability **is not in your code** — it's in the
Docker image itself. Use AWS Inspector to identify the actual source:

```bash
aws inspector2 list-findings \
  --filter-criteria '{
    "resourceType":[{"comparison":"EQUALS","value":"AWS_ECR_CONTAINER_IMAGE"}],
    "title":[{"comparison":"PREFIX","value":"<CVE>"}]
  }' \
  --query 'findings[0].packageVulnerabilityDetails.vulnerablePackages[*].{filePath:filePath,version:version}' \
  --output json
```

The `filePath` in each vulnerable package entry reveals the true source. Common root causes:

1. **Stale default gems from the Ruby base image.** The `ruby:3.4` image ships default
   gems (e.g. `net-imap`, `rexml`) at the version that was current when that Ruby minor
   was released. `bundle install` installs the newer version **alongside** the old one —
   the old files persist at `/usr/local/lib/ruby/gems/3.4.0/gems/<gem>-<old-version>` and
   Inspector keeps flagging them. **`gem update` does NOT fix this** — it also installs
   alongside. Only `gem uninstall` removes the old version.
   → Fix via `Gemfile.default-gems` (see Phase 3d).

2. **Nested lockfiles inside installed gems.** Some gems ship their own `Gemfile.lock` or
   `package-lock.json` as development artifacts (e.g.
   `/usr/local/bundle/gems/safety_net_attestation-0.5.0/Gemfile.lock` referencing an old
   `json` version). Inspector reads these nested lockfiles and flags them even though they
   have no effect on the runtime dependency tree.
   → Fix by deleting nested lockfiles in the Dockerfile (the production Dockerfile already
   runs `find /usr/local/bundle/gems -name 'Gemfile.lock' -delete` after `bundle install`).
   For npm equivalents, add the path to `FalsePositivefile`.

3. **Old images still in ECR.** Inspector scans all images in a repository, not just the
   latest tag. Findings from older images keep appearing in Vanta. These are not actionable
   from the code side — they clear when old images are cleaned up or when an ECR lifecycle
   policy removes them. If the **latest** image (check the image tag/hash) is clean, the
   finding is stale and will eventually resolve.

**Investigation checklist** for a container finding that looks fixed:
1. Confirm the fix is on `origin/production` (not just `main`) — check the specific file.
2. Query Inspector for the finding's `filePath` to see where the vulnerable version lives.
3. If `filePath` is a base-image default gem path → Phase 3d.
4. If `filePath` is a nested lockfile inside a bundle gem → Dockerfile cleanup.
5. If the finding only appears on old image hashes → stale ECR image, not actionable.

---

## Phase 3a — Fix OS packages

1. Create the soyio worktree. If Phase 0b found an **existing open PR** for this repo,
   check out that PR's branch so new fixes land on the same branch:
   ```bash
   git -C <workspace_root>/soyio worktree add \
     <ws>/.worktrees/soyio-patch-vulnerabilities-<YYYY-MM-DD> origin/<existing-branch>
   ```
   Then merge latest main into it to avoid conflicts:
   ```bash
   cd <ws>/.worktrees/soyio-patch-vulnerabilities-<YYYY-MM-DD>
   git merge origin/main --no-edit
   ```
   If there is **no existing PR**, create a fresh worktree from `origin/main` as usual
   (see the **Worktree rule** above).
   All file edits live inside that worktree, never in the user's checkout.

2. Resolve the **exact installed package name** — Debian Trixie uses `t64` suffixes:
   ```bash
   docker run --rm soyio-web:dev dpkg -l | grep -i <package-stem>
   ```
   Use the actual name (e.g. `libssl3t64`, not `libssl3`). If not installed at all → skip this entry (it's a no-op).

3. Append the confirmed name to `products/soyio/Aptfile.security-patches` (one per line).

4. **Audit all existing entries** while the image is available:
   ```bash
   docker run --rm soyio-web:dev dpkg -l <entry1> <entry2> ...
   ```
   Remove any showing `un` (unknown/not installed) — they are no-ops.

5. **Build & verify** (mandatory — never skip):
   ```bash
   cd .worktrees/patch-vulnerabilities-<YYYY-MM-DD>/products/soyio
   docker compose build web
   docker run --rm soyio-web:dev dpkg -l <patched-packages>
   ```
   Confirm each package shows `ii` status and version ≥ the fixed version.

---

## Phase 3b — Fix Ruby gems

1. Use the same worktree (create one if 3a was skipped).

2. Identify the target `Gemfile` from the manifest path resolved in Phase 1. This may be
   `products/soyio/Gemfile` (the monolith), or another Gemfile elsewhere in the monorepo
   (e.g. `sdks/soyio-rn-sdk/example/app/Gemfile`). All edits go in the target Gemfile.

3. Add or update a direct constraint in the target Gemfile, maintaining **alphabetical
   order** (`Bundler/OrderedGems` lint rule applies to `products/soyio/Gemfile`):
   ```ruby
   gem "<gem-name>", ">= <fixed-version>"
   ```
   If the Gemfile already pins the gem with an upper-bound constraint that excludes the
   fixed version (e.g. `'>= 6.1.7.5', '< 7.1.0'` when the fix requires `7.2.3.1`),
   widen or remove the upper bound. Check whether the constraint exists for a known
   compatibility reason (comments, CocoaPods version locks) and note the change in the
   PR body.

4. Run `bundle update <gem-name>` inside the directory containing the target Gemfile.

5. Verify: `grep '<gem-name>' <target-dir>/Gemfile.lock` shows version ≥ fixed.

---

## Phase 3c — Fix npm packages

1. Create a worktree for the target repo. If Phase 0b found an **existing open PR** for
   this repo, check out that PR's branch and merge latest main (same approach as Phase 3a
   step 1). Otherwise create a fresh worktree from `origin/main` (see the **Worktree
   rule** above). Never switch the user's branch or touch their WIP.

2. Identify the target `package.json` from the manifest path resolved in Phase 1. In the
   `soyio` monorepo this may be `products/soyio/package.json` (yarn, monolith frontend),
   `sdks/soyio-widget/package.json` (pnpm workspace), `packages/soyio-mcp-server/package.json`
   (pnpm workspace), or any other workspace package. Use the correct package manager for
   the target directory (`yarn` for `products/soyio/`, `pnpm` for everything else in the
   monorepo root workspace).

3. Analyze the dep tree (`yarn why` / `pnpm why` / `npm explain`) **in the target
   directory**, then apply the fix:
   - **Direct dep:** update version specifier in the target `package.json` + install
   - **Transitive dep:** bump parent first; only add a resolution/override if necessary
   - **Never jump major versions** when pinning (e.g. vulnerable `< 3.1.3` → resolve to `^3.1.3`, not `^9.x`)

4. Run lint/build to confirm nothing breaks.

5. **Version bump for publishable SDKs.** `sdks/soyio-widget` and `sdks/soyio-rn-sdk`
   are publishable packages — any dependency change that touches their `package.json`
   (or their source/build files) **must** include a patch version bump in the same PR.
   The only exception is changes scoped entirely to smoke/example apps (e.g.
   `sdks/soyio-rn-sdk/example/`), which are not published and do not need a bump.
   This also applies when these SDKs lived in standalone repos (`soy-io-widget`,
   `soyio-rn-sdk`).

---

## Phase 3d — Fix stale default gems from the base Docker image

When Inspector flags a Ruby gem at a path like
`/usr/local/lib/ruby/gems/3.4.0/gems/<gem>-<old-version>`, the vulnerability is in the
**base `ruby:3.4` image's default gems**, not in the application's `Gemfile.lock`. These
persist on disk even after `bundle install` installs the correct version.

1. Use the same soyio worktree (create one if previous phases were skipped).

2. Append the gem and a version constraint to `products/soyio/Gemfile.default-gems` (one
   entry per line, format: `gem_name version_constraint`):
   ```
   net-imap < 0.6.4
   ```
   The constraint should match all vulnerable versions from the base image. Use `< <fixed>`
   as the standard pattern.

3. Both `Dockerfile` and `Dockerfile.production` already loop over this file after
   `bundle install`:
   ```dockerfile
   RUN while IFS=' ' read -r gem version; do \
         gem uninstall -i /usr/local/lib/ruby/gems/3.4.0 "$gem" --version "$version" -aIx || true; \
       done < Gemfile.default-gems
   ```
   No Dockerfile edits are needed — just adding the line to the file is enough.

4. **Build & verify** (mandatory):
   ```bash
   cd .worktrees/patch-vulnerabilities-<YYYY-MM-DD>/products/soyio
   docker compose build web
   docker run --rm soyio-web:dev bash -c \
     'ls /usr/local/lib/ruby/gems/3.4.0/gems/ | grep <gem> || echo "(removed)"; gem list <gem>'
   ```
   Confirm the old version is gone from the default gems directory and only the safe
   version remains.

**Pattern files summary** — the soyio Docker build uses four declarative files for
security-related image hygiene:

| File | Purpose | Consumed by |
|---|---|---|
| `Aptfile.security-patches` | OS packages to upgrade | `apt install --only-upgrade` |
| `Gemfile.default-gems` | Base-image default gems to uninstall | `gem uninstall` loop |
| `FalsePositivefile` | Paths to delete (scanner false positives) | `xargs rm -f` |
| `Gemfile` / `Gemfile.lock` | Application Ruby dependencies | `bundle install` |

---

## Phase 3e — Fix Go module vulnerabilities

1. Create a worktree for the target Go repo. If Phase 0b found an **existing open PR**,
   check out that PR's branch and merge latest main (same approach as Phase 3a step 1).
   Otherwise create a fresh worktree from `origin/main` (see the **Worktree rule** above).

2. Identify the target `go.mod` from the manifest path resolved in Phase 1 (or by
   searching for `go.mod` files in the repo). For single-module repos the path is the repo
   root; for multi-module repos each `go.mod` is independent.

3. Update the dependency:
   ```bash
   cd <worktree>/<path-to-go.mod-dir>
   go get <module>@v<fixed-version>
   go mod tidy
   ```
   If the fixed version is a minimum (e.g. `>= 0.52.0`), use `@latest` or `@v<specific>`
   to land on the latest compatible version.

4. Verify: `grep '<module>' go.mod` shows version ≥ fixed. Also check `go.sum` was updated.

5. Run `go build ./...` to confirm the module compiles cleanly.

---

## Phase 4 — Deactivate unfixable vulnerabilities in Vanta

For every **unfixable** CVE, collect **all** of its vulnerability `id`s (every duplicate
across assets, from the deduped entry in Phase 1) and deactivate them in one call:

```bash
python3 ~/.claude/skills/patch-vulnerabilities/scripts/vanta.py deactivate \
  --reason "<brief one-sentence Spanish reason>" \
  --id <id1> --id <id2> --id <id3>
```

- **Reason** — keep it **brief** (one Spanish sentence). Example:
  *"No hay fix disponible en Debian Trixie"*.
- **Reactivate-when-fixable is ON by default** — this is the direct equivalent of the old
  "Reactivar cuando exista Fix" policy: Vanta automatically reopens the vulnerability when
  a fix becomes available. Only pass `--no-reactivate-when-fixable` if the user explicitly
  wants a permanent suppression.
- Deactivating in Vanta both records the reason and suppresses the finding — it replaces
  the old Notion `[Desactivación]` fields entirely.
- **Never deactivate uncorrelated vulnerabilities** (SERVER hosts / unmapped assets) — only
  report them in Slack.

The command exits non-zero if Vanta reports any per-item error; re-check those ids.

---

## Phase 5 — Commit & open PRs (after user approval)

### When an existing open PR was found (Phase 0b)

If the worktree is on an existing PR branch (from Phase 0b), check whether this run
actually produced any new commits beyond what the branch already had:

```bash
cd .worktrees/patch-vulnerabilities-<YYYY-MM-DD>
git diff origin/<existing-branch> --stat
```

- **No new changes** → all fixes were already addressed in the existing PR. Skip the
  commit/push. Reference the existing PR URL in the Slack summary and note that no
  additional fixes were needed.
- **New changes exist** → commit and push to the existing branch:
  ```bash
  git add <changed-files>
  git commit -m "chore(security): add fixes for <new CVEs>"
  git push origin HEAD:<existing-branch>
  ```
  The existing PR updates automatically. In the Slack summary, reference the existing PR
  URL and note that it was updated with additional fixes.
  If the push is rejected (e.g. because `main` was merged in and the histories diverged),
  use `git push --force-with-lease` — patch-vulnerabilities branches are automation-owned
  and safe to force-push.

**Do NOT create a new PR when an open one already exists for the same repo.**

### When no existing PR was found (new PR)

**soyio worktree:**
```bash
cd .worktrees/patch-vulnerabilities-<YYYY-MM-DD>
git add products/soyio/Aptfile.security-patches products/soyio/Gemfile products/soyio/Gemfile.lock
git commit -m "chore(security): <summary of CVEs fixed>"
git push -u origin patch-vulnerabilities-<YYYY-MM-DD>
gh pr create --base main --title "chore(security): <summary>" --body "$(cat <<'EOF'
### Contexto
- <CVEs y severidad>

### Qué se está haciendo
- <Bullet points por fix>

### Verificación
- <Build/lint results>
- <Version verification>
EOF
)"
```

**npm repos:** same `gh pr create` pattern with Spanish body, targeting `main`.

---

## Phase 6 — Slack summary

Send one message to `#vulnerabilidades` (channel ID: `C094H86AXFW`) after all PRs are open. Write in Spanish, keep it concise. Cover these sections (omit any that has no items):

**✅ Vulnerabilidades corregidas**
- `<package>` — `<CVE>` — PR: `<link>`
- `<package>` — `<CVE>` — PR: `<link>` (actualizado, PR existente)

Use "(actualizado, PR existente)" when fixes were pushed to an existing PR from a prior run.
Use "(sin cambios, PR existente)" when the existing PR already covered the fix.

**🏷️ Sin fix disponible (desactivadas en Vanta)**
- `<package>` — `<CVE>` — razón: "No hay fix disponible en Debian Trixie"

**❓ Sin repo asociado / fuera del monorepo**

Mention **every uncorrelated finding from this run's scan** (the one-week-ahead window). How
to render this section depends on volume:

- **Few items (≤ 15):** list each one —
  `<CVE>` — `<package>` — activo: `<assetName>` (`<registry o host>`) — severidad: `<severity>` — vence en `<daysUntilSla>` días
- **Many items (> 15):** don't enumerate all — write a **summary** instead:
  - a one-line total with a severity breakdown (e.g. "47 hallazgos: 6 CRITICAL, 18 HIGH, 23 MEDIUM"),
  - counts grouped by asset/host (e.g. `soyio-production: 23`, `awseb …: 12`, `twingate …: 8`),
  - then list only the **most urgent few** explicitly (overdue + CRITICAL/HIGH, sorted by `daysUntilSla`).

The total count must always be stated so nothing is silently dropped.

The section is mandatory whenever the scan has uncorrelated vulnerabilities (SERVER hosts,
unmapped container repos, or github repos missing locally). These are never fixed or
deactivated automatically, so the **whole set from this run must be surfaced here** (listed
or summarized) for a human to address — and any with an overdue/approaching SLA
(`slaDueSoon`) must be called out first, sorted most-urgent first.

---

## Phase 6b — dev-flash-reviews notification

After the `#vulnerabilidades` summary, post a short message to `#dev-flash-reviews`
(channel ID: `C07P8RD2FLK`) so the PRs get reviewed quickly.

**Only post if this run produced at least one PR.** Skip this phase when all findings were
already resolved, deactivated, or uncorrelated (i.e. no PRs to review).

Format — match the channel's existing style:

```
Vulnerabilidades
• <repo> (<short package list>) — <PR link>
• <repo> (<short package list>) — <PR link>
```

- First line is the bare word **Vulnerabilidades** (no emoji, no bold).
- One bullet per PR. Repo is the short name (e.g. `soyio`, `prisma`, `soyio-web-demo`).
- Package list is a parenthetical with the affected package names, comma-separated.
  Abbreviate if many (e.g. `vitest, vite, …`).
- Link is the full PR URL.

---

## Key rules

- **Monorepo manifest resolution is mandatory.** For every CODE_REPOSITORY finding in the
  `soyio` monorepo, resolve the Dependabot alert's `manifest_path` via the GitHub API
  before checking or fixing. Never assume a vulnerability lives in `products/soyio/` — the
  monorepo has independent lockfiles in `sdks/`, `packages/`, `docs/`, and elsewhere. A
  vulnerability "already fixed" in the monolith may still be open in another workspace
  package.
- **Always** work in a fresh worktree off the latest `origin/main` for every repo — never
  switch the user's checked-out branch or disturb their uncommitted work
- Always resolve the exact Debian package name (`t64` suffix) before editing Aptfile
- Always audit all existing Aptfile entries for no-ops when adding new ones
- Always build + verify the Docker image after any Aptfile change — never skip this
- **Bump publishable SDK versions.** When fixing a dependency in `sdks/soyio-widget` or
  `sdks/soyio-rn-sdk` (or their standalone-repo equivalents), always patch-bump the
  `version` field in `package.json` — these are published packages and consumers need a
  new release to pick up the fix. Skip the bump only for changes scoped entirely to
  smoke/example apps (e.g. `sdks/soyio-rn-sdk/example/`)
- Gemfile entries must be alphabetically ordered (`Bundler/OrderedGems` lint rule)
- Deactivate unfixable vulns in Vanta with a short reason; keep reactivate-when-fixable ON
- Process **all duplicate ids** per CVE in a single deactivate call (Vanta emits one per asset)
- A vulnerability that cannot be tied to a repo or monorepo part (`SERVER` hosts, unmapped
  container repos, github repos not present locally) is **never fixed or deactivated** — it
  must appear in the Slack "Sin repo asociado" section so a human addresses it
- **Warn on approaching SLAs for skipped (uncorrelated) findings** — any with `slaDueSoon`
  (overdue or within 14 days) must be flagged explicitly to the user and in the Slack
  ⚠️ section, since nothing else will act on them automatically
- **Investigate persistent container findings.** If a CONTAINER_REPOSITORY vulnerability
  keeps appearing despite the codebase having the patched version, do NOT assume it will
  clear on the next deploy. Query AWS Inspector for the finding's `filePath` — the root
  cause is usually a stale default gem from the base Docker image or a nested lockfile
  inside an installed gem. Fix via `Gemfile.default-gems` (default gems) or
  `FalsePositivefile` / Dockerfile cleanup (nested lockfiles). See Phase 2 investigation
  checklist and Phase 3d for details.
- **Never create duplicate PRs.** Before creating a worktree or branch, check for existing
  open `patch-vulnerabilities-*` PRs (Phase 0b). If one exists for the target repo, reuse
  its branch — push new commits to it and let the existing PR update. Only create a new PR
  when no open one exists. This prevents duplicate PRs when a prior run's PR hasn't been
  merged yet.
