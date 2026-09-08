# HANDOFF — Recovery + Architecture + UX Round

> Maintained continuously per AUTONOMOUS_EXECUTION_RULES.md. A fresh session reading
> this file must be able to resume with zero reliance on conversation memory.

---

## Status snapshot

**Updated**: 2026-09-08 — NEW ROUND STARTED (Phase 0 in progress)
**Branch**: `main`
**Start SHA**: `1081bbd` (fix: onboarding card scrollable)
**Execution plan**: `docs/EXECUTION_PLAN.md`
**State file**: `docs/EXECUTION_STATE.txt` = RUNNING
**Restart count**: `docs/EXECUTION_RESTART_COUNT.txt` = 1

---

## Prior Work (Production Control Program — Rounds 1-7: COMPLETE)

All 7 rounds of the Production Control Program are implemented and committed.
- Round 7 final: `61f5f95`
- 533 tests passed, 3 pre-existing failures (unchanged)

**Pre-existing failures (DO NOT FIX — unrelated to this round):**
1. `test_worker_cannot_fetch_other_threads_chat_attachment`
2. `test_active_worker_reads_object_tasks`
3. `test_active_worker_creates_task`

---

## Phase 0 — Fix incident root cause (test isolation + firewall)

### Phase 0 status: IN PROGRESS

**Incident recap**: `test_worker_calendar_birthday.py`'s `BirthdayAlertTests.setUp()` called
`backend._save_roles({'1': 'owner', '100': 'worker'})` without `MINIAPP_DATA_ROOT` set.
`DATA_ROOT` defaulted to `/home/promonta/agent/miniapp` (live prod). A blind watchdog
restarted the test process ~100 times over 8.5 hours, each time overwriting prod's
`roles.json`. Manual fix already applied (roles.json restored). This phase fixes the
architectural gap so it cannot recur.

### Phase 0 steps:

- [ ] 0.1 Fix `test_worker_calendar_birthday.py` — add env setup before module-level import
- [ ] 0.2 Audit all test files for same gap
- [ ] 0.3 Add `tests/conftest.py` with import-time env setup + autouse assertion
- [ ] 0.4 Fix `docs/HANDOFF.md` resume instructions (bare pytest command) ← this file
- [ ] 0.5 Verify prod data path end-to-end (routes return real data)
- [ ] 0.6 Frontend bootstrap hardening (_homeLoaded, prefetchTracked, loadedViews)
- [ ] 0.7 Global frontend error boundary (window.onerror + unhandledrejection)
- [ ] 0.8 Deploy script fix (deploy_frontend.py — real HTML parser, SHA verify, health check)
- [ ] 0.9 Build-version cache-busting (git SHA → ?v= querystring in app.html)
- [ ] 0.10 Test/production data firewall in main.py (RuntimeError if PROMONTA_ENV=test + prod path)

---

## Phase 1 — Security fixes

Status: NOT STARTED

**CRITICAL NOTE on finding #1**: The budget-percent field name discrepancy is schema drift
across 3 call sites. Do NOT blindly replace one key with another. Read the live Sheet header
first (read-only), then build `get_budget_percent(obj)` canonical accessor. Full details in
`docs/EXECUTION_PLAN.md` Phase 1.

Findings to fix:
- Budget-percent field schema drift (main.py:1763, 2679, objekte_lib.py:342,354)
- Chat attachment crash (`m.get('attachment') or {}`, main.py:4826-4827)
- TASKS_FILE race condition (main.py:6068-6151)
- manager role dead code (main.py:3009-3011)
- Stale test dates in test_needs_access_control.py:24

---

## Phase 2 — Production Control re-verification

Status: NOT STARTED

---

## Phase 3 — Navigation restructure

Status: NOT STARTED
- Extract Feed into #view-feed
- Nav order: Feed, Dashboard, Chat, Объекты, Профиль
- Sub-tab order: Фото, Новости, Инфо
- Dashboard calendar widget (staffing-first, not month-grid)
- Add nav labels under icons

---

## Phase 4 — Worker glove-UX fixes

Status: NOT STARTED

---

## Phase 5 — Architecture preparation

Status: NOT STARTED

---

## Phase 6 — Network resilience

Status: NOT STARTED

---

## Phase 7 — Performance + observability

Status: NOT STARTED

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
