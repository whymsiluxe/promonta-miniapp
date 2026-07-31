# Project state

**Last updated**: 2026-07-31, end of a multi-stage release-readiness pass
(see `docs/RELEASE_AUDIT.md` and `docs/RELEASE_CANDIDATE_REPORT.md` for full
detail — this file is the short summary, those are the authoritative record).

**Branch**: `main` (GitHub default), all release-readiness commits pushed
except `.github/workflows/ci.yml`/`requirements-test.txt` (blocked — see
"Known blockers" below).

**Repo**: https://github.com/whymsiluxe/promonta-miniapp — private.

**Working tree**: clean, pushed to `origin/main` as of this update, except
the two CI files noted above (present in the working tree, uncommitted).

## What this document is

The single place to check first after any session loss. If this contradicts
something elsewhere, this file wins for "what's the current operational
state" — other docs (ARCHITECTURE, FEATURES, RELEASE_AUDIT, etc.) are the
detailed reference.

## Stack

Vanilla HTML/JS frontend (no build step) + FastAPI/Python backend (140
routes, single `main.py`) + flat JSON file storage (no database, atomic
writes on all critical stores) + Google Sheets for object/tool data (via
`objekte_lib.py`/`tools_lib.py`). Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Environments

Production only, single VPS (Hetzner, `162.55.53.147`, `app.promonta.fun`).
No staging, no local dev environment set up yet. See [DEPLOYMENT.md](DEPLOYMENT.md).

## What's working

App is live, in active daily use. As of this release-readiness pass:

- **Security hardening**: chat attachments/voice/transcribe now validate
  file content via magic-byte allowlist (were previously accepting any
  file — real stored-XSS risk via unvalidated `.html`/`.svg` uploads,
  closed). Checkin photo path from client input is now sanitized against
  path traversal.
- **Reliability**: all critical JSON stores (`checkin_meta.json`,
  `chat_messages.json`, `chat_messages_archive.json`, `mangel_tickets.json`,
  most others) write atomically (temp-file + `os.replace`) — a crash mid-write
  no longer corrupts them.
- **Repo self-sufficiency**: `tools_lib.py`, `roadmap_lib.py`, `mangel_lib.py`
  are now tracked in `backend/` and loaded via an isolated `importlib`
  loader (resolves relative to `main.py`'s own directory, not global
  `sys.path`) — a clean `git clone` + deploy reproduces working code for
  these modules. `objekte_lib.py` is still untracked (known gap).
- **Chat unread counter fix**: the general nav badge (`GET
  /api/chat/unread_count`) previously mis-attributed thread-scoped messages
  (obj:/mangel:/task:) to every user's group counter — fixed, now matches
  `unread_by_thread` per-thread logic exactly.
- **Health/ops**: `/api/health` now versioned (version/commit/time),
  `/api/health/ready` added for owner-only readiness checks. Deploy/rollback
  scripts (`scripts/deploy.sh`, `scripts/rollback.sh`,
  `scripts/cleanup_rollback_backups.sh`) written and dry-run-verified.
- **Test coverage**: 151 automated backend tests (was near-zero before this
  pass), fully offline, covering upload security, atomic storage, chat
  unread, health endpoints, tools checkout/return, endpoint access patterns.
- **Documentation**: `docs/RELEASE_AUDIT.md` (full P0/P1/P2 findings),
  `docs/ENDPOINT_ACCESS_MATRIX.md`, `docs/BACKUP_AND_RECOVERY.md`,
  `docs/DATA_PROTECTION.md` all newly written this pass.
- **Инструменты (Tools) screen**: fully redesigned earlier this session —
  compact summary counters, richer search, worker no longer types their own
  name at checkout (backend derives it from Telegram identity), real
  `/return` endpoint (was previously misusing `/checkout` with empty fields).

## Known blockers

- **CI workflow not pushed**: `.github/workflows/ci.yml` and
  `requirements-test.txt` exist in the working tree on the VPS but could not
  be pushed to GitHub — the deploying OAuth token lacks the `workflow`
  scope required to create/update files under `.github/workflows/`. Needs
  either a token with that scope, or a manual push by someone with
  appropriate GitHub permissions. All CI steps were manually verified to
  pass on the VPS before this was written (151 tests, syntax checks,
  required-file checks, secrets scan — all green) — the workflow itself is
  correct, only the push is blocked.
- **No live Telegram E2E verification**: all fixes in this pass were
  verified via automated tests + manual code reading, not a live Telegram
  WebView session. Browser automation (Safari MCP) is not functional in
  this environment (`safari-helper` process does not respond, root cause
  not fully resolved — likely missing macOS Accessibility permission grant
  that requires a manual GUI click, not scriptable). A real Telegram Worker/
  Owner walkthrough is still required before this is truly release-ready —
  see `docs/RELEASE_CANDIDATE_REPORT.md` for the exact scenario checklist.
- **`objekte_lib.py` still untracked in git** — same class of risk `tools_lib.py`/
  `mangel_lib.py` had before this pass, not yet fixed for this module.
- Deploy has NOT been performed for the commits in this release-readiness
  pass as of this writing — `scripts/deploy.sh` exists and is verified via
  dry-run/manual-step checks, but running it against production requires a
  separate explicit go-ahead (per this pass's own instructions: "не
  выполнять production deploy без отдельного подтверждения").

## What requires verification before trusting it

- Whether `angebot-tab.html` / `projects-tab.html` / `tools-tab.html` are
  live or dead frontend code — not re-checked in this pass.
- Whether FastAPI's `/docs` Swagger UI is publicly reachable — `main.py`
  sets `docs_url=None, redoc_url=None, openapi_url=None` in the `FastAPI()`
  constructor, so this should already be closed, but worth a live `curl`
  check after next deploy.
- UX findings from this pass's code-level review (loading/error/empty states,
  double-submit guards, safe-area consistency) — see
  `docs/RELEASE_CANDIDATE_REPORT.md` for what was found and fixed vs. what's
  logged for later.

## Technical debt

- No local dev environment — all iteration happens against the live VPS.
- Frontend deploy uses `scp`/`rsync` + backup + restart via `scripts/deploy.sh` —
  not a fully automated `git push`-to-production pipeline (by design; a
  human-triggered script with pre-flight checks, not auto-deploy-on-merge).
- `objekte_lib.py` untracked in git (see "Known blockers").
- No formal semantic versioning before this pass — first tagged version is
  planned as `0.9.0-rc1` (release candidate), see `docs/RELEASE_CANDIDATE_REPORT.md`.
- 75+ stale `.bak-*` files committed directly in `backend/`/`frontend/` from
  past manual deploys — clutter, not a functional problem, candidate for a
  separate cleanup commit.

## Next recommended step

1. Resolve the GitHub token `workflow` scope issue and push
   `.github/workflows/ci.yml` + `requirements-test.txt`.
2. Perform the live Telegram Worker/Owner/cross-worker E2E walkthrough
   documented in `docs/RELEASE_CANDIDATE_REPORT.md` — this is the one thing
   this pass explicitly could not do itself.
3. Once E2E passes: run `scripts/deploy.sh` for the accumulated commits
   (with explicit owner go-ahead), verify `/api/health` and `/api/health/ready`
   post-deploy.
4. Track `objekte_lib.py` in git the same way `tools_lib.py`/`mangel_lib.py`
   were in this pass (separate, focused commit).
