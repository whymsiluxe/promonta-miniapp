# Session handoff — autonomous execution 2026-09-08 (EXECUTION_PLAN.md)

## Status

**Phase 0** (test isolation + incident root cause fix): COMPLETE  
**Phase 1** (security/correctness fixes): COMPLETE  
**Phase 2** (Production Control re-verification, 16 items): NOT STARTED  
**Phase 3** (Navigation restructure): NOT STARTED  
**Phase 4** (Worker glove-UX fixes): NOT STARTED  
**Phase 5** (Architecture preparation): NOT STARTED  
**Phase 6** (Network resilience — offline cache): NOT STARTED  
**Phase 7** (Performance + observability): NOT STARTED  

Tests: 557 passed, 1 skipped. Branch: main.

## Resumption note

Read `docs/EXECUTION_PLAN.md` and `docs/AUTONOMOUS_EXECUTION_RULES.md` before
resuming. The rules file mandates:
```bash
export PROMONTA_ENV=test
export MINIAPP_DATA_ROOT=$(mktemp -d)
test "$MINIAPP_DATA_ROOT" != "/home/promonta/agent/miniapp" || { echo 'REFUSING'; exit 1; }
```
before ANY pytest invocation. No production deployment without explicit owner instruction.

## What Phase 0 fixed (2026-09-08 incident root cause)

Watchdog loop was running tests with no `MINIAPP_DATA_ROOT` isolation, writing to production
`roles.json`. Three-layer fix:
1. `tests/conftest.py` — module-level env vars set before `import main` (import-time guard).
2. `backend/main.py` — RuntimeError at import if `PROMONTA_ENV=test` + prod DATA_ROOT.
3. `tests/test_worker_calendar_birthday.py` — env set at top before `import main as backend`.

## What Phase 1 fixed (security/correctness)

- **Budget percent column drift**: Live Sheets column is `'потрачено в % от бюджета'`;
  `objekte_lib.py` was using `'% бюджета'`. Added `get_budget_percent()` accessor in
  objekte_lib, expanded `BUDGET_FIELDS` in main.py to cover all three historical aliases.
- **Chat attachment crash**: `m.get('attachment', {})` → `(m.get('attachment') or {})` —
  explicit `None` attachment on plain-text messages caused AttributeError.
- **Task file race condition**: `create_task`/`update_task_status` now use
  `_lock_for(TASKS_FILE)` + `_load_tasks()`/`_save_tasks()` (old `update_json_transaction`
  bypassed locks and test mocks).
- **Angebot ACL**: `require_angebot_access` dependency enforces owner-only. Dead `manager`
  branch removed (set_role hard-rejects manager assignment anyway).
- **Module identity fix (test)**: `tests/test_phase1_security.py` uses
  `backend._load_repo_objekte_lib()` instead of `import objekte_lib` to get the repo's copy
  (main.py inserts `/home/promonta/agent` into sys.path[0], which would shadow the repo copy).

## Next step: Phase 2 — Production Control re-verification

Verify each of the 16 Production Control items (Rounds 1–7 in EXECUTION_PLAN.md) still works
correctly end-to-end. See `docs/EXECUTION_PLAN.md` §Phase 2 for the full item list.
