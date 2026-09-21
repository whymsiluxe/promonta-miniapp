# Open Questions

**Last updated**: 2026-09-21 (added Q3, Object Detail V2 decisions).
Prior consolidation: 2026-09-18, from `OPEN_QUESTIONS.md`,
`OPEN_QUESTIONS_09sep2026.md`, `OPEN_QUESTIONS_11sep2026.md` after reading
each in full and verifying against the real code — items already answered
by the owner or already resolved in code (even where the doc itself wasn't
updated to say so) are left out. See [CURRENT_STATE.md](CURRENT_STATE.md)
for the historical-files list this supersedes.

Real architectural/product forks go here with full context, per the
project's standing convention. Add a new dated entry rather than deleting an
answered one — once the owner answers, fold the resolution into
CURRENT_STATE.md/BACKLOG.md/CHANGELOG.md as appropriate and mark the entry
here resolved (don't delete — keeps the decision traceable).

---

## 1. Worker Card: "Календарь" tab vs "Открыть полный календарь" button

**Not actually duplication** (verified 2026-09-18, see BACKLOG.md P1): the
tab shows a preview (next 5 absence entries via a scoped
`/api/abwesenheit` call), the button opens the full Abwesenheit screen. A
standard preview-then-see-all pattern, not two implementations of the same
thing.

**What's actually needed**: confirm with the owner whether the complaint
("calendar twice for no reason") was about the *relationship between the two
not being visually obvious* (fixable with a label/layout tweak) or something
else entirely — the original complaint came from a screenshot without much
context. Don't remove either piece without that clarification.

*Source*: `docs/OPEN_QUESTIONS_09sep2026.md` (Item 6), re-verified 2026-09-18.

---

## 2. "Start без DailyPlan" — legitimate policy or a gap to close?

Currently a worker can tap Start (`checkin_start`) with no published
DailyPlan for the day — the request goes through with zero plan validation
(`backend/main.py`, `checkin_start()`, `daily_plan_id: str = Form('')` is
optional; empty → the whole plan-linkage validation block is skipped).

This was reframed by the owner on 2026-09-18, mid-cutoff-alert
implementation: the intended fix is **not** a start-time block on the
worker. It's upstream — the plan should be published the evening before by
the owner, and two alerts now exist for that (`backend/
daily_plan_cutoff_check.py`, 18:00 "not published for tomorrow yet" reminder
+ 06:30 "still not published for today" overdue alert, both live via
systemd timers as of 2026-09-18). **Start-without-a-plan stays freely
allowed by design** — this question is now considered resolved in that
direction, kept here only in case the owner wants a stricter gate later
(e.g. after seeing how often the alerts actually fire in practice).

*Source*: `docs/OPEN_QUESTIONS_11sep2026.md` (Q3, Phase 4) → resolved
2026-09-18 per owner's evening-reminder framing.

---

## 3. Object Detail V2 (Worker UX V2 Этап 7) — two decisions blocking the migration

Found 2026-09-21 while mapping the current object-detail screen before
attempting the plan's `Обзор|Работа|Медиа|Чат` reorganization (see
`docs/OBJECT_DETAIL_V2.md` for the full audit). Both need an explicit owner
answer before that migration can start safely — deferred on purpose rather
than guessed:

1. **`#stages-view` (`app.html:8851`, `objects.js:826-888`
   `openStagesView`/`closeStagesView`) looks legacy/half-dead.** No active
   call sites found from current click handlers — the live path is
   `openObjectDetail(..., 'stages', ...)` (`objects.js:452`), a different
   mechanism. Is `#stages-view` still needed for something not found in this
   pass, or safe to remove in its own small commit before the bigger
   reorganization?
2. **Which owner-only "Обзор" content (if any) becomes worker-visible?**
   `_renderObjControlCenter()` (`object-info.js:280-384`, the closest thing
   to an existing "Обзор" dashboard) is entirely gated
   `currentRole === 'owner'` — including `team&shifts`, which shows other
   workers' shift status. Worker UX V2's target "Обзор" wants active
   shift/recent activity visible to the worker, but showing the full
   control-center (including who else is on shift, budget-adjacent tiles)
   was never explicitly asked for and shouldn't be assumed.

*Source*: `docs/OBJECT_DETAIL_V2.md`, written 2026-09-21 during Этап 7 spike.

---

## Resolved / no longer open (kept for context, not re-litigating)

- **Drive OAuth scope for contract ingestion** — owner has said (2026-09-18)
  to keep building the surrounding DailyPlan logic but not enable
  `CONTRACTS_DRIVE_FOLDER_ID` yet. Standing decision, not forgotten — see
  BACKLOG.md P2.
- **External `create_object.py`/`create_object_folder.py` scripts** —
  resolved, moved into `backend/` (commit `befc962`, 2026-09-17), tracked in
  `scripts/manifest.sh`.
- **CI workflow coverage gaps (backend/core, JS subdirs, manifest drift)** —
  resolved in code (commit `2676d11`, 2026-09-17) even though the original
  doc entry was never marked done there.
- **GitHub repo private / PAT rotation** — not "open" in the sense of
  needing analysis, it's a standing owner decision (declined twice) — see
  CURRENT_STATE.md known blockers, not tracked as a question here.
- Every other item across the three source files (Нормы_работ verification,
  Sheets tab structure, systemd timer setup, various failure-mode
  clarifications, Worker Card back-stack behavior, `initialTab` handling,
  pre-existing failing tests) was explicitly answered by the owner in a
  2026-09-07 "Owner answers" pass or resolved by later code — not repeated
  here.
