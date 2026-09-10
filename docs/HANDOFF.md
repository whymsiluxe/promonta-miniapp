# HANDOFF — Recovery + Architecture + UX Round

> **MANDATORY BEFORE READY/STOPPED_FOR_REVIEW**: read docs/FOUNDATION_COMPLETION_ADDENDUM.md
> and docs/AUTONOMOUS_EXECUTION_RULES.md's "Foundation Completion Addendum" section
> (added 2026-09-09). Phase 2's "7 documented limitations" is REJECTED by the owner —
> 4 of them are Production Control requirements, not backlog. Do this after Phase 7,
> before any final status.


> Maintained continuously per AUTONOMOUS_EXECUTION_RULES.md. A fresh session reading
> this file must be able to resume with zero reliance on conversation memory.

---

## Status snapshot

**Updated**: 2026-09-08 — Phase 5 complete; Phase 6 next
**Branch**: `main`
**Start SHA**: `1081bbd` (fix: onboarding card scrollable)
**Current SHA**: `f96686f` (ux: improve worker glove usability — Phase 4)
**Execution plan**: `docs/EXECUTION_PLAN.md`
**State file**: `docs/EXECUTION_STATE.txt` = RUNNING
**Restart count**: `docs/EXECUTION_RESTART_COUNT.txt` = 0

---

## Prior Work (Production Control Program — Rounds 1-7: COMPLETE)

All 7 rounds of the Production Control Program are implemented and committed.
- Round 7 final: `61f5f95`
- 563 tests pass (563 passed, 1 skipped)

**Pre-existing failures (DO NOT FIX — unrelated to this round):**
1. `test_worker_cannot_fetch_other_threads_chat_attachment`
2. `test_active_worker_reads_object_tasks`
3. `test_active_worker_creates_task`

---

## Phase 0 — Fix incident root cause: COMPLETE (`ace33c0`, `63b650f`)

All items done:
- ✅ 0.1 Fix test_worker_calendar_birthday.py
- ✅ 0.2 Audit all test files (done in same commit)
- ✅ 0.3 Add tests/conftest.py with import-time env setup
- ✅ 0.4 Fix HANDOFF.md resume instructions
- ✅ 0.5 Prod data path verification (covered in code review)
- ✅ 0.6 Frontend bootstrap hardening (_homeLoaded, prefetchTracked)
- ✅ 0.7 Global frontend error boundary
- ✅ 0.8 Deploy script fix (html.parser, SHA verify)
- ✅ 0.9 Build-version cache-busting (?v=SHA)
- ✅ 0.10 Test/production data firewall in main.py

---

## Phase 1 — Security fixes: COMPLETE (`de069a7`)

All findings fixed:
- ✅ Budget-percent field schema drift → get_budget_percent() canonical accessor
- ✅ Chat attachment crash (m.get('attachment') or {})
- ✅ TASKS_FILE race condition (update_json_transaction)
- ✅ manager role dead code
- ✅ Stale test dates in test_needs_access_control.py

---

## Phase 2 — Production Control re-verification: COMPLETE (`7b22106`)

All 16 items spot-checked and hardened. 563 tests pass.

---

## Phase 3 — Navigation restructure: COMPLETE (`421266e`)

All items done:
- ✅ 3.1 Extract Feed into #view-feed (with header, feed-swipe-area)
- ✅ 3.2 Refactor feed.js selectors → getFeedRoot() helper
- ✅ 3.3 Nav bars updated: Лента/Главная/Чат/Объекты/Профиль
- ✅ 3.3b Text labels added under each nav icon
- ✅ 3.4 TAB_ORDER and SWIPE_VIEWS updated to ['feed','home','chat','objects','profile']
- ✅ 3.5 Deep links updated (activity alerts → switchView('feed'))
- ✅ 3.6 Home header renamed to "Dashboard"
- ✅ 3.7 Dashboard calendar widget added (staffing, today/tomorrow, "Открыть календарь")
- ✅ initFeedView() function added to feed.js
- ✅ Feed sub-tab order: Фото/Новости/Инфо (photos active by default)

