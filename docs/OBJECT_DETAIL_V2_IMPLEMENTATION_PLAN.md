# Object Detail V2 — implementation plan (Этап 7)

Status: **plan only, no code**. Follows `docs/STAGES_VIEW_MIGRATION_MAP.md`
(per-item `#stages-view` disposition, owner-approved) and the earlier
`docs/OBJECT_DETAIL_V2.md` (risk analysis: owner/worker inline-ternary
coupling, DOM-anchor insertion order, chat-embed fragility, near-zero test
coverage — all still accurate, referenced below rather than re-derived).

Two owner decisions this plan builds on, both already final:

1. **`#stages-view` retires entirely** — its non-duplicate pieces (shift
   timer/GPS, pause/resume, manual time, AI-анализ if retained) become
   panels inside the new "Работа" zone; everything else already has a
   better-architected equivalent inside `openObjectDetail()` today and is
   reused outright.
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
│    └── AI-анализ             ← DECISION REQUIRED before porting (see
│                                  migration-map doc; not automatic)
│
├── Медиа
│    Photo upload/gallery, docs summary+viewer — CURRENTLY owner-only
│    (per OBJECT_DETAIL_V2.md's finding); Worker Фото quick-action already
│    exists separately (Этап 6, worker-quick-actions.js) and is NOT
│    superseded by this zone — this zone is for BROWSING existing media,
│    not the capture flow. Whether worker gets browse access to Медиа is a
│    SEPARATE decision from Этап 6's already-shipped capture action; not
│    decided by this plan, flag to owner before touching the gate.
│
└── Чат
     embedObjectChat/unembedObjectChat — unchanged, ported LAST, 1:1,
     no rewrite of the DOM-move mechanism itself (see risk #2 below)
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

## Migration order (risk-ascending, per the original OBJECT_DETAIL_V2.md's
own reasoning — restated here because it still holds)

1. **`#stages-view` retirement** (small, isolated, mapping already done) —
   repoint the 3 remaining callers (`home.js` owner ring handler,
   `home.js` worker active-shift shortcut, `worker-checkin-fab.js`) to
   `openObjectDetail(id, name, 'work', status)`, delete the standalone
   screen and its legacy DOM/JS once nothing references it. Do this FIRST
   and as its own commit, before any zone restructuring — confirms the
   3-caller count was complete and doesn't tangle with the bigger change.
2. **Медиа** — least DOM/logic coupling to the rest of Инфо per
   OBJECT_DETAIL_V2.md's own finding; a contained slice to validate the
   "peel a section into its own zone" pattern before touching riskier ones.
3. **Работа** — kanban/history/needs/stages sections are already
   independently rendered (not entangled with owner-only control-center),
   plus the ported `#stages-view` panels from step 1. Larger than Медиа but
   still lower-risk than Обзор (no new owner/worker data-shape decision
   needed here beyond what step 1 already settled).
4. **Обзор** — requires the new worker-overview endpoint above to exist
   first; do not attempt a frontend-only version that just hides owner
   fields with CSS, per the owner's explicit instruction.
5. **Чат** — last, most fragile (DOM node relocation between parents,
   `embedObjectChat`/`unembedObjectChat`, 2 previously-documented bugs in
   that exact mechanism). Port the zone wrapper only; do not touch the
   embed/unembed implementation itself in the same pass.

## Test coverage to add BEFORE each step (not after)

Consistent with this repo's existing style (`tests/*_frontend_contract.py`,
source-assertion, no browser harness) — a source-assertion test locking in
current behavior before it's touched gives a diff to review, not blind
trust:

- Before step 1: assert `OBJ_DETAIL_TAB_ORDER` and the 3 caller sites'
  current `openStagesView(...)` calls (this doc's own baseline) — update to
  assert the new `openObjectDetail(..., 'work')` calls once repointed, so a
  future regression that reverts one caller is caught.
- Before step 4 specifically: a **backend** test for the new worker-overview
  endpoint asserting `BUDGET_FIELDS` are absent from the response and that a
  worker requesting another worker's `my_assignments`-equivalent gets either
  nothing or 403 (mirroring `test_worker_object_privacy.py`'s existing
  pattern for the list-objects endpoint — same invariant, new endpoint).
- Before step 5: a test asserting `embedObjectChat`/`unembedObjectChat`'s
  call sites and DOM target ids are unchanged post-migration (regression
  guard for the two previously-documented bugs in this exact mechanism).

## Explicitly out of scope for this plan

- The `AI-анализ смены` retain/drop decision (migration-map doc: "decision
  required," not assumed).
- Whether worker gets Медиа zone *browse* access (separate from the
  already-shipped Фото quick-action capture flow) — flag to owner, don't
  decide unilaterally.
- Exact visual/CSS layout within each zone.
- The worker-overview endpoint's exact response schema (sketched above at
  the field-category level, not finalized field names/shapes) — that's
  implementation detail for the coding session, not a plan-level decision.
