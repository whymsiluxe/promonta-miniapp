# Object Detail V2 — implementation plan (Этап 7)

Status: **plan only, no code**. Follows `docs/STAGES_VIEW_MIGRATION_MAP.md`
(per-item `#stages-view` disposition, owner-approved) and the earlier
`docs/OBJECT_DETAIL_V2.md` (risk analysis: owner/worker inline-ternary
coupling, DOM-anchor insertion order, chat-embed fragility, near-zero test
coverage — all still accurate, referenced below rather than re-derived).

Two owner decisions this plan builds on, both already final:

1. **`#stages-view` retires entirely, but only after its replacement is
   functionally complete** — its non-duplicate pieces (shift timer/GPS,
   pause/resume, manual time) become panels inside the new "Работа" zone
   BEFORE the standalone screen is removed, never after (see the corrected
   migration order below — an earlier version of this plan got this
   sequencing wrong). AI-анализ is deferred, not ported in this migration.
   Everything else already has a better-architected equivalent inside
   `openObjectDetail()` today and is reused outright.
2. **Same 4-zone IA for both roles** — `Обзор | Работа | Медиа | Чат` for
   owner AND worker. Content inside "Обзор" differs by role (owner: full
   dashboard incl. budget/margin/team; worker: operational status only, no
   financial/management data), and that filtering happens **server-side**,
   not via frontend CSS/JS hiding — this repo already has the precedent
   (`_serialize_object_for_worker()`, `main.py:2023`, strips `BUDGET_FIELDS`
   before a worker-facing response is even built).

## Current structure (verified against code, not the plan doc's guess)

