# Release process

No formal releases yet — see [TODO.md](TODO.md) P0/P1 for CI/CD gaps. Until that exists, this is the manual process.

## Branching

- `main` — stable, matches what's deployed.
- `docs/...`, `fix/...`, `feat/...`, `chore/...`, `security/...` — work branches.
- `wip/...` — interrupted-session recovery branches (see CLAUDE.md).

## Versioning

No version currently tracked (pre-1.0, no `package.json`/`pyproject.toml` version field found). If versioning is introduced: `0.1.0` as a starting point, Semantic Versioning after that (MAJOR = incompatible change, MINOR = backward-compatible feature, PATCH = backward-compatible fix). Do not label this project `1.0.0` — it hasn't gone through a stabilization/release process that would justify it.

## Before any change reaches production

1. Edit in this repo, on a work branch.
2. Manually verify per [TESTING.md](TESTING.md)'s checklist (no automated gate exists).
3. Commit with a clear message (Conventional Commits style: `fix:`, `feat:`, `docs:`, `chore:`, `security:`).
4. Update `docs/CHANGELOG.md`, `docs/PROJECT_STATE.md`, `docs/SESSION_HANDOFF.md`, and `docs/FEATURES.md` if the change affects feature status.
5. Sync the changed file(s) to the VPS (`scp`/`rsync` to `/var/www/miniapp/` for frontend, `/home/promonta/agent/miniapp/` for backend) — **after** first copying the live file to a `.bak-pre-<description>-<timestamp>` backup on the VPS, as a last-resort rollback.
6. For backend changes: `systemctl restart promonta-miniapp`, then `systemctl status` and a health-check curl to confirm it came back up.
7. For frontend changes: reload the app in Telegram and spot-check the changed area.

## GitHub release

Not created without an explicit request — this repo is for version control and documentation continuity, not public release management (it's private, internal tooling for one company).

## Rollback

See [DEPLOYMENT.md](DEPLOYMENT.md#rollback).
