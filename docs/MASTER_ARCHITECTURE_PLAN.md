# Master Plan Round 0 + Round 1 — Foundation Bug Fixes

## Context

Owner supplied a full master technical architecture plan (stabilization → modular
monolith → staging/CI/E2E → PostgreSQL-ready core → future CRM/mobile). The plan is
explicit that architecture rounds (splitting `backend/main.py`, ~8650 lines / 176
routes) must NOT start until Round 1 ("Foundation Bug Fixes") is done, reviewed, and
approved. A previous session already burned significant account usage running an
aggressive-retry background audit with zero output — the owner explicitly demanded
this round run "maximally economically." Two of Round 1's 14 items (item 1,
multi-worker acceptance) were already fixed and pushed earlier today (commits
`12eda32`, `1628201`) in direct response to owner findings — verified closed by
investigation below, not re-done.

Two parallel Explore agents read the actual current code (not the stale
`docs/ARCHITECTURE_REFACTOR_BACKLOG.md`, which itself turned out to be inconsistent
with reality on 2 items) and confirmed, with file:line evidence, the exact current
state of all 14 Round 1 items plus the surrounding conventions (deploy script, test
file naming, existing safe-store pattern, existing risk-engine function). This plan
is built entirely on that evidence.

## Investigation findings — what's real vs. what's already fixed