- `openObjectDetail()` (`objects.js`) has **3 top-level tabs**:
  `OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'stages']` (`objects.js:1427`) —
  Чат / Инфо / План работ. "6-tab" in some old comments is stale history,
  not current structure (see migration-map doc's correction).
- "Инфо" is not one thing — it's ~11 independently-rendered sections in one
  scroll: `_renderObjControlCenter()` (owner-only dashboard),
  `_renderObjTeamAndShifts()` (owner-only), photo-upload, status-switch,
  description, works (Объёмы/Задачи sub-tab), defects summary, docs
  summary+viewer, needs, budget (owner-only), task kanban, history.
- **A genuine, currently-inaccessible-to-workers data source exists for
  Обзор's shift-status content**: `_renderObjControlCenter()` calls `GET
  /api/dashboard/shifts-today`, which is `require_owner`-gated server-side
  (`main.py:2813`) — its own docstring says why: "агрегирует GPS/личные
  данные всех работников." A worker calling it today gets a 403. This is
  **not** a bug to route around by loosening that gate — it's proof the
  worker Обзор needs its own, narrower endpoint (see below), not reuse of
  the owner one with a client-side role check bolted on.

## Target zone content, both roles

```
Object Detail V2
│
├── Обзор
│    OWNER (full — reuses _renderObjControlCenter's data sources as-is):
│      Working-now / not-started / awaiting-response tiles (company-wide
│      GPS/personal aggregation, existing owner-only endpoint)
│      Budget/margin summary
│      Team & shifts (who's assigned, who declined, why)
│      Plan/stage progress, open needs/defects counts
│
│    WORKER (trimmed — NEW endpoint, see below):
│      Object name, address, overall status
│      MY assigned stage(s)/work type(s)
│      MY assignment dates
│      MY current shift status (reuse resolveWorkerShiftState(), same
│        pattern Home/Object already use elsewhere)
│      Today's DailyPlan preview for this object (reuse today-plan.js
│        rendering, not a second implementation)
│      MY open problems/blockers for this object (needs+defects I raised
│        or am assigned to, not everyone's)
│      Recent activity (already role-neutral: history section)
│
│      Explicitly NOT shown to worker: budget/margin/revenue, commercial
│      docs, salaries/rates, other workers' full assignment records,
│      admin actions (assign/remove worker), company-wide GPS aggregation
│
├── Работа  (same for both roles; the "мои" framing above IS the access
│    control on Работа's action buttons, not a second gate)
│    ├── DailyPlan / этапы     ← reuse (renderObjectStagesTab/_loadObjStages,
│    │                            _openAddStageSheet — already worker-visible)
│    ├── Start / Finish        ← reuse canonical Shift Flow
│    │                            (_appendCheckinShortcut, already exists)
│    ├── Shift timer + GPS     ← PORT from #stages-view (genuinely missing)
│    ├── Pause / Resume        ← PORT from #stages-view (genuinely missing)
│    ├── Manual time entry     ← PORT from #stages-view (genuinely missing)
│    ├── Quick Actions         ← reuse worker-quick-actions.js (Этап 6)
│    ├── Needs / Defects       ← reuse existing sections, unchanged gating
│    ├── Task kanban           ← reuse renderObjectTaskKanbanSection (owner
│    │                            builds/assigns, worker sees own — verify
│    │                            existing gate, don't relax it)
│    └── AI-анализ             ← DEFERRED. Not ported in this migration at
│                                  all — do not let its retain/drop decision
│                                  block Object Detail V2. Revisit after.
│
├── Медиа
│    OWNER (unchanged): full photo gallery + all documents, as today.
│
│    WORKER (new, narrow): operational photos of the object (the same
│      photos Этап 6's Фото quick-action already captures — this zone is
│      for BROWSING them, not a second capture flow) + explicitly
│      worker-safe technical documents. NEVER commercial/financial
│      documents (offers, invoices, contracts, budgets) — if the backend
│      cannot yet reliably distinguish a worker-safe technical document
│      from a commercial one (no classification/access-flag exists today),
│      worker Медиа ships as **photos only** first; documents are added
│      only after that classification exists, not by guessing per
│      filename/folder. Same server-side-filtering principle as Обзор.
│
└── Чат
     embedObjectChat/unembedObjectChat — unchanged, ported LAST, 1:1,
     no rewrite of the DOM-move mechanism itself (see OBJECT_DETAIL_V2.md's
     risk #2 for why this exact mechanism is fragile)
```

## New backend work required (not optional — this is where the real risk is)

**`GET /api/objects/{id}/worker-overview`** (name placeholder) — a NEW
endpoint, not a role-branch inside an existing one. Owner review's principle
applies directly: *"безопасность должна быть server-side, а frontend —
второй слой."* Composition:

- Object identity fields (name, address, status) — already public today.
- This worker's own assignment(s) for this object — reuse the same
  `my_assignments` shape `_serialize_object_for_worker()` already produces
  (`main.py:2043-2047`), don't invent a second shape.
- This worker's shift state for this object — `resolveWorkerShiftState()`
  is frontend-only; the backend equivalent is already `GET /api/checkin` +
  the session-ownership filtering `list_checkins()` already does for
  non-owner roles (`main.py:8624-8627`). Reuse that filter, don't rebuild it.
- This worker's own open needs/defects for this object — filter
  `/api/tasks`/`/api/mangel` results by `assigned_to == this worker` (or
  `created_by`, whichever the product decision settles on) server-side, not
  by fetching everyone's and filtering in the browser.
- Explicitly EXCLUDE: `BUDGET_FIELDS` (reuse the existing constant, same
  pattern as `_serialize_object_for_worker`), team roster beyond public
  fields, `shifts-today`-style cross-worker aggregation.

This is new backend code, which is out of this plan's "no code" scope — it's
listed here because the migration cannot start with a frontend-only pass;
the data source has to exist first.

## Migration order — CORRECTED (owner review found a real sequencing bug in
the original version of this section; see below for what was wrong)

**What was wrong:** the original order retired `#stages-view` as step 1,
repointing its 3 callers straight to `openObjectDetail(id, name, 'work',
status)` — but no `work` tab/panel exists yet at that point (only
`chat`/`info`/`stages` do). That call would try to show a
`obj-detail-panel-work` element that doesn't exist. Worse, even if the tab
key were fixed, retiring `#stages-view` before the Работа zone actually
carries its unique content (timer/GPS, pause/resume, manual time) would
leave workers with a real feature regression for however long the
migration takes — those three have no equivalent anywhere else today (see
mapping doc). **A retirement step can never run before its replacement is
functionally complete**, not even briefly.

Corrected order:

1. **Create the 4-zone shell**: `Обзор | Работа | Медиа | Чат` tabs/panels
   added to `openObjectDetail()`, alongside the existing 3 — nothing removed
   yet. Работа's shell initially just re-renders the EXISTING `stages`
   content (`renderObjectStagesTab`/`_loadObjStages`/`_appendCheckinShortcut`)
   unchanged — a thin wrapper, not a rewrite. `#stages-view` and its 3
   callers are untouched at this point; this step only adds a new,
   parallel-but-unused path to validate the shell itself first.
2. **Port the unique reusable panels into Работа**: shift timer/GPS status,
   pause/resume, manual time entry — extracted from `#stages-view`
   (`checkin.js`'s `_activeShiftTimerInterval` logic and friends) as
   functions callable from Работа, driven by `resolveWorkerShiftState()`'s
   already-resolved state, not a second poll. Start/Finish and the stage
   list are NOT re-implemented here — they already route through the
   canonical paths (`_appendCheckinShortcut`, `renderObjectStagesTab`) from
   step 1. **Only once Работа's content is a functional superset of
   `#stages-view`** does step 3 become safe.
3. **Retire `#stages-view`**: now — and only now — repoint the 3 callers
   (`home.js` owner ring handler, `home.js` worker active-shift shortcut,
   `worker-checkin-fab.js`) to `openObjectDetail(id, name, 'work', status)`,
   delete the standalone screen and its legacy DOM/JS. This is safe because
   step 2 already made Работа a full replacement, not a partial one.
4. **Медиа** — least DOM/logic coupling to the rest of Инфо per
   OBJECT_DETAIL_V2.md's own finding; a contained slice to validate the
   "peel a section into its own zone" pattern before touching riskier ones.
   Worker access here is photos + explicitly worker-safe technical
   documents ONLY (see the dedicated section below) — never commercial/
   financial documents, and never by relaxing today's owner-only gate
   wholesale.
5. **Обзор** — requires the new worker-overview endpoint (below) to exist
   first; do not attempt a frontend-only version that just hides owner
   fields with CSS, per the owner's explicit instruction. **The endpoint
   must not become a second shift-state source** — see the dedicated
   section below, this is a hard architectural constraint, not a style
   preference.
6. **Чат** — last, most fragile (DOM node relocation between parents,
   `embedObjectChat`/`unembedObjectChat`, 2 previously-documented bugs in
   that exact mechanism). Port the zone wrapper only; do not touch the
   embed/unembed implementation itself in the same pass.

Each of steps 1-6 is its own commit with its own quality gate (full suite +
node --check), matching this session's established pattern — no step lands
mixed in with another.

## Hard constraint: Worker Overview must not create a second shift-state machine

`resolveWorkerShiftState({ objectId })` is — after this session's 4 rounds of
review — the single, hardened source of shift state (outbox → server →
dead_letter recovery → localStorage, with the exact precedence rules fixed
across those rounds). The new backend worker-overview endpoint (below)
returns object/assignment/blocker data; it must NOT also compute or return
its own ACTIVE/PAUSED/PENDING/SYNC_ERROR determination for the frontend to
read instead of calling the resolver. Worker Overview's zone code calls
`resolveWorkerShiftState({ objectId })` exactly like every other consumer
(Home, FAB, Quick Actions) — the backend endpoint's job is everything
EXCEPT shift state: identity, assignments, blockers, DailyPlan preview data.
Re-litigating this per screen is exactly the re-fragmentation risk
`test_worker_shift_state_architecture_guard.py` exists to catch on the
frontend side; this is the same principle applied to a new backend surface
before it's built, not after.

## Test coverage to add BEFORE each step (not after)

Consistent with this repo's existing style (`tests/*_frontend_contract.py`,
source-assertion, no browser harness) — a source-assertion test locking in
current behavior before it's touched gives a diff to review, not blind
trust:

- Before step 1 (4-zone shell): assert `OBJ_DETAIL_TAB_ORDER` still equals
  the current 3 tabs, and the 3 `openStagesView()` caller sites' calls are
  unchanged — this doc's own baseline, so an accidental early repoint (the
  exact bug this correction fixes) fails a test immediately instead of
  reaching a worker.
- Before step 2 (port unique panels): a test asserting the ported timer/
  GPS/pause/manual-time functions read state via `resolveWorkerShiftState()`
  (or its already-resolved result), not a second poll/globals tied to
  `#stages-view`'s specific DOM ids.
- Before step 3 (retire `#stages-view`): update the step-1 baseline test to
  assert the NEW `openObjectDetail(..., 'work')` calls at all 3 sites, AND
  assert `#stages-view`'s DOM/JS no longer exists — both directions checked
  in the same commit, so this step can't land as "added new path, forgot to
  remove old" or "removed old, one caller still points at it."
- Before step 5 (Обзор): a **backend** test for the new worker-overview
  endpoint asserting `BUDGET_FIELDS` are absent from the response, that a
  worker requesting another worker's `my_assignments`-equivalent gets either
  nothing or 403 (mirroring `test_worker_object_privacy.py`'s existing
  pattern for the list-objects endpoint), AND that the endpoint's response
  contains no shift-state field at all (the hard constraint above) —
  frontend-side, a test that the zone's code calls
  `resolveWorkerShiftState(` and does not read a shift-state-shaped field
  from the overview response.
- Before step 6 (Чат): a test asserting `embedObjectChat`/`unembedObjectChat`'s
  call sites and DOM target ids are unchanged post-migration (regression
  guard for the two previously-documented bugs in this exact mechanism).

## Explicitly out of scope for this plan

- The `AI-анализ смены` retain/drop decision — deferred, not decided here;
  not ported in this migration at all (see corrected migration order).
- Exact visual/CSS layout within each zone.
- The worker-overview endpoint's exact response schema (sketched above at
  the field-category level, not finalized field names/shapes) — that's
  implementation detail for the coding session, not a plan-level decision.
- The exact backend classification/access-flag mechanism for distinguishing
  worker-safe technical documents from commercial ones (needed before
  worker Медиа can show documents at all, per the Медиа section above) —
  worker Медиа ships as photos-only until that exists; designing that
  classification is separate follow-up work, not blocking this plan.