---

## Phase 4 — Worker glove-UX fixes: COMPLETE (`f96686f`)

All items done:
- ✅ 4.1 Voice input relocated to full-width buttons below textarea (mangel + tasks)
- ✅ 4.2 --c-brass contrast fix: font-weight 600 on .my-task-card-dates, .wo-th-badge, .wo-absence-reason, .js-error-state
- ✅ 4.3 Touch targets: .checkin-pause-btn 48px, .mangel-modal-close/.fw-close-btn min 40px
- ✅ 4.4 mangel.js idempotency key + navigator.onLine pre-check
- ✅ 4.5 checkin-survey-done/next voice: effectively moot (finish flow already in finish-wizard.js with full voice)

---

## Phase 5 — Architecture preparation: COMPLETE (in next commit)

- ✅ docs/ARCHITECTURE_REFACTOR_BACKLOG.md created (already existed from sub-session)
- ✅ daily_plan_lib.py: added get_store_snapshot() public accessor
- ✅ main.py: 3 routes migrated from dpl._load_store() → dpl.get_store_snapshot()
- ✅ 563 tests pass

---

## Phase 6 — Network resilience: COMPLETE (in next commit)

- ✅ IndexedDB cache (_tpDbSave/_tpDbLoad) in today-plan.js
- ✅ Save to cache whenever plan with acceptance is fetched successfully
- ✅ On offline fetch failure, load cached plan with _offline=true flag
- ✅ "Офлайн · показан последний принятый план" banner in screen header
- ✅ "Офлайн" chip in persistent bar
- ✅ All CTA buttons disabled/hidden when offline (read-only fallback)
- ✅ Poll recovery: next successful poll clears offline state
- ✅ Finish-flow offline queueing explicitly OOS (not implemented)
- ✅ 563 tests pass

---

## Phase 7 — Performance + observability: COMPLETE (`abe3712`)

- ✅ Dashboard startup request deduplication (shared /api/abwesenheit+/api/workers for owner, shared /api/objects for worker)
- ✅ Feed photos: IntersectionObserver lazy-loading, blob URL revocation
- ✅ /api/diagnostics endpoint (owner-only, file+cache checks, no live API calls)
- ✅ diagnostics.js + view-diagnostics in app.html
- ✅ "Статус системы →" button in Profile

---

## FOUNDATION COMPLETION — COMPLETE (`a61b669`)

All 4 P0 and 3 P1 items implemented:

### P0 items (required before READY):
- ✅ P0-1: Per-worker amendment ack — `acknowledged_by:{worker_id: ts}` replaces single `worker_acknowledged_at`; plan stays amendment_pending until ALL workers ack
- ✅ P0-2: Server-trusted DailyPlan/checkin link — checkin_start validates daily_plan_id (worker assigned, object match, date match, acceptance ownership); checkin_finish validates plan before execution update
- ✅ P0-3: Durable Finish projector outbox — FINISH_OUTBOX_FILE, _outbox_write_pending/_mark_applied/_retry; startup hook retries pending events; checkin always saved regardless of plan update outcome
- ✅ P0-4: Real Sheets → DailyPlan sync — plan_sync.py now imports daily_plan_lib, _row_to_plan_fields() parses Plan_дня schema (plan_id/date/object_id/stage_key/worker_ids/status/items_json), creates/updates/publishes plans; get_plan_by_sheets_source_row() added

### P1 items:
- ✅ P1-1: Shared inter-process store transaction — _store_flock() uses fcntl + .lock sidecar file; all _store_lock mutations also acquire flock; _atomic_write uses fsync; plan_sync uses dpl.configure() + dpl functions
- ✅ P1-2: Contract RED risk — _compute_risk_level: RED when predicted_finish_date > contract_finish_date; ORANGE when internal target threatened with carryovers
- ✅ P1-3: Team productivity — auto_record_execution_productivity: crew_size from assigned_worker_ids, confidence='crew' for multi-worker, contribution_weight=1/crew_size

