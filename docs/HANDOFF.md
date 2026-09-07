# HANDOFF — Production Control Program

> Maintained continuously per AUTONOMOUS_EXECUTION_RULES.md. A fresh session reading
> this file must be able to resume with zero reliance on conversation memory.

---

## Status snapshot

**Updated**: 2026-09-08 — ALL ROUNDS 1-7 COMPLETE
**Start SHA**: `90fd59b8f62a28edb0124c6bb546ea566cadbc74`
**Final SHA**: `c1f876a` (Round 6), `test_round7_hardening` pending commit
**Branch**: `main`
**Current tests**: 533 passed, 3 pre-existing failures (unchanged), 44 warnings

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

## Round 2 — COMPLETE

**Goal**: Worker "Сегодня" UX — acceptance screen, persistent bar, checkin link.

**Tests**: 466 passed (was 461), same 3 pre-existing failures.
**Commit**: `67e76df`

### Steps completed
- [x] `frontend/js/today-plan.js` — NEW (461 lines): `checkAndShowTodayPlan()`, blocker form, polling, bar, acceptance → sets `window._dailyPlanCheckinFields`
- [x] `frontend/js/checkin.js` — reads `window._dailyPlanCheckinFields` on `start` action
- [x] `frontend/app.html` — CSS for `.tp-*`, `#today-plan-screen`, `#today-plan-bar`; DOM elements; `<script>` tag; `initApp()` hook
- [x] `backend/daily_plan_lib.py` — `record_blocker()`; `blockers` key in `_EMPTY_STORE`
- [x] `backend/main.py` — `checkin_start` gets `daily_plan_id/version/acceptance_id` Form fields; `PlanBlockerBody` + `POST /api/daily-plan/{id}/blocker` route
- [x] 5 new tests in `test_daily_plan.py` (blocker endpoint + lib)

---

## Round 3 — COMPLETE

**Goal**: Finish wizard integration — plan-fact step, tomorrow-prep step, carryover, `daily_plan_report` backend field.

**Tests**: 471 passed (was 466), same 3 pre-existing failures.

### Steps completed
- [x] `backend/main.py` — `checkin_finish` gets optional `daily_plan_report: str = Form('')`; calls `dpl.apply_daily_execution()` after session save (idempotent, best-effort)
- [x] `frontend/js/today-plan.js` — exports `window._todayPlanState` (synced at all 3 assignment points)
- [x] `frontend/js/finish-wizard.js` — REWRITTEN:
  - Dynamic step sequence via `_fwStepSequence()`: 6 steps without plan, 8 steps with accepted plan
  - New `plan-fact` step: numbered plan items, 4 status buttons (done/partial/not_done/blocked), qty + comment for non-done items
  - New `tomorrow-prep` step: issue toggle buttons, comment, auto-creates Need entries from selected issues
  - All navigation uses `_fwNavNext()` / `_fwNavBack()` (no hardcoded step numbers)
  - `openFinishShiftWizard()` loads plan from `window._todayPlanState`
  - `_fwSubmitFinish()` appends `daily_plan_report` JSON if item results exist; clears bar after finish
- [x] `frontend/app.html` — CSS for `.fw-plan-item`, `.fw-status-btn`, `.fw-issue-btn`
- [x] `tests/test_daily_plan.py` — 5 new `ApplyDailyExecutionTests`: execution record, plan marked completed, carryover for partial/not_done, idempotency
- [x] `tests/test_object_access_and_checkin_photos.py` + `test_owner_kt_requirements.py` — updated direct calls to pass `daily_plan_report=''`

---

## Round 4 — COMPLETE

**Goal**: Owner matrix + Контроль дня + Worker Card 4-tab extension + risk/replan.

**Tests**: 499 passed (was 471), same 3 pre-existing failures.
**Commit**: `6fdff5c`

### Steps completed
- [x] `backend/main.py`:
  - `GET /api/daily-plan/today` now accepts `?worker_id=X` query param (owners only)
  - `_compute_risk_level(carryovers, amendments, blockers, execution) -> str` (green/yellow/orange)
  - `GET /api/daily-plan/owner/today` updated to compute risk per-plan using blockers
  - `GET /api/daily-plan/owner/matrix` (owner-only, date_from/date_to/object_id filter)
  - `POST /api/daily-plan/replan/{object_id}` (owner-only, read-only risk summary)
  - `daily_plan_lib.get_blockers_for_plan(plan_id)` helper
- [x] `frontend/js/home.js`:
  - `kpi-kontrol` KPI tile in owner dashboard
  - `_loadHomeKontrolDaySummary()` fetches `/api/daily-plan/owner/today`, highlights orange
  - Контроль дня button in working-objects plan tab
- [x] `frontend/app.html`:
  - `view-kontrol-day` div (KPI strip, filter chips, rows, detail overlay)
  - `initKontrolDayView()`, `_renderKdKpi()`, `_renderKdRows()`, `_showKdDetail()`, `closeKdDetail()`
  - Worker Card 4-tab CSS (`.wc-tabs`, `.wc-tab-panel`, `.wc-today-*`, `.wc-today-carryover`)
  - Worker Card "Сегодня" tab renders plan items, carryovers, acceptance time
- [x] `frontend/js/profile.js` — 4-tab Worker Card:
  - `_wcSwitchTab()`, `_loadWorkerCardTab()`, `_loadWcTodayTab()`, `_wcTodayTabHtml()`
  - `_loadWcCalendarTab()` (upcoming absences), `_loadWcProfileTab()` (skills/sizes/birthday)
  - `_loadWorkerCardIdentity()` stashes stats/card on `_workerCardEl`
