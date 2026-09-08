# HANDOFF — Recovery + Architecture + UX Round

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

## Phase 7 — Performance + observability: NEXT

- Dashboard startup request audit (N+1)
- Feed photos thumbnail-first loading
- Owner diagnostics view/endpoint

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
