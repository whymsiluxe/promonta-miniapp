# Backlog

**Last updated**: 2026-09-25 (shipped chat swipe-to-reply; found calendar
year-view+drag already built by an earlier session and removed the stale
entry — see "Verified already done").
Prior consolidation: 2026-09-18, from ~15 historical PLAN/HANDOFF/
UNIFIED_AUTONOMOUS_MASTER_PLAN files after reading each one in full and
verifying every candidate item against the real code (`git log`, `grep`),
not taken on the source doc's word. See [CURRENT_STATE.md](CURRENT_STATE.md)
for which files this superseded.

Items here are real gaps confirmed absent from the code as of 2026-09-18.
Anything that looked like a gap in an old doc but is actually already built
was left out — see each historical file's own `SUPERSEDED` note if you want
the full original list for comparison.

## P1 — worth doing soon

- **Rotate GitHub PAT leaked into chat 2026-09-25.** The fine-grained PAT
  used for `promonta`'s `/home/promonta/.git-credentials` (push access to
  this repo) was pasted directly into a Claude Code chat message by the
  owner to unblock a deploy after the previous classic PAT started 403'ing.
  *Why*: any token typed into a chat transcript should be treated as
  potentially logged/retained and rotated once no longer urgently needed —
  see `~/Projects/promonta/configs/ACCESS.md` "GitHub PAT" entry for the
  token and full context. *Status*: TODO — revoke old token at
  github.com/settings/tokens, issue a fresh one, update
  `/home/promonta/.git-credentials`, update ACCESS.md.
- **Object Detail V2 migration (Worker UX V2 Этап 7).** Reorganize worker
  object-detail from 3 tabs + 10+ stacked sections into `Обзор|Работа|
  Медиа|Чат`. NOT done as code in the 2026-09-21 session — a mapping audit
  found real risk factors (owner/worker interleaved in the same render
  functions, a chat panel that physically moves DOM nodes with 2
  already-documented bugs in its history, DOM-anchor-hardcoded section
  order, near-zero test coverage on ~3000 lines) high enough that the plan's
  own "reusable panels + follow-up doc" escape hatch was used instead. Exact
  target section->zone mapping and a risk-ordered migration order (Медиа ->
  Работа -> Обзор -> Чат) are in `docs/OBJECT_DETAIL_V2.md`. Two decisions
  need to be made explicitly before starting: `#stages-view`'s legacy status,
  and which owner-only "Обзор" content (if any) becomes worker-visible.