**Item 1 (multi-worker acceptance) — CLOSED, do not touch.** All four layers
(`daily_plan_lib.accept_plan()`, the HTTP endpoint, `get_today_plan_for_worker()`
STATUS_PRIORITY, frontend `_shouldShowPlanScreen()`) are consistent as of HEAD
`1628201`. 603 tests passing, 1 skipped, clean working tree except one untracked
`docs/AUDIT_TASK.md` (leftover from the aborted audit session — delete it as part of
Round 0 cleanup, it's not part of the codebase).

**Items 2–14 — all confirmed real, with exact locations:**

| # | Item | File:line | Real problem confirmed |
|---|------|-----------|------------------------|
| 2 | Per-worker amendment UX | `main.py:7906` calls `get_pending_amendments(plan["id"])` without `worker_id` | A worker who already acked an amendment still sees it pending if a co-worker hasn't acked. Structured diff (`_compute_diff`) exists and is stored but never rendered — frontend only shows a bare badge. |
| 3 | Sheets план_дня validation | `plan_sync.py:215-220` | Malformed `items_json` silently becomes `items=[]` and **overwrites a valid DailyPlan** via `update_plan_items(..., new_items=[])`. No schema validation, no per-row error reporting. |
| 4 | plan_id immutability | `plan_sync.py:206` | `plan_id` falls back to `f"{object_id}:{date_str}:{stage_key}"` when no explicit sheet column exists — changing date/stage/object silently orphans the old plan and creates a disconnected new one. |
| 5 | Sheets field-change detection | `plan_sync.py:291` | Only `items` are hash-compared; changes to `worker_ids`/`date`/`object_id`/`stage_key`/`status` on an existing plan are never detected or applied. |
| 6 | Sheet row deletion semantics | `plan_sync.py:259-267` | `seen_plan_ids` is built but never read again — dead code, zero reconciliation when a sheet row disappears. |
| 7 | Replan blocker schema | `main.py:8451` reads `b.get("plan_id")`; every blocker record actually uses key `"daily_plan_id"` | `plans_with_blockers` is always empty in `/api/daily-plan/replan/{object_id}`. Worse: `/api/daily-plan/owner/matrix` (`main.py:8380,8388`) uses **bracket access** `a["plan_id"]` on records that only have `daily_plan_id` — this is a live `KeyError` risk (likely 500s) once any acceptance/amendment exists in range. |
| 8 | Replan amendments | `main.py:8419-8420` filters `a.get("object_id")` | Amendment records have no `object_id` field and no `status` field at all — this filter always returns empty, so amendment-driven YELLOW risk in replan can never fire. |
| 9 | Owner Today session matching | `main.py:8046-8052,8062` | Sessions keyed by `worker_id` only, no `object_id`/`daily_plan_id` cross-check — a worker with two same-day object shifts can get the wrong session attributed to a plan row. (Note: the *write* side, `checkin_start()`, already validates this correctly — only the owner-facing read/aggregation side doesn't.) |
| 10 | Unified risk engine | `_compute_risk_level()` exists at `main.py:8309`, used once at `:8071` | Replan (`main.py:8479-8483`) has its own **independent inline 3-tier calc** (no RED tier), not calling the shared function — and its inputs are broken anyway by items 7/8, so it's nearly always green/yellow regardless of real state. |
| 11 | Diagnostics sync field naming | writer: `plan_sync.py` writes `last_sync_at`/`plan_dnya_synced_at`; reader: `main.py:946` reads `last_synced_at` (extra `_ed`, never written) | Diagnostics always falls through to `'dailyplan_sync': 'file_exists_no_sync'` even when sync works perfectly. |
| 12 | Dashboard business date (timezone) | `home.js:159,162,1037`, `feed.js:352`, `checkin.js:574` | All use raw `new Date().toISOString()` (UTC) instead of the existing, correct `shared.js::todayBerlin()`/`tomorrowBerlin()`. No backend Python equivalent exists either (only a comment referencing the JS helper) — not needed for this item, but worth noting for future backend date work. |
| 13 | Dashboard staffing widget | `home.js:151-198` (`_loadHomeCalendarWidget`) fetches only `/api/abwesenheit/all`+`/api/workers` | Shows every non-absent worker as "Свободен" regardless of real assignment/work status. **A correct, already-built endpoint exists**: `/api/dashboard/team-plan` (`main.py:2693`, joins assignments+checkin_meta+Sheets, uses correct Berlin date) — it's just wired into a different widget (`home.js:1393`, "Команда → План"), not into the compact home calendar widget. |
| 14 | Contract store safety | `main.py:8508-8522` (`_load_contract_store`/`_save_contract_store`) | Bespoke raw `json.load()` with silent `except JSONDecodeError: return {"contracts": {}}` — bypasses the existing, already-built `CRITICAL_JSON_PATHS`/`_safe_load_json`/quarantine mechanism entirely, even though `CONTRACT_INGEST_STATE_FILE` is already registered as critical (`main.py:8650`). Corruption silently wipes the visible contract list with zero trace. |

**Existing conventions to reuse, not reinvent** (confirmed by investigation):
- Safe-store pattern: `CRITICAL_JSON_PATHS` set + `_safe_load_json()` + `_quarantine_corrupt_json()` + `CorruptJsonError` exception handler (`main.py:162-230`, `:466`). Adding contract-store safety (item 14) is a matter of routing `_load_contract_store`/`_save_contract_store` through this existing machinery, not building new quarantine logic.
- `_compute_risk_level()` (`main.py:8309`) is the one correct 4-tier risk function — item 10's fix is to make replan call it (after fixing items 7/8's key bugs so its inputs are real) instead of keeping its own inline calc.
- Berlin date helpers already exist in `frontend/js/shared.js:166,170` — item 12 is a search-and-replace of the wrong pattern in 3 files, not new code.
- Test file naming: round/session-scoped fixes go in a new `tests/test_round1_foundation_fixes.py` (matching precedent: `test_round7_hardening.py`, `test_foundation_completion.py`), not scattered into feature files — keeps this round's regression tests reviewable as one unit.
- `docs/HANDOFF.md`'s status snapshot is 8 commits stale (points at `f96686f`, HEAD is `1628201`) — Round 0 updates it as part of baseline recording, following the same doc-update convention as commit `432f0f7`.

## Approach

Execute via a single bounded autonomous session on the VPS (`systemd-run`, same
pattern proven to work for Phase 0-7 and the Foundation Completion round), NOT the
aggressive-retry watchdog pattern used for yesterday's failed audit. Concretely:

- **One `systemd-run` launch**, generous timeout, no auto-restart loop by default.
- If it hits the usage limit mid-round: stop cleanly, leave `docs/HANDOFF.md` accurate,
  end the process. A bounded watchdog (max 2-3 restarts total, checked against a
  restart-count file, self-disabling once Round 1 reports done) may retry — explicitly
  NOT an unconditional 10-minute-interval infinite loop like yesterday's.
- Task instructions embed the full evidence table above so the session does not need
  to re-discover any of this — it goes straight to fixing, using the file:line
  references already gathered, saving significant token/API usage versus a fresh
  from-scratch audit.
- **One item, one commit — but tiered test economy, not 13 full suite runs.** Owner
  chose strict per-item commit granularity (even for the logically-coupled 7+8+9+10
  cluster) but explicitly flagged that running the full 603+ test suite after each of
  13 items is expensive and contradicts the "maximally economical" mandate. Final
  agreed tiering:
  - **Per item**: run only the targeted/focused regression test(s) for that specific
    item (e.g. `pytest tests/test_round1_foundation_fixes.py -k item_N` or the
    relevant existing test file), plus `py_compile`/`node --check` on changed files —
    not the full suite. Commit once these pass.
  - **Full isolated suite run** at these checkpoints only: after item 6 (end of block
    2-6), after item 10 (end of block 7-10), after item 14 (end of block 11-14), and
    once more at the final Round 1 gate before writing the report.
  - **If any focused test OR any full-suite checkpoint run fails**: STOP and
    investigate before continuing — do not proceed to the next item or the next block
    with a known failure.
  - Add regression tests per item into `tests/test_round1_foundation_fixes.py` (one
    test class or clearly-labeled test group per item, so the file stays organized by
    item number even though commits are separate).
- No production deploy. No Google Sheets tab creation/modification. No systemd config
  changes. Round 1 only — do not begin `main.py` extraction (Round 2+).
- Owner's report-format requirement is embedded verbatim in the task so the final
  output follows: ROUND / START SHA / FINAL SHA / changed files / what moved / what
  behavior changed intentionally / what was NOT changed / tests added / full test
  result / JS syntax result / Python compile result / known limitations / unexpected
  findings / git status / origin/main SHA / deployment status / READY FOR REVIEW, then
  STOP.

## BEFORE EXECUTION — REQUIRED PLAN CORRECTIONS (owner review, second pass)

These three corrections supersede the corresponding entries in "Fix plan per item"
below — read them first, they change the required behavior, not just the wording.

**1. Item 2 — amendment UX.** Passing `worker_id` to `get_pending_amendments()` is
not enough on its own. A worker may already hold an acceptance for a prior plan
version, and Today's mandatory-screen gate is typically `!data.acceptance` — so a
worker with an old acceptance would still never see the amendment screen even after
the backend fix. Required: pending-amendment display must NOT be gated by
`!data.acceptance`. If `pending_amendments` for THIS worker exist, the Worker Today
amendment screen must open regardless of any older acceptance. Render the existing
diff (БЫЛО / СТАЛО / ДОБАВЛЕНО / УДАЛЕНО). The CTA ("ПОНЯТНО — ПРИНЯТЬ ИЗМЕНЕНИЯ")
must call `POST /api/daily-plan/{plan_id}/amendments/{amendment_id}/accept` — not the
plain accept endpoint. After Worker A acknowledges, A must stop seeing it pending;
Worker B must keep seeing it pending until B acknowledges. Add frontend/API
regression coverage for exactly this two-worker sequence.

**2. Item 4 — plan_id semantics.** Round 1 is READ-ONLY toward production Google
Sheets (the master plan explicitly forbids Sheets writes without separate owner
approval) — so "generate and persist a stable ID back to a tracking field" is
disallowed, full stop, not just deprioritized. Required semantics instead: an
explicit `plan_id` column value is mandatory for a Plan_дня row to be publishable.
Missing/blank `plan_id` → validation error, recorded as a sync error, and the row
does NOT create/update/publish any DailyPlan. No synthetic `object_id:date:stage_key`
identity is used for publishable rows at all — remove that fallback rather than keep
it as a secondary path.

**3. Item 6 — cancelled/source-deleted read-side behavior.** Writing
`cancelled`/`source_deleted` status is not sufficient by itself — the read paths that
select a worker's active plan currently pick any same-day plan for that worker and
sort by status, with unknown statuses still falling through as a candidate (per
`STATUS_PRIORITY.get(p["status"], 99)` — 99 is a low sort priority, not an exclusion).
Required: a `cancelled`/`source_deleted` plan must NOT appear as an active Worker
Today plan, must NOT be acceptable by a worker, and must NOT appear as an active row
in Owner Today — it must be actively excluded from those candidate lists, not merely
deprioritized. The historical record must remain queryable for audit/history through
whatever existing history-access path applies. For accepted/started/executed plans:
never cancel destructively — mark `source_deleted`/`source_status=deleted` and
preserve the accepted snapshot/execution/carryover/fact history exactly as item 6
already specifies. Add regression tests covering: a cancelled plan is excluded from
`get_today_plan_for_worker()`'s candidates, excluded from Owner Today's active rows,
and still reachable via history.

## Fix plan per item (for the task instructions)

1. **Skip — already closed.** Verify once more via `git log`/current code read (cheap,
   avoids blind trust), do not re-implement.
2. Pass `worker_id` into `get_pending_amendments()` call at `main.py:7906` (function
   already supports it). Render the existing stored `diff` (БЫЛО/СТАЛО/ДОБАВЛЕНО/
   УДАЛЕНО) in the frontend amendment badge instead of the bare text badge. **See
   "BEFORE EXECUTION — REQUIRED PLAN CORRECTIONS" #1 above — the mandatory-screen
   gate must not depend on `!data.acceptance`; it must open whenever pending
   amendments exist for this worker, and the CTA must call the amendment-accept
   endpoint, not the plain accept endpoint.**
3. Add structured validation in `_row_to_plan_fields()` (plan_sync.py): on
   `items_json` parse failure, do NOT set `items=[]` and do NOT call
   `update_plan_items`; instead record a sync error (row number + reason) in sync
   state and leave the existing valid plan untouched. Prefer a small
   dataclass/Pydantic-style structural check over ad-hoc dict access, per the plan's
   explicit instruction, but keep it proportionate — this is 383-line script, not a
   framework.
4. **Per "BEFORE EXECUTION" #2 — Sheets-write-back option is disallowed.** Require an
   explicit, non-blank `plan_id` sheet column value as a hard precondition for
   publishing a Plan_дня row. Missing/blank `plan_id` → validation error, recorded as
   a sync error, and the row must NOT create/update/publish any DailyPlan. Remove the
   `f"{object_id}:{date_str}:{stage_key}"` synthetic-identity fallback entirely for
   publishable rows — do not keep it as a secondary path.
5. Extend the change-detection in `_process_daily_plan_rows()` beyond items-only hash
   to also compare `worker_ids`/`date`/`object_id`/`stage_key`/`status`; route
   post-acceptance relevant changes through the existing amendment path, not a
   destructive overwrite.
6. Implement reconciliation: after processing all sheet rows, compare against
   previously-known plan IDs for that sync run. Draft/never-accepted plans whose row
   disappeared → mark cancelled. Accepted/started/executed plans → never delete
   history; mark `source_deleted=true` (or `source_status=deleted`) and keep the
   accepted snapshot/execution/carryover/fact history intact. **Per "BEFORE
   EXECUTION" #3 — writing the status is not sufficient by itself: also update
   `get_today_plan_for_worker()`'s candidate filter (and any Owner Today active-row
   filter) to actively EXCLUDE `cancelled`/`source_deleted` plans, not merely
   deprioritize them via STATUS_PRIORITY's fallback-to-99 behavior. History remains
   reachable through the existing history-access path, whatever that is — verify
   which function that is during implementation, don't assume.**
