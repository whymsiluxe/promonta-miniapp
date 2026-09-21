# #stages-view → Object Detail migration map

Owner review (2026-09-22) flagged a real risk: blindly moving `#stages-view`
into the new 4-zone Object Detail ("Работа" zone) could drag along a
duplicate implementation of something the *already-live* `openObjectDetail()`
reuses just fine. This doc is the required mapping before any code changes
for Этап 7 — per-item disposition, backed by actual grep/read of the current
code (not assumption).

**Correction (owner review, round 2 of this doc):** an earlier version of
this doc said `openObjectDetail()` has "6 lazy-loaded tabs" and misattributed
the first `openStagesView()` caller to "Today DailyPlan preview." Both were
wrong — fixed below, verified directly against `objects.js` and `home.js`.

## The two systems, as they exist today

- **`#stages-view`** (`objects.js::openStagesView()`) — standalone screen.
  Own header, own back button, not a NavigationManager overlay, not part of
  the `.view` system `switchView()` toggles.
- **`openObjectDetail()`** (`objects.js`) — the actual current default path.
  **3 top-level tabs** — `chat` / `info` / `stages` (`objects.js:1427`:
  `const OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'stages'];`), each with
  multiple sections nested inside it. (Some old in-code comments elsewhere
  still say "6-tab" — that's a historical artifact of an earlier iteration,
  not the current structure; don't design Этап 7 against it.) Registered as
  a NavigationManager overlay (fixes a real hardware-back bug, 29.07 comment
  at objects.js:914-930), used by **every** object-card tap already:
  - Whole-card click → `openObjectDetail(id, name, 'chat', status)`
    (objects.js:531-536, added 24.07)
  - `.stage-clickable` sub-element click → `openObjectDetail(id, name,
    'stages', status)` (objects.js:449-454)

**`openStagesView()` is not the primary object-open path today.** It is only
reached from 3 call sites, none of which are the object card itself:

| Caller | Context |
|---|---|
| `home.js:823-830` (`_attachHomeRingHandlers`) | **Owner** Home dashboard — tapping an object progress ring. Workers never reach this handler at all (`initHomeView()` routes worker straight to `initWorkerHomeView()`, a completely different render path). |
| `home.js:1212-1220` (`_openObjectForShift`) | **Worker** Today — the active-shift "Завершить" shortcut (per its own 17.09 comment: the idle "Начать" path already moved to the shared picker flow; this is only the already-active-shift case now). |
| `worker-checkin-fab.js:128` | FAB → object/stage picker → `_openWorkerShiftObject()` |

All three are "jump straight to this object's shift status" shortcuts, not a
general object-browsing entry point — that conclusion (3 remaining callers,
none of them the primary object-open path) is correct and unchanged from the
original version of this doc; only the description of the first caller was
wrong.

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
| AI-анализ смены (`checkin-analyze-btn`) | **No.** | **Decision required before porting.** If retained, extract as a reusable panel driven by the resolver's already-resolved session state — do not preserve `#stages-view`-specific globals/DOM contract. Not every old function should carry over automatically just because it exists; confirm with owner it's still wanted first. |
| Manual time entry (`checkin-manual-form`, `checkin-manual-link-btn`) | **No.** | **Port as a reusable panel** — same reasoning as pause/resume, needs the resolver-based `objectId`/session context rather than `#stages-view`'s own globals. |

## Target state

```
Object Detail V2
│
├── Обзор
├── Работа
│    ├── DailyPlan / этапы        ← reuse (renderObjectStagesTab/_loadObjStages)
│    ├── Start / Finish           ← reuse canonical Shift Flow (_appendCheckinShortcut)
│    ├── Shift timer + GPS        ← PORT (genuinely missing today)
│    ├── Pause / Resume           ← PORT (genuinely missing today)
│    ├── Manual time              ← PORT (genuinely missing today)
│    ├── Quick Actions            ← reuse worker-quick-actions.js
│    └── AI-анализ                ← decision required, only if retained
│
├── Медиа
└── Чат
```

Standalone `#stages-view` retires entirely afterward, along with its
duplicate stage renderer, Start/Finish UI, chat shortcut, and local quick
actions. Everything reused above already has a live, arguably
better-architected equivalent inside `openObjectDetail()` today — reused
outright, not re-implemented as a second copy.

## Remaining `openStagesView()` callers to update when #stages-view is retired

All 3 must be repointed to `openObjectDetail(objectId, objectName, 'work')`
(or whatever the Работа zone's tab key ends up being) instead of
`openStagesView(objectId, objectName)`:

1. `home.js:823-830` (`_attachHomeRingHandlers`) — owner Home object-ring tap
2. `home.js:1212-1220` (`_openObjectForShift`) — worker Today active-shift shortcut
3. `worker-checkin-fab.js:128` — FAB → picker → `_openWorkerShiftObject()`

## Not yet answered by this doc

This is a mapping, not an implementation plan — the target-state diagram
above fixes what belongs in "Работа" and where it comes from, but not its
internal visual layout/ordering within that zone, nor the DOM/CSS mechanics
of the actual migration. The second open question (Owner's full vs Worker's
trimmed "Обзор") is already answered separately: same 4-zone IA for both
roles —

```
OWNER:  Обзор | Работа | Медиа | Чат
WORKER: Обзор | Работа | Медиа | Чат   (same 4 zones, content differs)
```

— content differs per role, filtered server-side (not just hidden client-side
DOM/CSS) since the backend already has worker-safe serialization
(`_serialize_object_for_worker`) as precedent. Both feed into the actual
Этап 7 implementation plan, still to be written after this mapping is
reviewed and approved.
