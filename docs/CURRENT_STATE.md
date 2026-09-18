# Current State

**Last updated**: 2026-09-18. This is the single place to check first — if
it contradicts anything elsewhere in `docs/`, this file wins for "what's
true right now." Everything else in `docs/` with a date in its filename
(`*_09sep2026.md`, `*_11sep2026.md`, `*_13sep2026.md`, `HANDOFF*.md`,
`PLAN_*.md`, `EXECUTION_PLAN.md`, `MASTER_ARCHITECTURE_PLAN.md`,
`ROUND1_TASK.md`, `AUTONOMOUS_*.md`, `SESSION_HANDOFF.md`,
`PRODUCTION_CONTROL_PLAN.md`, `RELEASE_AUDIT.md`, `RELEASE_CANDIDATE_REPORT.md`,
`FOUNDATION_COMPLETION_ADDENDUM.md`) is a **historical snapshot of one
finished (or abandoned) work round** — kept for git-blame-style context, not
maintained, not a source of truth. Their content was read in full and folded
into this file and `BACKLOG.md`/`OPEN_QUESTIONS.md` on 2026-09-18; each now
carries a one-line `SUPERSEDED` pointer at the top.

## Repo / branch / deploy

- **Repo**: https://github.com/whymsiluxe/promonta-miniapp — still **PUBLIC**
  (owner has declined to make it private twice; not an oversight, a standing
  decision — see OPEN_QUESTIONS.md).
- **Branch**: `main`. Working tree clean.
- **Deployed = HEAD**: production backend confirms `commit` in
  `GET /api/health` matches `git rev-parse HEAD` on the VPS repo as of this
  writing (`201ef52`). `scripts/deploy.sh` is the only deploy path; both
  manual sessions and the autonomous Codex runner use it directly on the VPS
  repo (no separate CI/CD deploy pipeline).
- **CI**: green on every commit for the last several days (`gh run list`),
  covers full pytest + backend/core + frontend/js subdirs + deploy-manifest
  drift detection (closed 2026-09-17, commit `2676d11`).

## Stack (unchanged, still accurate)

Vanilla HTML/JS frontend (no build step, no framework) + FastAPI/Python
backend (`backend/main.py`) + flat JSON file storage under
`MINIAPP_DATA_ROOT` (no database) + Google Sheets for object/tool data via
`objekte_lib.py`/`tools_lib.py`. Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Scale, as of 2026-09-18

- Tests: **886 passed, 1 skipped** (`PROMONTA_ENV=test pytest tests/ -q`).
- Routes: **185** (`backend/main.py`).
- `backend/main.py`: **10092 lines** — still one file, no router split.
- `frontend/app.html`: **10521 lines** — still one file, most feature logic
  already lives in `frontend/js/*.js` modules, but a meaningful amount
  (styles, view containers, some inline handlers) remains inline.
- `frontend/js/home.js`: 1782 lines, `frontend/js/chat.js`: 2225 lines —
  the two largest JS modules.

## What's working (high-level, see FEATURES.md for the full trace)

App is live, in active daily use by the owner and workers. Recent rounds
(2026-09-13 through 2026-09-18) added, on top of the existing worker
checkin/chat/tasks/defects/tools/abwesenheit feature set:

- **DailyPlan system**: publish/accept/amendment flow, per-worker
  acknowledgment, carryover tracking, blocker reporting, contract-deadline
  risk coloring (RED/GREEN via `predicted_finish_date` vs
  `contract_finish_date`), tomorrow-preview tab (accept a plan a day early
  without it affecting today's shift-start linkage), and two owner alerts —
  an 18:00 "tomorrow's plan not published yet" reminder and a 06:30
  "today's plan is overdue" alert (`backend/daily_plan_cutoff_check.py`,
  two systemd timers). Starting a shift without a plan stays freely allowed
  either way — this is a lagging-indicator alert, not a start-time gate.
- **Shift Flow**: all entry points (Home CTA, bottom FAB, Object Detail,
  DailyPlan) converge on one shared object-picker → stage-picker → start
  flow; the FAB now opens the same real `#active-shift-panel` (timer/GPS/
  pause/quick-actions) as Object Detail instead of a separate simplified
  modal. GPS status shows the real saved accuracy in meters instead of a
  boolean "geolocation API exists" check.
- **Object Info**: budget dashboard, task Kanban (To Do/In Progress/Done),
  document gallery with object filters, team drag-assignment.
- **Calendar (Abwesenheit)**: week + month views (year view + drag-to-move
  deliberately not built — needs its own design pass, see BACKLOG.md),
  `PATCH /api/abwesenheit/{id}` for moving dates.
- **Offline resilience**: outbox pattern for checkin/finish with a
  dead-letter state after 5 failed attempts (`shared.js`
  `promontaOutboxRecordFailure`), `api()` has request timeout + safe-read
  retry.
- **Contract ingestion pipeline exists but is deliberately OFF**:
  `backend/contract_ingest.py`/`scripts/plan_sync.py` (Drive polling → AI
  fact extraction → draft DailyPlan → owner approve/reject) is fully built
  and tested but gated behind `CONTRACTS_DRIVE_FOLDER_ID`, unset in
  production. Owner has explicitly said not to enable it yet (2026-09-18) —
  this is a live decision, not an oversight; see BACKLOG.md.

## Known blockers / standing decisions (not bugs — explicit choices)

- **Repo stays public** — owner declined private twice. Do not silently
  change this.
- **GitHub PAT not rotated** — discussed, no go-ahead yet.
- **No staging environment** — production-only, by scale not by oversight.
- **No live automated Telegram E2E** — covered by unit/contract tests +
  manual owner verification via screenshots, not a scripted WebView flow.

## Technical debt (see BACKLOG.md for the actionable list)

- `backend/main.py` and `frontend/app.html`/`home.js`/`chat.js` remain
  monolithic — no domain/router split has started.
- Flat JSON storage, no database — fine at current scale (see DATABASE.md),
  revisit if concurrency/reporting needs grow.
- No CRM layer (clients/leads/deals) — out of scope so far, P3 idea only.

## Where to look next

- Active/actionable work: [BACKLOG.md](BACKLOG.md).
- Things genuinely waiting on an owner decision: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
- Chronological detail of every change: [CHANGELOG.md](CHANGELOG.md).
- Feature-by-feature trace of what's actually wired end-to-end:
  [FEATURES.md](FEATURES.md) (last verified 2026-09-13 per its own header —
  worth a re-pass given how much has shipped since, not done in this cleanup).
