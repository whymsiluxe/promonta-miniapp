# HANDOFF — Production Control Program

> Maintained continuously per AUTONOMOUS_EXECUTION_RULES.md. A fresh session reading
> this file must be able to resume with zero reliance on conversation memory.

---

## Status snapshot

**Updated**: 2026-09-07, beginning of autonomous run
**Start SHA**: `90fd59b8f62a28edb0124c6bb546ea566cadbc74`
**Branch**: `main` (clean, 2 untracked docs files added at start)
**Baseline tests**: 432 passed, 3 pre-existing failures (see below), 43 warnings

### 3 pre-existing test failures (do NOT fix in this run — unrelated)

1. `test_worker_cannot_fetch_other_threads_chat_attachment`
2. `test_active_worker_reads_object_tasks`
3. `test_active_worker_creates_task`

---

## Round 0 — COMPLETE

### Key findings

**SHA confirmed**: `90fd59b8f62a28edb0124c6bb546ea566cadbc74`

**Productivity field verdict**:
`work_speed` at `main.py:1480-1538` is `{analyzed_sessions: int, last_summary: str}` — a
narrative text field, NOT a numeric rate. `avg_session_hours` is duration, not rate.
**VERDICT: NUMERIC LEGACY PRODUCTIVITY FIELD NOT FOUND.** `manual_baseline_factor` and
`observed_rate` are entirely new fields.

**Worker Card confirmed**:
- Exists in `frontend/js/profile.js:801`
- Signature: `openWorkerCard(uid, returnCtx)` — has returnCtx
- Uses `NavigationManager.registerOverlay(closeWorkerCard)`
- Guard: double-open blocked by `_workerCardEl` check
- Currently has period pills (week/month) but NO 4-tab structure
- Entry points: home.js:1104 (working-objects view), home.js:1096,1301 (team/other),
  chat.js:1298, object-info.js:306,382, objects.js:178, tools.js:94,132

**Finish wizard confirmed**: `frontend/js/finish-wizard.js`, 6 steps
(Фото/Что сделано/Доп.работы/Потребности/Гео/Сводка). No DailyPlan step yet.

**CRITICAL_JSON_PATHS convention**: `CRITICAL_JSON_PATHS.update({...})` at `main.py:7589`.
New `daily_plan_store.json` must be added there.

**Business date helpers**: `business_now()`, `business_today()`, `business_today_str()`
at `main.py:625-644`. Use throughout.

**checkin_start** (`main.py:6463`): Form fields `object_id, lat, lon, stage_name, files`.
GPS is required (400 if missing). New optional fields: `daily_plan_id`,
`daily_plan_version`, `daily_plan_acceptance_id`.

**checkin_finish** (`main.py:6597`): Form fields `lat, lon, done_summary, extra_work,
extra_works, needs, defects, next_day_needs, pause_minutes, voice_note_file_id, files`.
2 photos required. New optional field: `daily_plan_report` (JSON).

**Sheets sync**: NO `scripts/plan_sync.py` exists. Inline `_cached_get_used_range()` per
request. Must build from scratch. NO APScheduler in project — use systemd timer.

**Drive OAuth**: `.sheets.json` has `client_id, client_secret, refresh_token` (no scopes
stored). Cannot verify Drive scope from credential file alone.
**STATUS: DRIVE_SCOPE_REQUIRED** — contract ingestion blocked. See OPEN_QUESTIONS.md #1.

**work_types.py**: 47 work types in 8 groups, unified catalog. Already the single source
of truth. Norm fields (baseline_rate_per_hour, default_steps, default_tools/materials)
do NOT yet exist — must add to the catalog or to a separate norms store.

**No plan_sync.py, no contract_ingest.py, no daily_plan_store.json** — all new.

