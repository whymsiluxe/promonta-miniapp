# HANDOFF — Round 1.2 Final DailyPlan Consistency Fix + Phase A (paused)

> Round 1.2 (2 owner-identified issues) COMPLETE. Phase A step 1 done (core/time.py),
> rest of Phase A PAUSED pending owner review of this report — do NOT continue Phase A
> or begin the full main.py router split automatically. NO deploy performed.

---

## Status snapshot

**Updated**: 2026-09-10 — Round 1.2 COMPLETE, Phase A step 1 of 6 done
**Branch**: `main`
**Round 1.1 FINAL_SHA**: `4d8c113`
**Round 1.2 / Phase A step 1 FINAL_SHA**: `d4878ad`
**Tests**: 644 passed, 1 skipped, 0 failed (was 638 at Round 1.1; +6 net: 2 field_changes
tests, 4 accepted-snapshot tests)
**Route count**: 176 (unchanged — confirmed before and after every commit)
**Deployment status**: NOT deployed. Production still runs the Round 1 code
(`2d27b7d`). Round 1.1 + Round 1.2 + Phase A step 1 are committed/pushed only.

---

## Round 1.2 — owner review of Round 1.1, two remaining issues, both fixed

| # | Finding | Fix | Commit |
|---|---------|-----|--------|
| 1 | Amendment UI didn't render `diff.field_changes` (object/date/worker/stage changes from `update_plan_fields()`) — fell through to "Нет деталей изменений". | `today-plan.js` now renders ОБЪЕКТ/ДАТА/РАБОТНИКИ/ЭТАП sections with old→new values. Raw IDs shown immediately, resolved to real names async via `/api/objects` + `/api/workers` (same pattern as the existing `_resolveBarObjectName` helper). | `964ffc0` |
| 2 | **Most serious**: `update_plan_fields()` mutated a plan's `object_id`/`date`/`assigned_worker_ids`/`stage_key` in place even after acceptance. Check-in Finish compared the *current* (possibly since-mutated) plan against the session's recorded object/date — a Sheets edit made after a worker started their shift could silently skip `apply_daily_execution` for an otherwise valid, already-completed shift. | `accept_plan()` now freezes `object_id`/`date`/`stage_key`/`assigned_worker_ids`/`plan_version` into an `accepted_context_snapshot` on the acceptance record — never rewritten afterward. `checkin_finish` validates against that frozen snapshot (via the session's `daily_plan_acceptance_id`) instead of the live plan. Old acceptances without a snapshot fall back to the previous live-plan comparison (documented conservative fallback, no fabricated history). | `d4878ad` |

**Edge case #3 from the original review** (plan_id column vulnerable to accidental manual erasure in the Sheet) — owner explicitly said "not a blocker now," not fixed in this pass, no action taken.

## A process error found and corrected mid-session

The Phase A step 1 commit (`77b5082`) was supposed to include the `backend/main.py`
changes (the actual `business_now()` extraction + import fallback) but the `git add`
command for that commit only listed `backend/core/` and the test file — `main.py`'s
extraction sat as an **uncommitted local change** the whole time, even though it was
on disk and tests were passing against it. Caught this while investigating an
unrelated git-diff oddity, before it could compound with later changes. Corrected
with an explicit follow-up commit (`67e5103`) that states plainly what happened —
no code content changed, only the missing commit was made. Lesson: always confirm
`git status --short` shows a clean tree immediately after every commit, not just
before it.

## Phase A — status: step 1 of 6 done, rest paused

Per owner's approved ordering (Round 1.2 → Phase A → UI/design round → staging+CI+E2E
→ PostgreSQL → full router split, only alongside CRM or real pain):

- **Done**: `backend/core/time.py` — `business_now()` extracted (the one true leaf
  with zero main.py coupling). `business_today()`/`business_today_str()`/
  `_today_berlin_str()` deliberately STAY in main.py, calling `business_now` by
  module-local name, because tests monkeypatch `patch.object(backend, 'business_now',
  ...)` and need that same patched name resolved at call time — moving them too would
  make them silently resolve `core.time`'s own unpatched `business_now` instead.
- **Not started**: `core/config.py`, `core/paths.py` (~40 file-path constants, zero
  external importers per the dependency-mapping investigation — safe but mechanical),
  `core/constants.py` + `core/limits.py`, `core/storage.py` (clean extraction per the
  map, but `CRITICAL_JSON_PATHS` must stay a mutable module attribute populated at
  end-of-file — real order-of-definition trap if done carelessly), `core/permissions.py`
  (deepest chain — `get_current_user` → `_notify_owner_new_user` → `send_telegram_message`
  is the one upward edge that needs a small `core/telegram.py` extraction first to avoid
  a circular import).
- A full dependency map (file:line references, 10 flagged risks R1-R10, safe extraction
  order) was produced by a research pass before touching any code — available in this
  session's history if the continuation needs it; not duplicated into this file to keep
  it a status report, not a design doc.

## Verification performed (Round 1.2 + Phase A step 1)

- Targeted tests after each fix, full isolated suite run at the end: 644 passed,
  1 skipped, 0 failed.
- `python3 -m py_compile` on every changed `.py` file, `node --check` on `today-plan.js`.
- Route count confirmed unchanged (176) after every commit.
- `git diff` reviewed before each commit; `git status --short` confirmed clean after
  each one (this check is what caught the Phase A commit gap above).
- 6 new regression tests: 2 for field_changes rendering, 4 for the accepted-context
  snapshot (including a sanity check proving the OLD live-plan comparison logic would
  actually fail in the exact scenario being fixed — not just that the new logic passes).

## READY FOR REVIEW

Round 1.2 complete: both owner-identified issues fixed, tested, committed, pushed.
Phase A step 1 (core/time.py) also done and verified. NOT deployed. Do NOT continue
Phase A automatically — steps 2-6 (paths/constants/limits/storage/permissions) need
separate owner go-ahead per the "one small step, verify, report" cadence already
established. Do NOT begin the full main.py router split.