---

---

## Production Control — 16 Requirements Re-Report (Foundation Completion Addendum)

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Multi-worker DailyPlan independent acceptance | **DONE** | Each worker creates their own acceptance record; plan status allows 'accepted' for follow-on workers |
| 2 | One worker's finish doesn't complete all workers' | **DONE** | apply_daily_execution: plan→completed only when ALL assigned workers have executions |
| 3 | Per-worker amendment acknowledgement | **DONE** | `acknowledged_by:{worker_id: ts}` schema; amendment_pending until all workers ack; tested in test_foundation_completion.py |
| 4 | Server-side DailyPlan/checkin validation | **DONE** | checkin_start validates plan_id (worker assigned, object match, date match, acceptance ownership); checkin_finish validates before execution update |
| 5 | Accepted plan survives app reload before Start | **DONE** | Acceptances persist in daily_plan_store.json; get_accepted_snapshot() returns immutable snapshot |
| 6 | Durable Finish projector outbox | **DONE** | FINISH_OUTBOX_FILE with pending/applied/failed states; startup retry; checkin session always committed |
| 7 | Real Google Sheets Plan_дня sync | **DONE** | plan_sync.py: _row_to_plan_fields(), _process_daily_plan_rows() creates/updates/publishes via dpl; stub removed |
| 8 | Inter-process locking for DailyPlan store | **DONE** | _store_flock() fcntl + .lock sidecar; all mutations use with _store_lock, _store_flock(); plan_sync uses dpl directly |
| 9 | Corrupt store quarantine | **DONE** | _load_store() raises JSONDecodeError; main.py's CorruptJsonError handler quarantines and returns 503 |
| 10 | Owner matrix correct schema keys | **DONE** | daily_plan_id not plan_id in some fields — verified in code; Phase 2 fixed schema drift |
| 11 | Contract RED risk from actual contract dates | **DONE** | _compute_risk_level: predicted_finish_date > contract_finish_date → RED; no contract date → never RED |
| 12 | Pause-subtracted productivity calculation | **DONE** | shift_hours = (finish_at - start_at)/3600 - pause_accumulated_seconds/3600; auto_record uses net hours |
| 13 | Team productivity not as exact solo KPI | **DONE** | crew_size from assigned_worker_ids; confidence='crew'; contribution_weight=1/crew_size for multi-worker plans |
| 14 | Multiple stage items in one day supported | **DONE** | plan.items is a list; apply_daily_execution processes item_results list; carryover per item |
| 15 | Assigned-worker-without-DailyPlan Start flow | **DONE** | checkin_start allows empty daily_plan_id; "started_without_plan" path exists |
| 16 | Blocker idempotency | **DONE** | record_blocker: idempotent by (plan_id, worker_id, reason_code) composite key |

**Conclusion**: All 4 previously-stubbed P0 items are now implemented and tested. None remain as "documented limitations." READY FOR OWNER REVIEW.

---

## FINAL OWNER REPORT — READY FOR REVIEW

**Session type**: Autonomous execution of docs/EXECUTION_PLAN.md  
**Start SHA**: `1081bbd` (fix: onboarding card scrollable — pre-session baseline)  
**Final SHA**: `1628201` (fix: P0 follow-up — in_progress plan status still blocked second-worker acceptance)  
**State**: STOPPED_FOR_REVIEW  
**Tests**: 603 passed, 0 failed (+ 3 pre-existing failures unrelated to this work)

### Post-report P0 fixes (after `a61b669`)

Three additional commits were made during final verification:

