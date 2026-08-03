# Project state

**Last updated**: 2026-08-01, worker profile v2 / onboarding v2 / unified
work-type catalog / unified assignment feature (NOT YET DEPLOYED as of this
writing — see `docs/CHANGELOG.md` entry "2026-08-01" for full detail; this
file is the short summary). Previous entry: 2026-07-31 4-round
release-hardening pass, deployed as `526922f`.

**Branch**: `main` (GitHub default). Deployed SHA / production:
`526922fb263d3296e5958b0a5857b6c4e90d3fef` — the 2026-08-01 work is pushed
to `main` and CI-green but **not yet deployed to production** (per this
task's own instruction: no deploy without separate go-ahead).

**Repo**: https://github.com/whymsiluxe/promonta-miniapp — **currently
PUBLIC**. This is a known blocker, see below — needs manual switch to
private before pilot rollout.

**Working tree**: clean, everything pushed to `origin/main`, CI green.

## What this document is

The single place to check first after any session loss. If this contradicts
something elsewhere, this file wins for "what's the current operational
state" — other docs (ARCHITECTURE, FEATURES, RELEASE_AUDIT, etc.) are the
detailed reference and may lag behind.

## Stack

Vanilla HTML/JS frontend (no build step) + FastAPI/Python backend (single
`main.py`) + flat JSON file storage (no database, atomic writes + lock on
all critical stores, corrupt-file quarantine with a persistent lock marker)
+ Google Sheets for object/tool data (via `objekte_lib.py`/`tools_lib.py`).
All backend runtime-data JSON paths (roles/assignments/checkin/chat/
abwesenheit/profiles/tasks/critical-alerts/roadmap/stage-requests/etc.) are
isolated via `MINIAPP_DATA_ROOT`, verified by a real subprocess test. Full
detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Environments

Production only, single VPS (Hetzner, `162.55.53.147`, `app.promonta.fun`).
No staging, no local dev environment set up yet. See [DEPLOYMENT.md](DEPLOYMENT.md).

## What's working

App is live, in active daily use. As of this pass:

- **Repo self-sufficiency**: `tools_lib.py`, `mangel_lib.py`, `objekte_lib.py`,
  `roadmap_lib.py` are ALL tracked in `backend/` and loaded via an isolated
  `importlib` loader (resolves relative to `main.py`'s own directory, not
  global `sys.path`) — a clean `git clone` + deploy reproduces working code
  for all of them. (Previously `objekte_lib.py` was the last untracked one —
  fixed.)
- **Security**: chat attachments/voice/transcribe validate file content via
  magic-byte allowlist. Worker object-mutation scope enforced (accepted
  assignment required, was previously global write access). Chat attachment
  access (including archived messages) checked per-message, not just first
  match. Abwesenheit `reason`/`note`/`start_time`/`end_time` redacted from
  other workers' view (own record and owner still see everything).
- **Reliability**: critical JSON stores quarantine corrupt files with a
  *persistent* `.corrupt-lock` marker (not just a one-shot 503 — a second
  request after quarantine used to silently fall back to an empty default).
  Tool checkout/return/creation races closed with real per-serial and
  creation-scoped locks, verified with `threading.Barrier` concurrency tests.
- **Caddy/HTTP**: `.bak-*`/`.git`/hidden-file serving blocked (was a live
  P0 — verified 200 OK on a real `.bak` snapshot before the fix). CSP
  `media-src` allows `blob:` (voice playback). Body-size limit raised to
  30MB (was rejecting legitimate 2-photo finish-shift uploads under the old
  10MB cap). Config changes always applied via backup + `caddy validate` +
  reload, never blind.
- **Deploy**: `scripts/deploy.sh` covers all backend lib modules + PDF JS
  scripts in backup/restore/syntax-check; trap-based auto-rollback if any
  step after backup creation fails; test suite runs with a dummy `BOT_TOKEN`
  + isolated `MINIAPP_DATA_ROOT`, never production credentials; frontend
  JS/CSS get deploy-time cache-busting (`?v=<SHA>`) injected into the
  *serving* copy of `app.html`.
- **CI**: green, runs full pytest + Python/JS/shell syntax + required-files
  (including `objekte_lib.py`/`roadmap_lib.py`/PDF scripts, previously not
  checked at all despite being required) + `npm ci` + `pdfkit` smoke-check +
  secrets scan.
- **Test coverage**: 202 automated backend tests (was 151 before this pass),
  fully offline, including real concurrency tests (not sequential-call
  approximations) and a real subprocess `MINIAPP_DATA_ROOT` isolation test.

## Known blockers

- **2026-08-01 feature not deployed** — new onboarding v2, unified work-type
  catalog, unified Assignment Sheet are pushed+CI-green on `main` but not
  yet copied to production (`scripts/deploy.sh` not run for this batch —
  needs explicit go-ahead). No manual Telegram E2E performed yet either
  (Safari MCP non-functional in this environment) — code-review only.
- **GitHub repository is public** — needs a manual switch to private
  (Settings → Danger Zone → Change visibility) before pilot. Not done
  automatically per explicit instruction to never change this silently.
- **GitHub PAT not rotated** — the token used throughout these sessions for
  CI-status checks and git push has been in active use; rotation discussed,
  not executed, no explicit go-ahead yet.
- **No live Telegram E2E verification** — all fixes across all four rounds
  were verified via automated tests + manual code reading + live curl/health
  checks against production, never a real Telegram WebView session. Safari
  MCP is not functional in this environment (`safari-helper` process does
  not respond). Owner is doing this manually with screenshots.
- **~144 loose `.bak-*` files** still physically present on
  `/var/www/miniapp/` — Caddy no longer serves them (404 confirmed), but
  disk isn't cleaned. Left as-is per explicit prior owner decision; only
  remove on explicit request.
- **No frontend request timeout** (AbortController) in `api()` — was
  requested once, deferred as non-blocking UX polish, not yet done.

## Technical debt

- No local dev environment — all iteration happens against the live VPS.
- Frontend deploy uses `scp`/`rsync` + backup + restart via `scripts/deploy.sh` —
  not a fully automated `git push`-to-production pipeline (by design; a
  human-triggered script with pre-flight checks, not auto-deploy-on-merge).
- Backend is NOT symlink-atomic (staged release dir + atomic switch) — would
  require changing the systemd unit's fixed `WorkingDirectory`, out of scope
  so far. Compensated with trap-based auto-rollback instead (see deploy.sh).
- No formal semantic versioning — `VERSION` file just tracks `{version,
  commit}` from the deploying SHA.
- `package-lock.json` exists for the PDF (`pdfkit`) dependency and CI
  verifies it via `npm ci`, but production `node_modules` on the VPS was
  installed manually outside of any tracked process — `deploy.sh` checks
  its presence before touching prod files but doesn't install it itself.

## 2026-08-03 status

Both remaining backend pilot blockers closed and deployed to production
(commit `859d3dc`):
- checkin_finish now verifies actually-saved photo count, not raw upload
  count (see CHANGELOG).
- Object access (chat/files/stages/check-in) now gated by assignment
  `[date_from, date_to]` period via `has_active_object_access()`, not just
  `accepted` status.

## 2026-08-03 second pass (session tokens, Owner AI freeze, worker-privacy, needs ACL, business-date sweep)

Code + tests only, pushed to `main`, **NOT deployed** (per explicit instruction
this round — `scripts/deploy.sh` not run). Production backend still serves
`859d3dc`; `main` HEAD after this pass is ahead of it (see CHANGELOG entry
"стабилизационный раунд" for full detail). Full local suite: 355 passed,
1 skipped (pre-existing) — test count has grown since the "202 automated
backend tests" figure quoted above (2026-08-01 entry); that number is stale,
current count is visible directly from `pytest tests/ -q` output, not tracked
as a fixed figure in this doc going forward.

Closed this pass:
- 12-hour backend session token over Telegram initData (was: hard 1h initData
  TTL, worker got 401 mid-shift).
- Owner AI (Claude CLI subprocess) safe freeze: `OWNER_AI_ENABLED` env flag
  (default false), `--dangerously-skip-permissions` removed, subprocess env
  reduced to an explicit allowlist instead of full `os.environ`.
- `GET /api/objects` no longer leaks colleague assignment metadata
  (`task_note`/`decline_reason`/`assignment_id`/dates/pending-declined status)
  to Worker — new `_serialize_object_for_worker()` DTO.
- Access control added to `/api/tasks` (Потребности) GET+POST when `object_id`
  is passed — worker now needs `has_active_object_access`.
- `business_now()`/`business_today()`/`business_today_str()` — remaining UTC
  `date.today()`/`datetime.now()` call sites (assignment matching, profile
  aggregates, stage completion dates, dashboard "today") moved onto the
  Europe/Berlin business-date helper introduced in the prior pass.

Explicitly deferred this pass (owner decision, not forgotten):
- **Manager/Bauleiter role** — out of scope, not requested for this round.
- **Owner AI real sandbox** (separate Unix user, read-only checkout, process
  isolation) — the env-flag freeze above is a stopgap, not the real fix.
  Re-enabling `OWNER_AI_ENABLED=true` in production without that sandbox
  reintroduces full-repo subprocess access risk.
- **PostgreSQL / DB migration** — flat JSON storage stays as-is.
- **Offline queue** (full client-side offline-first write queue) — not built.
- **`main.py` decomposition** — still one large file, no split into routers.
- **Redesign** — no UI/IA changes this pass, fixes only.
- **Rate limiting on all upload endpoints** — not extended beyond what
  already existed (AI chat rate limit only).
- **New access model for `GET` stages/roadmap** — stays open to any worker,
  per prior explicit owner decision, unchanged this round.

## Next recommended step

1. Make the GitHub repository private, then rotate the PAT that's been in
   use, enable secret scanning, add branch protection on `main` (see
   CHANGELOG "manual checklist" — none of these four executed automatically
   per instruction).
2. Perform the live Telegram Worker A / Worker B / Owner E2E walkthrough —
   this is the one thing automated agents in this environment could not do.
3. Review this pass's diff (session tokens / Owner AI freeze / worker-privacy
   DTO / needs ACL / business-date sweep), then run `scripts/deploy.sh`
   explicitly when ready — not part of this pass.
4. Once E2E passes, repo is private, and this pass is deployed: this becomes
   genuinely READY FOR PILOT, not before.
