# dev → main Rollout Plan: v1.0.0

**Status:** Planned, not executed (user chose "hold off" on 2026-08-26 — this document is the reference for when they're ready).

## Situation

`main` has not been touched since **v0.12.24** (2026-08-09, commit `9aa2de4f`). Since then,
`dev` has accumulated **203 commits / 4363 changed files**, including:

- The entire **v1.0.0 release**: RBAC flipped from decorative (every session hardcoded admin)
  to actually enforced, OAuth login (Authentik/Google/GitHub) with a signup allowlist, TOTP
  2FA + backup codes, a full login-page redesign, native Discord/Apprise webhooks wired to
  real activity.
- The **#392 security sweep**: ~150 commits adding authentication to FastAPI routes that
  previously had none (artists, videos, thumbnails, scheduler, playlists, health,
  performance, maintenance, personal insights, etc.).
- ~50 further bug fixes, cleanups, and dependency bumps, most recently the two dashboard
  "Download All Wanted" fixes (PRs #476, #477).

`version.json` and `CLAUDE.md` on `dev` already claim **v1.0.0 was "Released 2026-08-17."**
That's not true yet — no `v1.0.0` git tag exists anywhere, and none of this has reached
`main`. This rollout is what actually makes that claim true.

**Why this can't be incremental:** every commit since v0.12.24 is built on top of the auth
rewrite. Cherry-picking a subset is not realistic — it's the full backlog in one merge, or
nothing.

## What's actually risky vs. not

| Item | Risk | Notes |
|---|---|---|
| RBAC enforcement flip | **Real** | Any client currently relying on "everyone is effectively admin" behavior breaks. This is the point of the change, but it's the one thing that can surprise someone post-merge. |
| #392 auth sweep (~150 routes) | **Real** | Previously-open routes now require a session. Anything hitting those routes without auth (scripts, health checks, monitoring) will start getting 401s. |
| 2 new DB migrations (024, 025) | Low | Small, additive (`youtube_id` unique constraint + redundant index cleanup). Migration 024 has a documented pre-flight check for duplicate `youtube_id` values and refuses to start if any exist. |
| Dependency bumps | Low | `requirements.txt`/`requirements-fastapi.txt`/`requirements-dev.txt` — minor version bumps, nothing unusual for this repo's cadence. |
| 208 tracked MariaDB data files under `volumes/` | **None — this is a fix** | `main` has raw database files accidentally committed to git; `dev` already added a `.gitignore` rule and dropped them. The huge deletion count in the diffstat is this cleanup, not something to worry about. |
| `main`'s own commits since v0.12.24 | None | Only doc/version-bump commits (README, CLAUDE.md, `version.json`) from the historical release process — no code divergence. `dev`'s docs supersede them. |

`main` is branch-protected: PR required, 1 approving review, and required status checks
(`build`, `test (3.11)`, `test (3.12)`, `security`) must pass. No direct push — this has to
go through a real PR.

## Phase 0 — Safety net

1. Tag current `main` tip as an instant rollback point before touching anything:
   ```bash
   git tag pre-v1.0.0-rollout origin/main
   git push origin pre-v1.0.0-rollout
   ```
2. Confirm `dev`'s tip is green (already true as of PR #477 — CI/CD Pipeline and Build and
   Push Docker Image both passed). Re-check immediately before starting in case anything
   landed on `dev` since.

## Phase 1 — Prepare the merge branch

```bash
git checkout main && git pull origin main
git checkout -b release/v1.0.0-dev-merge
git merge origin/dev --no-ff -m "chore: merge dev into main for v1.0.0 rollout"
```

Expect **no code conflicts** (main has no divergent code, only doc/version commits). Expect
conflicts in exactly these files, because both branches independently touched them:

- `version.json`
- `CLAUDE.md`
- `README.md`
- `CHANGELOG.md`

Resolve all four by taking `dev`'s version outright — `dev`'s copies are newer and
authoritative. `version.json` and the doc files get corrected properly in Phase 3 anyway.

```bash
git checkout --theirs version.json CLAUDE.md README.md CHANGELOG.md
git add version.json CLAUDE.md README.md CHANGELOG.md
git commit
```

## Phase 2 — Pre-PR validation

Run the same gates used for every fix this cycle, on the merged result:

```bash
~/.local/bin/black --check src/
~/.local/bin/isort --profile black --check-only src/
pytest tests/unit -q
```

All three must be clean before opening the PR — required status checks will re-run these
anyway, but catching a failure locally is faster than iterating through CI.

## Phase 3 — Release housekeeping (on the merge branch, before opening the PR)

`CHANGELOG.md`'s `[Unreleased]` section is stale — it only has migration 024's entry, not a
summary of the whole v1.0.0 backlog. Before tagging this as a real release:

1. Rewrite `CHANGELOG.md`'s `[Unreleased]` section into a proper `## [1.0.0] - 2026-08-26`
   entry, summarizing the major pieces (RBAC enforcement, OAuth/2FA, webhooks, #392 auth
   sweep, dashboard fixes) — not a raw 203-commit dump. Use the "v1.0.0" bullet list already
   in `CLAUDE.md`'s Version History section as the source of truth for what to include.
2. Update `version.json` for real (this is what `./scripts/update_version.sh` does, but the
   version number itself needs a manual bump since the script preserves the existing one):
   ```bash
   ./scripts/update_version.sh   # refreshes git_commit/build_date
   # then manually confirm version.json's "version" field reads "1.0.0"
   # and "git_branch" reads "main"
   ```
3. Confirm `CLAUDE.md`'s "Current Version"/"Next Version" lines read `1.0.0` / `1.0.1` (they
   already do on `dev` — just verify they survived the merge).