**Files Round 1 will touch**:
- `backend/main.py` (new routes, store registration, checkin extension)
- `backend/daily_plan_lib.py` (NEW — DailyPlan store operations, extracted for clarity)
- `scripts/plan_sync.py` (NEW — Sheets sync worker)
- `docs/API.md`, `docs/DATABASE.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

---

## Round 1 — COMPLETE

**Goal**: DailyPlan backend core: data store, versioning, acceptance, basic CRUD routes,
plan_sync worker skeleton.

**Tests**: 461 passed (was 432), same 3 pre-existing failures.

### Steps completed
- [x] Data model: `daily_plan_store.json` schema defined (all 9 entity types)
- [x] `backend/daily_plan_lib.py` created (store ops, versioning, acceptance, carryover, productivity)
- [x] New routes in `main.py`:
  - GET /api/daily-plan/today (worker's plan for today)
  - POST /api/daily-plan/{id}/accept (worker acceptance)
  - POST /api/daily-plan/{id}/amendments/{id}/accept (amendment acknowledgment)
  - GET /api/daily-plan/owner/today (Контроль дня unified DTO)
  - GET /api/daily-plan/object/{id} (object day-by-day)
  - POST /api/daily-plan (owner creates plan)
  - GET /api/daily-plan/{id} (full plan detail)
  - GET /api/productivity/workers/{id} (worker productivity)
  - POST /api/productivity/workers/{id}/baseline (owner sets prior)
- [x] CRITICAL_JSON_PATHS updated with DAILY_PLAN_STORE_FILE
- [x] `scripts/plan_sync.py` skeleton (reads Plan_этапов/Plan_дня/Нормы_работ, 60s interval, backoff)
- [x] Defensive fix: `checkin_meta` lookups use `.get('id')` not `['id']` for manual entries
- [x] 29 new tests in `tests/test_daily_plan.py` (all passing)

### Files changed in Round 1
- `backend/daily_plan_lib.py` — NEW
- `backend/main.py` — import, file constants, 9 routes, CRITICAL_JSON_PATHS, defensive fix
- `scripts/plan_sync.py` — NEW
- `tests/test_daily_plan.py` — NEW
- `docs/HANDOFF.md` — this file

---

## Rounds 2-7 — NOT STARTED

- **Round 2**: Worker "Сегодня" UX + acceptance screen + persistent bar + checkin link
- **Round 3**: Finish wizard integration + fact-report + carryover + tomorrow-prep + Needs
- **Round 4**: Owner matrix + Контроль дня + Worker Card 4-tab extension + risk/replan
- **Round 5**: Google Drive contract ingestion + extraction + draft Project Plan
- **Round 6**: Productivity observations + effective rates + Worker Card analytics
- **Round 7**: Hardening + full tests + real Telegram E2E checklist

---

## Decisions made (non-trivial)

1. **DailyPlan store in single file**: `daily_plan_store.json` with top-level keys
   `{plans, versions, acceptances, amendments, executions, carryovers}`. Single file per
   spec. Added to CRITICAL_JSON_PATHS.

2. **plan_sync.py as standalone script**: No APScheduler exists in project. Use systemd
   timer (like other periodic scripts) rather than importing a scheduler library. This
   matches existing project conventions and avoids new dependencies.

3. **Worker Card tabs via class-based tab system**: Add a `wc-tabs` strip + `wc-tab-panel`
   divs inside the existing `worker-card-panel`. Tab switching is pure JS, no overlay
   recreation. The existing period-pills move inside the Производительность tab.

4. **Finish wizard DailyPlan step**: Insert a new step 2.5 (between "Что сделано" and
   "Доп.работы") — OR extend step 2 to include DailyPlan action list. Decision: extend
   step 2 with a plan-items section when `_fwDailyPlanId` is set. Fallback to current
   step 2 when no plan.

5. **Drive scope**: BLOCKED — report DRIVE_SCOPE_REQUIRED, build all other rounds
   independently of Drive. Round 5 stubs the ingestion endpoint; actual Drive reads gated
   on `CONTRACTS_DRIVE_FOLDER_ID` env var + verified scope.

---

## Technical risks

- `main.py` is already 7601 lines. Every Round 1 route addition grows it further. The spec
  explicitly defers decomposition — acceptable, but diff reviewability is limited.
- Sheets API quota: 5 new tabs + sync worker every 60s. The sync worker must implement
  exponential backoff + quota-pause. Existing inline calls don't have this yet.
- No staging environment — all changes land on production JSON + Sheets.

---

## If resuming after interruption

1. Read this file first.
2. Run: `python3 -m pytest tests/ -q --tb=no` — confirm baseline (432 passed, 3 failing).
3. `git log --oneline -10` to see what was committed.
4. Continue from the first unchecked step in Round 1 above.
5. Check `docs/OPEN_QUESTIONS.md` for unresolved decisions.