- **Worker Card "Календарь" tab vs "Открыть полный календарь" button —
  clarify, don't just remove one.** Verified 2026-09-18: this is NOT
  duplication, it's a preview-then-see-all pattern (the tab shows the
  worker's next 5 absence entries; the button opens the full Abwesenheit
  screen). The owner read it as "calendar twice for no reason" from a
  screenshot without that context. Real fix here is likely a UI label/visual
  tweak so the relationship is obvious at a glance (e.g. "Ближайшие" as the
  tab label, or visually nesting the button inside the tab panel more
  clearly) — not deleting either piece. Confirm the actual complaint with
  the owner before touching this (see OPEN_QUESTIONS.md #1).

## P2 — worth doing, not urgent

- **Backend domain split**: `backend/main.py` is 10092 lines, one file.
  Candidate router boundaries (from earlier planning, still reasonable):
  `auth`/`permissions`, `objects`, `checkin`, `chat`, `tasks`, `mangel`
  (defects), `profile`, `documents`, `ai`, `daily_plan`, `contracts`. Hard
  constraint carried over from every prior attempt at scoping this: route
  paths and names must not change during the split.
- **Frontend thin-shell split**: `frontend/app.html` (10521 lines) still
  carries styles/view containers/some inline handlers beyond what's already
  externalized into `frontend/js/*.js`. `home.js` (1782 lines) and `chat.js`
  (2225 lines) are the two largest JS modules and the next candidates if
  this is picked up.
- **Full automated E2E test**: owner assigns → worker accepts → DailyPlan
  publish/accept → shift start with photo+GPS → pause → finish → owner sees
  the result on their dashboard. Not found in `tests/` — current coverage is
  unit/contract-level per feature, not one continuous flow. Also would need
  a bad-connectivity/reconnect variant given the offline-outbox work already
  in place.
- **CRM block** (clients, leads, deals, communication history) — not in the
  data model at all currently. P3-adjacent, listed here because it keeps
  coming up in owner-pasted gap lists; no scoping done yet.
- **Real staging environment.** Production-only today (by design so far, not
  an oversight — see CURRENT_STATE.md known blockers).
- **Contract ingestion pipeline activation.** `backend/contract_ingest.py` +
  `scripts/plan_sync.py` are fully built (Drive polling → fact extraction →
  draft DailyPlan → owner approve/reject) and gated behind
  `CONTRACTS_DRIVE_FOLDER_ID`. Owner has explicitly said (2026-09-18): don't
  enable yet, keep building the surrounding DailyPlan logic (cutoff alerts,
  tomorrow-preview, etc.) first. Revisit when the owner gives the go-ahead —
  needs Drive OAuth scope confirmed first (was `docs/OPEN_QUESTIONS.md` Q1
  historically, already resolved as "deliberately deferred," not re-opening
  it here).

## P3 — future ideas, not scoped

- **PostgreSQL / real database migration.** Flat JSON stays fine at current
  scale (see DATABASE.md); revisit only if concurrency or reporting needs
  grow. Not urgent, no scoping done.
- **Google Sheets write-back for DailyPlan** (currently one-directional,
  Sheets → local store via `plan_sync.py`). Would need a durable sync queue
  if built — explicitly flagged in earlier planning as "only together, not
  separately."
- **Cross-worker productivity accuracy for multi-worker objects on a single
  DailyPlan** — `daily_plan_lib.py` already has a `contribution_weight`/
  `confidence="crew"` mechanism for this; whether it needs refinement wasn't
  re-verified in this pass.

## Explicitly out of scope (owner decision, not a gap)

- Material/warehouse inventory (Materialverwaltung).
- Fahrtenbuch (vehicle logbook).
- Manager/Bauleiter role — not requested.
- QR-code scanner for tool lookup — better fit for a future native app than
  the Telegram WebView; logged as an idea there, not building here.
- **Sanitized fixture/seed data for local development** — this was in the
  old (now-superseded) `docs/TODO.md` P2 list. Owner confirmed 2026-09-18
  this is no longer needed: automated tests already run fully isolated
  (`MINIAPP_DATA_ROOT` pointed at a fresh tempdir per test, never touches
  production data — 886 tests, zero prod risk), and there's no separate need
  for a hand-explorable local demo instance beyond that. Not building.

## Verified already done (kept here only so nobody re-proposes them)

Offline outbox with dead-letter state, `api()` request timeout/retry,
server-side DailyPlan validation at checkin start, per-worker plan
acknowledgment, owner daily cockpit, object history, drag-assign, budget
dashboard, task Kanban, document gallery, week/month calendar views,
Stundenzettel period charts, home dashboard sparklines, tool booking
calendar with conflict checks, news category filtering, durable finish
outbox with startup reconciliation, contract RED/GREEN risk coloring,
shared `fcntl`-based store locking across the API process and the
`plan_sync.py` worker, bottom-nav order (Лента/Главная/Чат/Объекты/Профиль,
Feed first — this was an open item in an old plan, confirmed done by
reading `frontend/app.html` directly 2026-09-18), dashboard N+1 request
dedup + feed lazy-load + owner diagnostics view (commit `abe3712`), calendar
year view + drag-to-move absence/assignment entries (`_abwRenderYearView`,
`_abwDragEntryId`/`_moveAbwesenheitEntry` in `abwesenheit.js` — built after
the "needs its own design pass" note was written, confirmed present and
wired 2026-09-25, this backlog entry was stale), chat swipe-to-reply
(commit `0a5b8cb`, 2026-09-25).
