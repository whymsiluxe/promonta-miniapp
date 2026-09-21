# #stages-view → Object Detail migration map

Owner review (2026-09-22) flagged a real risk: blindly moving `#stages-view`
into the new 4-zone Object Detail ("Работа" zone) could drag along a
duplicate implementation of something the *already-live* `openObjectDetail()`
6-tab system reuses just fine. This doc is the required mapping before any
code changes for Этап 7 — per-item disposition, backed by actual grep/read of
the current code (not assumption).

## The two systems, as they exist today

- **`#stages-view`** (`objects.js::openStagesView()`) — standalone screen.
  Own header, own back button, not a NavigationManager overlay, not part of
  the `.view` system `switchView()` toggles.
- **`openObjectDetail()`** (`objects.js`) — the actual current default path.
  6 lazy-loaded tabs (`chat`/`info`/`stages`/…), registered as a
  NavigationManager overlay (fixes a real hardware-back bug, 29.07 comment at
  objects.js:914-930), used by **every** object-card tap already:
  - Whole-card click → `openObjectDetail(id, name, 'chat', status)`
    (objects.js:531-536, added 24.07)
  - `.stage-clickable` sub-element click → `openObjectDetail(id, name,
    'stages', status)` (objects.js:449-454)

**`openStagesView()` is not the primary object-open path today.** It is only
reached from 3 call sites, none of which are the object card itself:

| Caller | Context |
|---|---|
| `home.js:828` | Tapping an object name inside the Today DailyPlan preview |
| `home.js:1219` | Worker Home shift CTA ("Продолжить смену" style shortcuts) |
| `worker-checkin-fab.js:128` | FAB → object/stage picker → `_openWorkerShiftObject()` |

All three are "jump straight to this object's shift status" shortcuts, not a
general object-browsing entry point.

## Per-item mapping