7. Fix `main.py:8451` to read `b.get("daily_plan_id")` (matching how blockers are
   actually stored) instead of `b.get("plan_id")`. Fix `main.py:8380,8388` bracket
   access `a["plan_id"]` → `a.get("daily_plan_id")` to eliminate the live `KeyError`
   risk. Prefer routing through a domain helper (e.g.
   `get_open_blockers_for_object(object_id)` in daily_plan_lib.py) instead of
   reimplementing store access inline in the endpoint, per the plan's explicit
   preference.
8. Fix `main.py:8419-8420` to resolve amendments correctly: object → plans (via
   existing `get_plan`/store lookups) → amendments (via `daily_plan_id`), instead of
   filtering on a nonexistent `object_id`/`status` field on amendment records.
9. Extend Owner Today session matching (`main.py:8046-8062`) to key on
   `worker_id`+`object_id`+`business_date`(+`daily_plan_id` where available), not
   `worker_id` alone — mirroring the validation rigor `checkin_start()` already applies
   on the write side. Add a multi-session-same-day test.
10. After fixing items 7/8 (so replan's inputs are real), make the replan endpoint
    call the existing `_compute_risk_level()` instead of its own inline 3-tier calc,
    passing `contract_finish_date`/`internal_target_date` where available so RED
    becomes reachable in both places, not just owner/today.
11. Standardize on ONE sync-timestamp field name end-to-end (plan_sync.py writer and
    main.py:946 reader currently disagree — `last_sync_at`/`plan_dnya_synced_at`
    vs. `last_synced_at`). Pick whichever plan_sync.py already writes (avoid
    unnecessary rename churn) and fix the reader to match.
12. Replace `new Date().toISOString().split('T')[0]` / `.slice(0,10)` with
    `todayBerlin()` (or `tomorrowBerlin()` where appropriate) in exactly the three
    confirmed live files: `home.js:159,162,1037`, `feed.js:352`, `checkin.js:574`.
    Do not touch `.bak-*` files (dead) or launch a wider unrelated sweep, per the
    plan's explicit "search only in touched files, no unrelated global refactor."
13. Rewire `_loadHomeCalendarWidget()` (home.js:151-198) to consume the existing,
    already-correct `/api/dashboard/team-plan` endpoint (main.py:2693) instead of the
    bare `/api/abwesenheit/all`+`/api/workers` combination — reuse, do not build a
    second scheduling backend, per the plan's explicit instruction.
14. Route `_load_contract_store()`/`_save_contract_store()` (main.py:8508-8522)
    through the existing `_safe_load_json()`/quarantine mechanism instead of raw
    `json.load()`. Confirm `CONTRACT_INGEST_STATE_FILE` (already in
    `CRITICAL_JSON_PATHS`) is in fact the file these functions read/write (verify, the
    investigation flagged this needs a final confirmation) — if the actual contract
    data file differs from the ingest-state file, add the correct path to
    `CRITICAL_JSON_PATHS` too.

## Verification

- After EACH of the 14 items individually (strict one-item-one-commit, no grouping):
  run only the focused/targeted regression test(s) for that item, plus
  `python3 -m py_compile` on every changed `.py` file and `node --check` on every
  changed `.js` file. Commit once these pass.
- Run the FULL isolated test suite
  (`export PROMONTA_ENV=test && export MINIAPP_DATA_ROOT=$(mktemp -d) && .venv/bin/python3 -m pytest tests/ -q`)
  only at these checkpoints: after item 6, after item 10, after item 14, and once
  more at the final Round 1 gate. Confirm 603+ passing (baseline), 0 new failures at
  each checkpoint.
- If any focused test or any full-suite checkpoint fails: STOP and investigate before
  continuing to the next item/block — do not proceed with a known failure.
- `git diff` review before each commit: confirm no unintended behavior change beyond
  the specific item being fixed.
- Final: `git log --oneline` since START_SHA, `git status --short` (must be clean),
  `git rev-parse HEAD` vs `git rev-parse origin/main` (must match after push).
- Delete the stray `docs/AUDIT_TASK.md` (leftover from the aborted audit run) as part
  of Round 0 cleanup — it's not part of the codebase and has no owner.
- Produce the report in the owner's exact requested format, end with **READY FOR
  REVIEW**, and stop — do not begin Round 2 (main.py extraction) automatically.
