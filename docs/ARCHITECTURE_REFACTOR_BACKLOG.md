# Architecture Refactor Backlog

Recorded after the 2026-09-08 recovery + UX round.  
These are recommended future extraction slices — **not work done in this round**.  
Owner decision: no mass extractions until this release is manually verified working in Telegram.

---

## Backend — `backend/main.py` (~7600 lines, one file)

### Recommended domain splits (future rounds)

| Domain | Routes to extract | Notes |
|---|---|---|
| Auth / session | `/api/session`, `get_role`, HMAC validation | Stable, low-change — good first extract |
| Objects | `/api/objects/*` | Depends on objekte_lib.py; extract together |
| Workers | `/api/workers/*`, `/api/roles/*` | Worker profiles, assignments |
| Checkin | `/api/checkin/*`, `/api/session/*` | Finish wizard, checkin_meta |
| Feed | `/api/feed/*`, photo upload/gallery | Could become its own service later |
| Chat | `/api/chat/*` | Largest independently-testable domain |
| Production Control | `/api/daily-plan/*`, daily_plan_lib.py | Already partially in its own lib |
| Contracts | `/api/contracts/*`, `/api/angebot/*` | Angebot, Rechnung generation |
| Defects/Mängel | `/api/mangel/*` | mangel_lib.py already extracted |

### Known private-function leakage (low priority)

`apply_daily_execution` in `main.py::checkin_finish` currently calls
`dpl._load_store()` directly (a private function). Should be wrapped in a public
`dpl` method to maintain encapsulation. Only the routes this plan touches need
immediate cleanup — full sweep is a separate round.

### Known data issues (documented, not fixed in this round)

- **Sheets Plan_дня sync**: DailyPlan store writes do NOT sync to Google Sheets
  (`план_дня` tab). Comment in `main.py:7954` explicitly says "без Sheets-синка".
  Design: local JSON store is the source of truth for historical execution facts;
  Sheets is future/planning source. Sheets sync would require a write-back path
  (create `plan_дня` tab row per execution). Tracked as a future feature, not
  a current bug.
- **Durable Finish outbox**: No write-ahead log or retry queue for DailyPlan
  executions. `apply_daily_execution` writes directly and is idempotent by
  session_id, but if the process crashes mid-write, no recovery mechanism exists
  beyond idempotent retry. At current scale (single-process, local JSON), acceptable.
  Revisit if Sheets sync is added (then the outbox becomes load-bearing).
- **Contract RED risk**: `main.py:8095` comment: "RED is reserved for genuine
  contract-date risk (not implemented yet — returns ORANGE at most)". Requires
  `contract_finish_date` field in the contract store. Not implemented.
- **Corrupt DailyPlan store quarantine**: `daily_plan_lib.py::_load_store()` re-raises
  `JSONDecodeError` expecting `main.py` to handle via its CorruptJsonError mechanism.
  Verified: the main stores (roles, checkin_meta, tasks) have quarantine; the
  DailyPlan store relies on the same main.py path to trigger it. Test coverage in
  `test_release_audit3.py` verifies main-path quarantine. No separate quarantine
  needed in daily_plan_lib.py.

### Known accuracy issues (documented, not fixed in this round)

- **Team productivity crew_size=1**: `daily_plan_lib.py::auto_record_execution_productivity()`
  defaults `crew_size=1` when auto-recording from execution results. Multi-worker
  shifts are recorded as single-worker productivity. Fix: pass actual crew_size
  from the plan's `assigned_worker_ids` count or from the execution. Medium effort,
  requires coordinating crew attribution across simultaneous sessions.
- **Per-worker amendment acknowledgment**: Amendment ack is a single `worker_acknowledged_at`
  boolean, not a per-worker map. For plans with N workers, the first to acknowledge
  clears the amendment state for all. Fix: change schema to `acknowledged_by: dict[worker_id → timestamp]`
  and require all assigned workers to ack. Schema migration needed.
- **Server-side DailyPlan validation in checkin_finish**: `checkin_finish` accepts
  client-supplied `daily_plan_id` without verifying the worker is assigned to that
  plan. Fix: call `dpl.get_acceptance(plan_id, worker_id)` in `checkin_finish` and
  reject if not found. Low risk at current scale (single-tenant), but a security
  hardening item.

---

## Frontend — `frontend/app.html` (~6000+ lines, one file)

### Recommended extraction slices (future rounds)

| Slice | What | Blocker |
|---|---|---|
| `tokens.css` | CSS custom properties (already extracted as of last session) | — |
| Bootstrap / init | initApp(), auth flow, NavigationManager | High coupling to DOM |
| Contracts tab | Angebot/Rechnung UI | Self-contained enough to extract |
| Kontrol-day / Production Control | Owner matrix, DailyPlan UI | Large, high-churn |
| Chat UI | Chat hub, direct threads | Chat hub redesign not yet done |
| Feed UI | Feed sub-tabs | Now extracted to `#view-feed` (Phase 3) |

Extraction approach: move CSS to `frontend/css/<name>.css`, inline JS blocks to
`frontend/js/<name>.js`, keeping `app.html` as a thin shell. Each extraction must
be verified with `node --check` and the HTMLParser deploy check.

---

## Known deliberate limitations (per owner decision — do not "fix" without asking)

- **No database, no ORM** — flat JSON files, adequate at current scale.
- **No CI/CD, no automated E2E** — tracked in TODO.md.
- **Material/warehouse inventory and Fahrtenbuch** — explicitly out of scope.
- **Vanilla JS** — no React/Vue migration. Real problem is global-state sprawl in
  app.html, fix via incremental extraction, not framework swap.