| `#stages-view` item | Already exists in Object Detail? | Disposition |
|---|---|---|
| Stage list (`stages-list`, `loadStagesWithRowNumbers()`) | **Yes** — `object-info.js::renderObjectStagesTab()` / `_loadObjStages()`, the "Этапы" tab already inside `openObjectDetail`. Different render function, same underlying `GET /api/objects/{id}/stages` data. | **Reuse.** Object Detail's "Этапы" tab is the live implementation; `#stages-view`'s `loadStagesWithRowNumbers()`/`renderStageRow()` is the one to retire, not port. |
| Add/delete stage (`add-stage-btn`, `addNewStage()`) | **Yes** — `object-info.js::_openAddStageSheet()`, a proper bottom-sheet (29.07 v5, full NavigationManager/focus/error lifecycle) already wired into the Object Detail "Этапы" tab. `#stages-view`'s version is a plain inline input+button, older and less complete. | **Reuse.** Object Detail's sheet is strictly more complete (keeps stale error text on network failure, restores focus, Telegram Back closes the sheet not the screen). |
| Start shift (`checkin-start-btn`, `checkin.js::_confirmCheckinPreview` etc.) | **Partially** — Object Detail's "Этапы" tab already calls `_appendCheckinShortcut()` (object-info.js:1371-1414) for non-owner roles, which resolves via `resolveWorkerShiftState()` + `openWorkerShiftFlow()` — the **canonical resolver architecture**, not `#stages-view`'s own `initCheckinControls()`/`refreshCheckinButtons()` two-button UI. | **Reuse the canonical path, delete the legacy one.** `_appendCheckinShortcut`'s single toggle button (Start/Finish/pending/error states, driven by the resolver) is architecturally correct today; `#stages-view`'s two-button (`checkin-start-btn`+`checkin-finish-btn`) UI predates the resolver unification and duplicates its own state logic via `refreshCheckinButtons()`. |
| Pause/resume (`checkin-pause-toggle-btn`) | **No** — `_appendCheckinShortcut` only has one button (Start/Finish), no inline pause control. | **Port as a reusable panel**, but redesign to route through the resolver like the rest of `_appendCheckinShortcut`, not `checkin.js`'s legacy pause-toggle handler tied to `#stages-view`'s specific DOM ids. |
| Finish shift | Same as Start — `_appendCheckinShortcut`'s button already becomes "■ Завершить смену" when `workerShiftStateHasActiveSession()`, which opens the Finish Wizard via the same `openWorkerShiftFlow()`. | **Reuse.** No separate work needed beyond what Start already covers (same button, same flow). |
| Active shift status (`active-shift-panel`: timer, GPS status) | **No** — nothing in Object Detail currently shows a live shift timer/GPS accuracy readout. This is real, worker-valuable content `_appendCheckinShortcut` doesn't have. | **Port as a reusable panel.** Genuinely missing functionality, not a duplicate — extract `active-shift-panel`'s timer/GPS rendering (`checkin.js`'s `_activeShiftTimerInterval` logic) into a function callable from wherever Object Detail's "Работа" zone ends up, driven by `resolveWorkerShiftState()`'s already-resolved state (session `startAt`/`startAccuracy`), not a second independent poll. |
| Quick actions row (Чат/Потребность/Дефект buttons inside `active-shift-panel`) | **Yes, elsewhere** — `worker-quick-actions.js` (Этап 6) already builds exactly this: Фото/Потребность/Дефект/Чат with proper context resolution (`resolveWorkerActionObject()`). | **Delete the legacy copy, reuse `worker-quick-actions.js`.** `active-shift-panel`'s 3-button row (`active-shift-qa-chat`/`-need`/`-defect`) is a smaller, older, `#stages-view`-local duplicate of the same feature Этап 6 already generalized and hardened (composite active-screen guard, round-2/3 owner review fixes). Wiring the Работа zone to call `runWorkerQuickAction()` with the zone's own known `objectId` is strictly better than porting the local 3-button markup. |
| Chat shortcut (`object-chat-btn`) | **Yes** — Object Detail's own `chat` tab (`obj-detail-panel-chat`) is a full embedded chat, not a shortcut button. `#stages-view`'s `object-chat-btn` just calls `openObjectOrMangelChat()` to open a chat thread from a different screen. | **Delete.** Once Работа lives inside Object Detail, its own Чат tab is one swipe/tap away — a shortcut button to itself has no purpose. |
| AI-анализ смены (`checkin-analyze-btn`) | **No.** | **Port as-is** (small, self-contained button + result panel), or confirm with owner it's still wanted before porting — not investigated further here since it's out of scope for the P0/P1 review that triggered this doc. |
| Manual time entry (`checkin-manual-form`, `checkin-manual-link-btn`) | **No.** | **Port as a reusable panel** — same reasoning as pause/resume, needs the resolver-based `objectId`/session context rather than `#stages-view`'s own globals. |

## Target state

Standalone `#stages-view` is retired entirely. Its still-needed, non-duplicate
pieces (active shift timer/GPS panel, pause/resume, manual time entry,
AI-анализ) become panel components inside Object Detail's future "Работа"
zone, reading state via `resolveWorkerShiftState()` like everything else this
session's work already converged on — not a second migrated copy of the
screen sitting next to the new one. Everything else (stage list, add stage,
Start/Finish button, quick actions, chat) already has a live, arguably
better-architected equivalent inside `openObjectDetail()` today and is reused
outright, not re-implemented.

## Remaining `openStagesView()` callers to update when #stages-view is retired

All 3 must be repointed to `openObjectDetail(objectId, objectName, 'work')`
(or whatever the Работа zone's tab key ends up being) instead of
`openStagesView(objectId, objectName)`:

1. `home.js:828` — Today DailyPlan preview's object link
2. `home.js:1219` — worker Home shift CTA
3. `worker-checkin-fab.js:128` — FAB → picker → `_openWorkerShiftObject()`

## Not yet answered by this doc

This is a mapping, not an implementation plan — it does not decide the
Работа zone's exact tab order/visual design, nor touch the second open
question (Owner's full vs Worker's trimmed "Обзор", already answered
separately: same 4-zone IA for both roles, content differs, server-side
filtered). Both feed into the actual Этап 7 implementation plan, still to be
written after this mapping is reviewed.