- [x] 12 new tests in `test_daily_plan.py` (Round4RouteTests class)

---

## Round 5 — COMPLETE

**Goal**: Google Drive contract ingestion (Drive scope BLOCKED, fully gated).

**Tests**: 499 passed (unchanged), same 3 pre-existing failures.
**Commits**: backend+script+tests (`f388c84`), frontend (`ae33524`)

### Steps completed
- [x] `backend/main.py`:
  - `CONTRACTS_DRIVE_FOLDER_ID`, `CONTRACT_INGEST_STATE_FILE`, `_CONTRACT_INGEST_LOCK`
  - `_load_contract_store()`, `_save_contract_store()`
  - `GET /api/contracts`, `GET /api/contracts/{id}`, `POST /api/contracts/{id}/approve`,
    `POST /api/contracts/{id}/reject`, `POST /api/contracts/ingest`
  - `ContractReviewBody` Pydantic model
  - `CONTRACT_INGEST_STATE_FILE` added to `CRITICAL_JSON_PATHS`
- [x] `scripts/contract_ingest.py` — NEW:
  - Drive polling worker, exits if `CONTRACTS_DRIVE_FOLDER_ID` not set
  - `run_once()`, `process_file()`, `_extract_text()`, `_run_claude_extraction()`
  - SHA-256 dedup by (file_id, file_hash)
  - Prompt injection defense in system prompt
- [x] `tests/test_contracts.py` — NEW (16 tests: route + script helpers)
- [x] `frontend/app.html` — `view-contracts` div, `initContractsView()`, `openContractDetail()`
- [x] `frontend/js/home.js` — Договоры quick-nav tile in owner home-stack-wide

**DRIVE_SCOPE_REQUIRED**: Entire ingestion gated on `CONTRACTS_DRIVE_FOLDER_ID` env var.
See `docs/OPEN_QUESTIONS.md Q1` for steps to enable.

---

## Round 6 — COMPLETE

**Goal**: Productivity observations auto-record from execution + Worker Card analytics.

**Tests**: 513 passed (was 499 — 14 new), same 3 pre-existing failures.
**Commit**: `c1f876a`

### Steps completed
- [x] `backend/daily_plan_lib.py`:
  - `auto_record_execution_productivity(session_id, worker_id, plan, item_results, shift_hours)`:
    - For each "done" item with `actual_quantity > 0` and `work_type_id`
    - Distributes `shift_hours` proportionally by `time_estimate_hours` (equal if none)
    - Calls `record_productivity_observation()` for each eligible item (idempotent)
- [x] `backend/main.py`:
  - `checkin_finish`: after `apply_daily_execution`, auto-calls `auto_record_execution_productivity`
  - Computes `shift_hours = (finish_at - start_at) / 3600` from session
- [x] `frontend/js/profile.js`:
  - `_fillProductivityTab` is now async
  - After rendering hours/stats, fetches `/api/productivity/workers/{uid}`
  - `_wcProductivityRatesHtml()`: renders effective rate per work type (qty/h, sample count, hours)
- [x] `frontend/app.html`: CSS for `.wc-prod-rate-*`
- [x] `tests/test_round7_productivity.py` — NEW (14 tests)

---

## Round 7 — COMPLETE

**Goal**: Hardening + final tests + HANDOFF update.

**Tests**: 533 passed (was 513 — 20 new hardening tests), same 3 pre-existing failures.

### Steps completed
- [x] Security audit of all new routes:
  - `GET /api/daily-plan/today?worker_id=X` — verified: worker_id param only honored for owners
  - `GET /api/daily-plan/owner/matrix` — `require_owner` dependency confirmed
  - `POST /api/daily-plan/replan/{object_id}` — `require_owner` confirmed
  - All `/api/contracts/*` routes — `require_owner` confirmed on all
  - `POST /api/productivity/workers/{uid}/baseline` — `require_owner` confirmed
  - `GET /api/productivity/workers/{uid}` — 403 for different worker, self allowed
- [x] `tests/test_round7_hardening.py` — NEW (20 tests):
  - `DailyPlanSecurityTests`: worker_id param ignoring for non-owners, owner matrix structure
  - `ComputeRiskLevelTests`: all 4 risk levels, orange-beats-yellow, done-only-exec=green
  - `ContractRouteHardeningTests`: empty state, 404 on missing contract, 400 on already-approved
  - `AutoRecordEdgeCaseTests`: empty items, missing plan items, orphan items, same work_type twice
- [x] HANDOFF.md: final complete summary (this section)

---

## PROGRAM COMPLETE

All 7 rounds of the Production Control Program are implemented and tested.

**Test delta**: 499 → 533 passed (34 new tests this session, all green).

**Uncommitted changes at end**:
- `tests/test_round7_hardening.py` (to be committed with this HANDOFF update)
- `docs/HANDOFF.md` (this file)

**Deploy checklist** (human to do):
1. `git pull` on VPS
2. `sudo systemctl restart promonta-miniapp`
3. `cp /home/promonta/agent/miniapp-repo/frontend/* /home/promonta/agent/miniapp/frontend_deploy/` (triggers watchdog deploy)
4. Test Контроль дня tile on owner home
5. Test Worker Card 4-tab (Сегодня/Производительность/Календарь/Профиль)
6. Test Finish wizard with plan-fact step
7. Test Контроль дня view (rows, filter chips, detail overlay)
8. Test Договоры view (shows Drive-not-configured notice until Q1 resolved)
9. Check `/api/productivity/workers/{uid}` after next shift finish with plan

**Open questions**: See `docs/OPEN_QUESTIONS.md` — especially Q1 (Drive scope for contracts).

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
