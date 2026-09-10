# HANDOFF — Round 1 Foundation Bug Fixes

> Round 1 (items 2-14) COMPLETE. Item 1 was already closed prior (commit 1628201).
> STOP FOR REVIEW — do NOT begin Round 2 (main.py extraction) without separate owner review.

---

## Status snapshot

**Updated**: 2026-09-10 — Round 1 COMPLETE
**Branch**: `main`
**START_SHA**: `16282016a785f9c7a1b8b31eb1929a62abe425d3`
**FINAL_SHA**: `0877ff9ca34c77fd1c42384a223274d6de5b0657`
**origin/main SHA**: `0877ff9ca34c77fd1c42384a223274d6de5b0657` (matches — pushed)
**Baseline tests**: 603 passed, 1 skipped
**Final tests**: 631 passed, 1 skipped, 0 failed

---

## Round 1 item status

| # | Item | Status | Commit |
|---|------|--------|--------|
| 1 | Multi-worker DailyPlan acceptance | CLOSED (prior) | 1628201 |
| 2 | Per-worker amendment UX | DONE | e2d7a6f |
| 3 | Sheets items_json validation | DONE | 69b5b57 |
| 4 | plan_id immutability (explicit required) | DONE | 332fb77 |
| 5 | Sheets field-change detection | DONE | 758918a |
| 6 | Sheet row deletion reconciliation | DONE | 4cce0f7 |
| 7 | Replan blocker schema (daily_plan_id) | DONE | c7dd80d |
| 8 | Replan amendments resolution | DONE | c7dd80d |
| 9 | Owner Today session matching | DONE | a30fc15 |
| 10 | Unified risk engine in replan | DONE | ceab09c |
| 11 | Diagnostics sync field naming | DONE | f36dadb |
| 12 | Dashboard business date (Berlin TZ) | DONE | c6276ff (+ regression fix e5ed33d) |
| 13 | Dashboard staffing widget rewire | DONE | f5ce33f |
| 14 | Contract store safety | DONE | 0877ff9 |

## What moved / changed intentionally

- `backend/main.py`: owner/matrix + replan endpoints now use `daily_plan_id` key
  consistently (was a live KeyError risk via `a["plan_id"]` bracket access);
  amendment lookups resolve via `dpl.get_pending_amendments()` instead of filtering
  on nonexistent `object_id`/`status` fields; owner/today session matching keyed on
  `(worker_id, object_id)` tuple instead of `worker_id` alone; replan risk calc now
  calls the shared `_compute_risk_level()`; diagnostics reads `last_sync_at`;
  contract store routed through `_safe_load_json`/quarantine.
- `backend/daily_plan_lib.py`: added `update_plan_fields()` (worker_ids/date/stage_key
  change detection + amendment routing, item 5) and `mark_plan_source_deleted()`
  (item 6); `get_today_plan_for_worker()` and `get_pending_plans_for_owner_today()`
  now actively exclude cancelled/source_deleted plans.
- `scripts/plan_sync.py`: `_row_to_plan_fields()` returns `None` (sync error) on
  malformed/non-list items_json and on missing/blank plan_id — no more silent
  `items=[]` overwrite, no more synthetic `object:date:stage` fallback identity;
  existing-plan branch now also calls `update_plan_fields()`; the previously-dead
  `seen_plan_ids` now drives end-of-run reconciliation for disappeared Sheet rows.
- `frontend/js/today-plan.js`: mandatory screen opens on pending amendments
  regardless of stale acceptance; renders БЫЛО/СТАЛО/ДОБАВЛЕНО/УДАЛЕНО diff;
  amendment-accept CTA calls the amendment-specific endpoint.
- `frontend/js/home.js`, `feed.js`, `checkin.js`: business-date logic uses
  `todayBerlin()`/`tomorrowBerlin()` instead of raw UTC `toISOString()`.
- `frontend/js/home.js`: home calendar widget now combines absence data with
  `/api/dashboard/team-plan` assignment data — a worker shows assigned/absent/free,
  not just absent/free as before.
- `frontend/app.html`: added `.hcw-assigned` CSS rule for the new tri-state.
- `tests/test_round1_foundation_fixes.py`: new file, one test class per item
  (items 2-14), 29 tests total. One pre-written test (item 13) was adjusted after
  implementation — its literal ban on any `/api/abwesenheit/all` call conflicted
  with correctly combining absence + assignment data; replaced with a check on the
  actual behavior the test's own docstring described (see commit f5ce33f message).

## What was NOT changed

- No `main.py` extraction / router splitting (Round 2 — separate owner approval
  required).
- No production deploy.
- No live Google Sheets writes — item 4 explicitly forbids a synthetic-id write-back;
  Round 1 stayed read-only toward Sheets throughout.
- No systemd config changes.
- Item 10's RED risk tier remains unreachable in practice: no caller anywhere in the
  codebase currently supplies `contract_finish_date`/`predicted_finish_date` — wiring
  an actual contract-date data source is new functionality, out of scope for a
  Round 1 bug-fix pass. Flagging for a future round.

## Known limitations / carried-over items

- Test coverage note (raised by owner earlier, not a Round 1 item): the item 1
  regression tests call library/route functions directly rather than through a real
  HTTP TestClient/ASGI stack, so they don't independently prove the full HTTP path.
  Not addressed in Round 1 — same direct-call pattern was kept for consistency with
  existing test file conventions (`test_foundation_completion.py` etc.), but a future
  round could add real ASGI-level coverage.
- No CI pipeline exists on this repo to independently confirm the full suite runs
  clean on a fresh checkout — verification here was manual, on the VPS, in an
  isolated `MINIAPP_DATA_ROOT`.

## Verification performed

- Targeted test(s) run after every individual item commit — all green before commit.
- Full isolated suite run at checkpoints: after item 6 (626 passed), after item 10
  (626 passed), after item 14/final gate (631 passed, 1 skipped, 0 failed).
- `python3 -m py_compile` on every changed `.py` file; `node --check` on every
  changed `.js` file — all clean.
- `git diff` reviewed before every commit.
- One regression caught and fixed immediately: item 12's edit left `now`/`tomorrow`
  variables referenced after their declarations were removed — caught before it
  reached a checkpoint, fixed in commit e5ed33d.
- `git log --oneline` since START_SHA: 15 commits (1 already-prior + 14 new).
- `git status --short`: clean.
- `git rev-parse HEAD` == `git rev-parse origin/main`: `0877ff9ca34c77fd1c42384a223274d6de5b0657`.
- Deployment status: NOT deployed (as instructed). Production still runs the
  pre-Round-1 code until a separate, explicit deploy is approved.

## READY FOR REVIEW

Round 1 (items 2-14) is complete, tested, committed, and pushed to `origin/main`.
Round 2 (splitting `backend/main.py` into routers) requires separate owner review
and approval before starting — not begun here.