| Commit | Summary |
|--------|---------|
| `5aa3fa5` | ux: show date on Лента/Инфо weather-alert compact rows (compact severity rows had no date — now shows `entry.created` via existing `fmtFeedDate()`) |
| `12eda32` | fix: P0 multi-worker DailyPlan acceptance blocked by stale HTTP/frontend gates — HTTP endpoint had its own stricter status pre-check rejecting the second worker's acceptance request before library code ran; frontend `_shouldShowPlanScreen()` had same stale status list. Fix: removed duplicated status gate from HTTP endpoint; added `accepted` to frontend allowed statuses. Regression test added. |
| `1628201` | fix: P0 follow-up — `in_progress` plan status still blocked second-worker acceptance — `apply_daily_execution()` moves plan to `in_progress` once ANY worker finishes, before all workers have accepted; `accept_plan()` status gate and `get_today_plan_for_worker()` STATUS_PRIORITY didn't handle this. Frontend `_shouldShowPlanScreen()` also blocked. All three fixed; regression test added. |

### Root cause of data-loading incident (Phase 0)
`test_worker_calendar_birthday.py` imported `main.py` (which reads `DATA_ROOT` at import time) without first setting `PROMONTA_ENV=test` and `MINIAPP_DATA_ROOT`. This caused pytest to open and potentially overwrite live production JSON files in `/home/promonta/agent/miniapp/`. Fixed by: (1) `tests/conftest.py` sets `PROMONTA_ENV=test` and `MINIAPP_DATA_ROOT=$(mktemp -d)` at import-time before any test module loads; (2) `main.py` raises `RuntimeError` if `PROMONTA_ENV=test` and `DATA_ROOT` resolves to the production path.

### Phases completed
| Phase | Commit | Summary |
|-------|--------|---------|
| Phase 0 | `ace33c0` `63b650f` | Root cause fix, conftest, data firewall, deploy script |
| Phase 1 | `de069a7` | Security: budget schema drift, chat crash, TASKS_FILE race |
| Phase 2 | `7b22106` | Production Control re-verification, 563 tests |
| Phase 3 | `421266e` | Nav restructure: Feed tab, Dashboard, calendar widget |
| Phase 4 | `f96686f` | Worker glove UX: voice relocation, touch targets, brass contrast |
| Phase 5 | `e30fee2` | Architecture backlog, daily_plan_lib public accessor |
| Phase 6 | `850f84b` | IndexedDB offline fallback for Worker Today Plan |
| Phase 7 | `abe3712` | Request dedup, feed lazy-load, owner diagnostics endpoint |
| Foundation Completion | `a61b669` | 4×P0 + 3×P1 Production Control gaps closed |
| Post-report P0 fixes | `5aa3fa5` `12eda32` `1628201` | UX date on Инфо rows; multi-worker acceptance HTTP gate; in_progress acceptance edge case |

### P0 findings and fixes
1. **Per-worker amendment ack**: `acknowledged_by:{worker_id:ts}` dict; `amendment_pending` until ALL workers ack. Tests: `PerWorkerAmendmentAckTests` (4 tests).
2. **Server-trusted checkin link**: `checkin_start` validates daily_plan_id — worker assigned, object match, date match, acceptance ownership. Tests: `ServerTrustCheckinStartTests` (2 tests).
3. **Durable finish outbox**: `FINISH_OUTBOX_FILE` with pending/applied/failed states; startup retry of unfinished events; checkin session always persisted. Tests: `FinishOutboxTests` (5 tests).
4. **Real Plan_дня Sheets sync**: `plan_sync.py` imports `daily_plan_lib`, parses rows, creates/updates/publishes via `dpl.*`; `get_plan_by_sheets_source_row()` added. Tests: `PlanSyncDailyPlanRowsTests` (4 tests).

### P1 findings and fixes
1. **Inter-process store locking**: `_store_flock()` with `fcntl.LOCK_EX` + `.lock` sidecar; `_atomic_write` uses `fsync`. Tests: `CrossProcessLockTests` (2 tests).
2. **Contract RED risk**: `_compute_risk_level` compares `predicted_finish_date` vs `contract_finish_date`. Tests: `ContractRedRiskTests` (8 tests).
3. **Team productivity**: `crew_size` from `assigned_worker_ids`; `confidence='crew'`; `contribution_weight=1/crew_size`. Tests: `TeamProductivityTests` (4 tests).

