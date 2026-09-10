# HANDOFF — Round 1 + Round 1.1 Corrective Pass

> Round 1 (items 2-14) + Round 1.1 (owner review corrective pass) COMPLETE.
> STOP FOR REVIEW — do NOT begin Phase A (shared-core extraction) without separate
> owner review/approval of this report, and do NOT begin the full main.py router
> split at all right now (owner decision: deferred until CRM work or real pain).

---

## Status snapshot

**Updated**: 2026-09-10 — Round 1.1 COMPLETE
**Branch**: `main`
**Round 1 START_SHA**: `16282016a785f9c7a1b8b31eb1929a62abe425d3`
**Round 1 FINAL_SHA**: `0877ff9ca34c77fd1c42384a223274d6de5b0657` (deployed as `2d27b7d` after docs commit)
**Round 1.1 FINAL_SHA**: `17d3cc0` (see `git log --oneline` for exact hash)
**Tests**: 638 passed, 1 skipped, 0 failed (Round 1 was 631; +7 Round 1.1 regression tests)
**Deployment status**: Round 1 (`2d27b7d`) is live in production. Round 1.1 fixes are
committed and pushed but **NOT YET DEPLOYED** — owner said "NO DEPLOY until reviewed"
for this corrective pass.

---

## Round 1.1 — owner review corrective findings, all addressed

Owner reviewed the Round 1 report and found the overall work solid but flagged it was
NOT "all 14 fully closed" — rated ~8/10. Six concrete gaps, all fixed in this pass:

| # | Finding | Fix | Commit |
|---|---------|-----|--------|
| 1 | **Most serious**: item 3 (invalid items_json → skip row) + item 6 (reconciliation via seen_plan_ids) interacted badly — a row present-but-invalid never reached `seen_plan_ids`, so reconciliation treated it as a *deleted* row and wrongly cancelled/source_deleted an otherwise valid, untouched plan. | Added `_raw_row_plan_id()` — extracts plan_id from the raw row before full validation, adds it to `seen_plan_ids` regardless of validation outcome. "Row present but invalid" is now distinguishable from "row truly absent." | `a1ef2f7` |
| 2 | `update_plan_fields()` (item 5) created amendments with `plan_version_before == plan_version_after` — not a real versioned change, breaks history reconstruction. | Now bumps `plan.version` and writes a `version_record` on every real field change, same convention as `update_plan_items()`. | `47bb606` |
| 3 | `update_plan_fields()` didn't support `object_id`, despite it being in the original item 5 requirement list (worker_ids/date/object_id/stage_key/status). | Added `object_id` parameter, wired into the `plan_sync.py` caller. | `47bb606` |
| 4 | Status field transition semantics (Sheet status edits) were correct by construction but undocumented/untested — risk of accidentally breaking the "never unpublish/destroy accepted history" invariant in a future change without noticing. | Audited: only `draft → published` is ever applied; every other status (accepted/in_progress/amendment_pending/cancelled/completed) is left untouched by Sheet status edits. Added regression tests locking this in. | `203ac51` |
| 5 | Staffing widget (item 13) read `shiftState` from team-plan but never displayed it — showed only the object name, not whether the worker is actually working/assigned/finished. | Now renders `"{object} · {Работает\|Назначен\|Завершил}"`, distinct `.hcw-working` CSS state for active shifts. | `17d3cc0` |
| 6 | Item 10 (unified risk engine) should not be described as "RED risk operationally complete" — no caller anywhere supplies `contract_finish_date`/`predicted_finish_date`, so RED is reachable in the function but never triggered in practice. | Already documented as an inline code comment in `main.py` (`_compute_risk_level` caller) from Round 1; reconfirmed here as an explicit, honest "known integration gap" — not fixed in this pass, no dates fabricated. | (no new commit — pre-existing comment stands, called out explicitly in this report) |

## Round 1.1 commits

```
a1ef2f7 fix: round 1.1 #1 — invalid Sheet row must not look deleted to reconciliation
47bb606 fix: round 1.1 #2+#3 — update_plan_fields gets real version bump + object_id support
203ac51 test: round 1.1 #4 — lock Sheet status transition semantics
17d3cc0 fix: round 1.1 #5 — staffing widget shows real shift status
```

## What was NOT changed in Round 1.1

- Item 10's RED risk tier remains an acknowledged integration gap (see #6 above) —
  intentionally not fixed here; would require adding a real contract-date data source,
  which is new functionality out of scope for a corrective bug-fix pass.
- No deploy performed for Round 1.1 (owner's explicit instruction: "NO DEPLOY until reviewed").
- No Phase A / shared-core extraction started — owner decision, separate approval gate.
- No full main.py router split — owner has deferred this to a later round (post-CRM
  or when a specific domain becomes a real bottleneck), per owner's stated roadmap:
  Round 1.1 → Phase A (shared-core only, no route moves) → UI/design round → staging +
  CI + real ASGI/E2E → PostgreSQL/service-repository → full 176-route split (only
  alongside CRM work or genuine pain).

## Verification performed

- Targeted tests run after each Round 1.1 fix, all green before commit.
- Full isolated suite run at the end: 638 passed, 1 skipped, 0 failed.
- `python3 -m py_compile` / `node --check` on every changed file.
- `git diff` reviewed before each commit.
- 7 new regression tests added, one per finding (finding #6 needed no new test —
  it's a documentation-only correction to how the report describes existing, already-
  tested behavior).

## READY FOR REVIEW

Round 1.1 corrective pass complete: all 6 owner-identified gaps addressed (5 code
fixes + 1 explicit documentation correction), tested, committed, pushed. NOT deployed
pending owner review, per explicit instruction. Next step after approval: Phase A
(shared-core extraction only — `backend/core/{config,paths,constants,permissions,
storage,time,limits}.py`, zero route moves, zero DTO changes, zero business-logic
changes) — full spec already provided by owner, ready to execute on approval.
