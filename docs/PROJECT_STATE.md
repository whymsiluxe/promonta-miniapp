# Project state

**Last updated**: 2026-07-23, ~13:15 Berlin time (this recovery session).
**Branch**: `master` (repo just created — see note below on branch naming).
**Working tree**: clean as of the last recovery commit; documentation commit pending.

## What this document is

The single place to check first after any session loss. If this contradicts something elsewhere, this file wins for "what's the current operational state" — other docs (ARCHITECTURE, FEATURES, etc.) are the detailed reference.

## Stack

Vanilla HTML/JS frontend (no build step) + FastAPI/Python backend + flat JSON file storage (no database). Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Environments

Production only, single VPS (Hetzner, `162.55.53.147`, `app.promonta.fun`). No staging, no local dev environment set up yet. See [DEPLOYMENT.md](DEPLOYMENT.md).

## What's working

Per [FEATURES.md](FEATURES.md): the app is live and in active daily use by the owner and at least one worker (confirmed by session history — check-ins, chat, absence requests, defect tickets all have real usage data on the VPS as of today). Most individual feature rows are marked **UNVERIFIED** in FEATURES.md — not because they're suspected broken, but because this recovery's priority was securing the codebase and documenting it accurately, not re-testing every flow. The app was mid-active-development (visual redesign) when the session that prompted this recovery was lost.

## What's partially done / mid-flight

- A visual redesign (luxury splash screen, new icon system, warm color palette) was in progress as of 2026-07-22 evening, directly on the production frontend files. Not confirmed complete or broken — see [UI_UX.md](UI_UX.md).
- A chat-navigation feature was attempted and rolled back the same day (2026-07-22) after apparently causing an issue — details not fully preserved from the lost session, treat this area as recently unstable.

## What's broken / known bugs

- Chat/AI tab scroll behavior — unresolved as of last note, 3 architecture attempts, landed on one not confirmed working by the user. See [UI_UX.md](UI_UX.md).

## What requires verification before trusting it

- Whether `angebot-tab.html` / `projects-tab.html` / `tools-tab.html` are live or dead frontend code.
- Whether FastAPI's `/docs` Swagger UI is publicly reachable (a real exposure if so — not yet checked).
- Most of the 93 backend routes' permission scoping beyond the ones spot-checked in this recovery (GPS check-in filtering, chat message deletion, tool checkout, critical alert ack/resolve — all confirmed correct).

## Security risks (flagged, not silently patched)

- `POST /api/objects/{object_id}/tasks` — any authenticated worker can add a task to any object, not just their own assignment. Low severity, product-level gap, not a data leak. See [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md).
- No automated secret-scanning or dependency-vulnerability checking exists (no CI at all yet).
- Personal/GPS employee data has no formal retention/deletion policy (GDPR-relevant, Germany-based employer) — see [SECURITY.md](SECURITY.md).

## Technical debt

- No local dev environment, no automated tests, no CI/CD — the direct-edit-on-production workflow (with `.bak-pre-*` manual backups) is the root cause of the original lost-session/doc-drift problem this recovery addresses. See [TODO.md](TODO.md) P0.
- Frontend and backend lived in two different directories with two different (or no) git histories until today.

## This session's work (2026-07-23 recovery)

1. Located the actual production code on the VPS (the Mac-local copy was stale, dated 8-12 July vs. VPS code through 22-23 July — using the stale copy would have lost three weeks of work).
2. Built a combined repo `/home/promonta/agent/miniapp-repo/` (`backend/` + `frontend/`, the latter with its prior 14-commit git history preserved via `git subtree`).
3. Verified no secrets are hardcoded in any file being committed (grepped for token/key/secret patterns — zero matches; all secrets confirmed to load from `os.environ`).
4. Wrote `.gitignore` excluding all runtime data (personal/employee data, photos, generated PDFs, `.venv`).
5. Wrote full documentation set (this file plus README, ARCHITECTURE, FEATURES, API, ROLES_AND_PERMISSIONS, DATABASE, DEPLOYMENT, ENVIRONMENT, SECURITY, TROUBLESHOOTING, TESTING, UI_UX, DECISIONS, CHANGELOG, TODO, RELEASE_PROCESS) based on actually reading the code, not assumption.
6. Corrected one piece of stale institutional memory in the process: unknown Telegram user IDs get a hard 403 now, not a silent `worker` default (a whitelist hardening happened since the note that said otherwise was written).
7. Flagged (not fixed) one permission gap and several UNVERIFIED areas for follow-up — see TODO.md.
8. (Separately, unrelated to the app itself) found and killed ~400+ orphaned `chroma-mcp` processes on the Mac that had filled the local disk to the point where no shell command could run — a claude-mem plugin leak, not a miniapp issue, but it blocked work mid-session and is worth someone checking why `uvx` isn't reaping prior instances.

## Next recommended step

Push this repo to a private GitHub repository (pending `gh auth` check) — see [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for exact next commands.

## A note on branch naming

This repo was built directly with `master` as the default branch name (git's current default), not `main`. Other docs in this set refer to `main` as the stable branch per the original task brief's convention — rename the branch to `main` before or during the GitHub push if consistency matters, or update the docs to say `master` throughout. Not yet reconciled in this pass.