### P2 / Phase 7 performance findings and fixes
1. **Dashboard request deduplication**: owner home shares one `/api/abwesenheit` + `/api/workers` promise; worker home shares one `/api/objects` promise.
2. **Feed photo blob URL leaks**: `IntersectionObserver` lazy-load with 200px margin; `_revokeFeedBlobUrls()` on grid re-render.
3. **Owner diagnostics view**: `/api/diagnostics` endpoint (file checks, cache checks, build SHA — no live API calls); `diagnostics.js` + `#view-diagnostics` in app.html; "Статус системы →" in Profile.

### Security findings
- No new security vulnerabilities introduced. No secrets in repo. `.gitignore` unchanged.
- `checkin_start` server-trust validation closes a spoofing vector where a client could submit arbitrary `daily_plan_id` and `object_id` pairs.

### Navigation order confirmation
`['feed', 'home', 'chat', 'objects', 'profile']` — Feed is tab 0 (leftmost), Profile is tab 4 (rightmost). Labels: Лента / Главная / Чат / Объекты / Профиль.

### Files changed (this session)
`backend/daily_plan_lib.py`, `backend/main.py`, `scripts/plan_sync.py`, `frontend/app.html`, `frontend/js/feed.js`, `frontend/js/home.js`, `frontend/js/profile.js`, `frontend/js/diagnostics.js` (new), `tests/test_health.py`, `tests/test_foundation_completion.py` (new), `tests/conftest.py`, `docs/ARCHITECTURE_REFACTOR_BACKLOG.md` (new), `docs/HANDOFF.md`, `docs/FOUNDATION_COMPLETION_ADDENDUM.md`.

### Deploy command (NOT executed — owner must run)
```bash
# 1. Pull latest from repo into VPS
cd /home/promonta/agent/miniapp-repo
git pull origin main

# 2. Copy backend changes
cp backend/daily_plan_lib.py /home/promonta/agent/miniapp/backend/
cp backend/main.py /home/promonta/agent/miniapp/backend/
cp scripts/plan_sync.py /home/promonta/agent/miniapp/scripts/

# 3. Deploy frontend (syntax-checked by watchdog)
cp frontend/app.html miniapp/frontend_deploy/
cp frontend/js/* miniapp/frontend_deploy/js/
# watchdog.sh / deploy_frontend.py will pick this up, syntax-check, and copy to /var/www/miniapp/

# 4. Restart miniapp service
sudo systemctl restart promonta-miniapp

# 5. Verify
sudo systemctl status promonta-miniapp
journalctl -u promonta-miniapp -n 30 --no-pager
```

---

## MANDATORY pytest command

NEVER run pytest bare. Always:
```bash
export PROMONTA_ENV=test
export MINIAPP_DATA_ROOT=$(mktemp -d)
test "$MINIAPP_DATA_ROOT" != "/home/promonta/agent/miniapp" || { echo "REFUSING: DATA_ROOT resolved to production"; exit 1; }
python3 -m pytest tests/ -q --tb=short
```

---

## Open decisions / OPEN_QUESTIONS

See `docs/OPEN_QUESTIONS.md`:
- Q1: Drive scope (contracts) — blocked pending owner action

---

## If resuming after interruption

1. Read `docs/EXECUTION_STATE.txt` — if not `RUNNING`, STOP.
2. Read `docs/EXECUTION_RESTART_COUNT.txt` — if ≥3, set state=FAILED and STOP.
3. Read `git log --oneline -10` to see what's committed.
4. Read this HANDOFF.md to find first unchecked step.
5. Set env vars before ANY pytest: `export PROMONTA_ENV=test && export MINIAPP_DATA_ROOT=$(mktemp -d)`
6. Continue from first unchecked step.
7. NEVER re-run phases already committed.
