IMPORTANT ADDENDUM BEFORE FINAL STATUS

Reviewer can now see pushed main through 850f84b.

Phase 2 must NOT be considered closed with the current
"7 documented limitations".

Several of those limitations are original Production Control requirements
and must be fixed BEFORE READY FOR OWNER REVIEW.

After completing the current Phase 7 observability/performance tasks,
execute a focused FOUNDATION COMPLETION section.

NO DEPLOY.

==================================================
P0 — REAL SHEETS → DAILYPLAN SYNC
==================================================

Current scripts/plan_sync.py still contains:

"stub — Phase 2 implementation deferred"

This is NOT acceptable as a documented limitation.

Implement real:

Google Sheet План_дня
→ local DailyPlan create/update/version/amendment.

Required:

Sheet row added
→ DailyPlan appears.

Sheet row edited before acceptance
→ DailyPlan version changes.

Sheet row edited after acceptance
→ immutable accepted snapshot stays
→ amendment/new version is created
→ Worker must acknowledge appropriately.

Sheet row deleted after acceptance
→ historical accepted snapshot/fact survives.

Use the already-approved План_дня schema.

Do not invent a second planning store.

Add mocked Sheets integration tests.

==================================================
P0 — PER-WORKER AMENDMENT ACK
==================================================

Current amendment has one:

worker_acknowledged_at

for the entire plan.

This is invalid for multi-worker plans.

Change to per-worker acknowledgement, e.g.:

acknowledged_by: {
  worker_id: timestamp
}

or equivalent normalized records.

Scenario:

plan workers = A,B

new version/amendment

A acknowledges
B must still see amendment pending.

Add schema migration/backward compatibility.

Add tests.

==================================================
P0 — SERVER TRUSTED DAILYPLAN/CHECKIN LINK
==================================================

Do not trust client-supplied DailyPlan identifiers.

Validate server-side for Start AND Finish where applicable:

plan exists
worker assigned
object matches
business date matches
acceptance belongs to worker
acceptance belongs to plan
accepted version matches.

A malicious/incorrect:

plan_id
acceptance_id
version
object_id

must not contaminate execution/productivity data.

Add negative tests.

==================================================
P0 — DURABLE FINISH PROJECTOR OUTBOX
==================================================

Current Finish may commit Check-in and then fail applying DailyExecution.

Do not lose:

execution
carryover
productivity
fact mirror.

Implement deterministic durable event:

daily_execution:<session_id>

Check-in commit
→ pending projector event
→ apply_daily_execution
→ mark applied.

On failure:
event remains pending.

Retry safely on startup/timer/manual maintenance path.

Idempotent by session_id.

Valid Check-in must still succeed even if projector temporarily fails.

Add failure + retry test.

==================================================
P1 — SHARED INTER-PROCESS STORE TRANSACTION
==================================================

plan_sync.py currently has its own:

_load_plan_store()
_save_plan_store()

This must not remain as an independent read-modify-write implementation.

FastAPI and plan_sync are separate processes.

Use ONE shared DailyPlan transaction primitive:

fcntl/file lock
→ load latest
→ mutate
→ atomic replace/fsync
→ unlock.

Both API and sync worker use the same storage implementation.

Corrupt store must fail safely/quarantine,
never silently become an empty store.

==================================================
P1 — CONTRACT RED RISK
==================================================

Current RED is still documented as not implemented.

Implement only when dates exist:

predicted_finish_date > contract_finish_date
→ RED

internal_target threatened
→ ORANGE

carryover with remaining buffer
→ YELLOW

normal
→ GREEN.

No contract date:
do not fake RED.

Return explicit unknown/not_available state if required.

Add tests.

==================================================
P1 — TEAM PRODUCTIVITY
==================================================

Current auto productivity defaults crew_size=1.

Fix.

If shared plan/item has multiple workers and individual contribution
is unknown:

record crew observation,
NOT exact solo worker productivity.

Do not update an individual's strong effective rate as if he alone
produced the whole quantity.

Solo work:
individual observation allowed.

Explicit contribution:
individual observation allowed with confidence/source.

Pause time must remain subtracted from productive hours.

Add 2-worker tests.

==================================================
RE-REPORT THE 16 REQUIREMENTS
==================================================

After fixes, print ALL 16 items again.

For each:

DONE
LIMITATION
BLOCKED

But:

Sheets → DailyPlan sync
per-worker amendment ack
server-trusted linkage
durable Finish outbox

must NOT be marked as harmless limitations.

If any of these four remain missing:

FINAL STATUS = NOT READY.

==================================================
FULL VERIFICATION
==================================================

Run all tests only with isolated test environment.

Then:

pytest
node --check all JS
py_compile changed Python
HTML validation

Confirm:

git status clean
HEAD == origin/main

Push all commits.

NO DEPLOY.

STOP.