4. Commit: `git commit -am "docs: finalize v1.0.0 release notes and version metadata"`.

## Phase 4 — Open and merge the PR

```bash
git push -u origin release/v1.0.0-dev-merge
gh pr create --base main --head release/v1.0.0-dev-merge \
  --title "release: v1.0.0 — auth rewrite, RBAC enforcement, OAuth/2FA, security sweep" \
  --body "..."   # summarize the major pieces; link the v1.0.0 GitHub milestone
```

Wait for all four required checks (`build`, `test (3.11)`, `test (3.12)`, `security`) to go
green, then get the required approving review. Merge with a real merge commit (not squash —
this is 203 commits of individually-meaningful history worth keeping, matching the repo's
existing merge-commit convention for dev→main releases).

## Phase 5 — Tag and release

Once merged:

```bash
git checkout main && git pull origin main
git tag -a v1.0.0 -m "v1.0.0 - First Production-Ready Release"
git push origin v1.0.0
```

Pushing the tag triggers `.github/workflows/release.yml`, which generates release notes from
the commit range and publishes a GitHub Release automatically.

## Phase 6 — Post-merge verification

1. Confirm `.github/workflows/ci-cd.yml`'s push-to-`main` run is green (test + build +
   security jobs).
2. Confirm the GitHub Release was created by `release.yml` and its auto-generated notes look
   sane.
3. Spot-check that the RBAC/auth behavior change is understood and expected — this is the one
   change in this release with real behavioral impact (Phase "What's actually risky" above).
4. **Prod deploy is a separate, manual step**, not automated by any workflow here — per your
   own environment notes, 192.168.1.68:5050 is a manual Docker deploy. This plan stops at
   "main has v1.0.0 tagged and released"; deploying it to prod is a distinct decision to make
   later, not part of this rollout.

## Rollback

If anything goes wrong post-merge before a prod deploy happens, `main` can be reset to the
Phase 0 tag:

```bash
git checkout main
git reset --hard pre-v1.0.0-rollout
git push --force-with-lease origin main   # only if truly necessary; branch protection may block this
```

Branch protection disallows force-push by default — reverting via a new PR that reverts the
merge commit is the safer path if `main` has already moved on.
