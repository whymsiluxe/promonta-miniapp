# Decisions

Architectural decision log. New decisions get a new entry; superseded ones are marked, never rewritten.

---

**Date**: 2026-07-23
**Status**: Accepted
**Decision**: Combine the backend (`/home/promonta/agent/miniapp/`) and frontend (`/var/www/miniapp/`, which already had its own 14-commit git history) into a single repo, `miniapp-repo`, with `backend/` and `frontend/` subdirectories, built directly on the VPS.
**Context**: A Claude Code session was lost mid-work. Investigation found the two halves of the app lived in different directories on the VPS, only the frontend had version control, and a stale local copy existed on the developer's Mac (dated 8-12 July, while the VPS frontend had commits through 22-23 July) that would have caused data loss if used as the basis for recovery.
**Problem**: No single source of truth existed; documentation didn't reflect the actual, more-advanced state of the code.
**Options considered**: (1) two separate repos (frontend/backend), (2) work from the stale Mac copy and reconcile later, (3) one combined repo built from the live VPS state.
**Chosen**: (3).
**Why**: A single repo with one README/doc-set is easier to keep in sync per the new documentation-governance rules (see `CLAUDE.md`), and building directly from the VPS avoids reconciling a diverged, stale local copy. `git subtree add` was used (not `git filter-repo`, not installed) to bring the frontend's existing history in under a `frontend/` prefix without rewriting it.
**Consequences**: The old frontend repo's remote (a local filesystem path, `/var/www/miniapp`) was removed after the subtree merge — GitHub is now the intended remote. The Mac-side stale copy at `~/Projects/promonta/miniapp/frontend/` was left untouched (not deleted) since it wasn't authorized for destructive cleanup in this pass — see TODO.md for reconciling or removing it.
**Risks**: If anyone continues editing `/var/www/miniapp` or `/home/promonta/agent/miniapp` directly on the VPS without syncing back to this repo, the repo will drift from production again — the exact problem this recovery fixes. The governance rules in `CLAUDE.md` exist specifically to prevent that regression.
**Affected files**: entire repo structure.

---

**Date**: 2026-07-23
**Status**: Accepted
**Decision**: Runtime JSON data stores (worker profiles, chat messages, GPS check-in logs, photos, generated PDFs) are excluded from git entirely via `.gitignore`, not just from public visibility.
**Context**: These files contain employee personal data (names, GPS locations, photos, birthdays, clothing sizes) and business documents (client quotes/invoices). The task's own safety rules prohibit committing "real personal data of employees."
**Problem**: A private repo still isn't an appropriate place for this data — it multiplies where sensitive data lives and creates a stale, unsynced copy the moment someone's shift GPS log updates.
**Chosen**: Never commit runtime data. Backend code only. Data stays on the VPS, protected by the existing `backup.sh` daily-tarball mechanism (see DATABASE.md), not by git.
**Consequences**: `docs/FEATURES.md` status claims can't be verified by reading committed fixtures — verification requires either live access to the VPS or a manually-sanitized fixture set, which doesn't exist yet (see TODO.md).
**Affected files**: `.gitignore`.

---

**Date**: 2026-07-28
**Status**: Accepted
**Decision**: Chat Hub keeps 5 category tabs (Общий/Личные/Объекты/Дефекты/Потребности), not the 4 the Phase 06 spec (ТЗ3) literally describes.
**Context**: `docs/plan-phases/06-chat-hub-rebuild.md`'s code audit found a 5th tab, "Потребности" (`task:ID` threads), already live in production and in active daily use — it predates this plan and isn't a Phase 06 addition. The spec text says "4 таба" and lists only Общий/Личные/Объекты/Дефекты.
**Problem**: Silently dropping the tab during the rebuild would delete team members' access to an existing, used feature (task-request chat threads) with no owner sign-off; silently keeping it would mean diverging from a written spec without recording why.
**Options considered**: (1) drop Потребности to match the spec literally, (2) keep it and treat the spec's "4 таба" as describing the four *new* dark-theme tab types being introduced, not a hard cap, (3) block the whole Phase 06 rebuild pending an explicit owner answer.
**Chosen**: (2) — keep 5 tabs.
**Why**: `app.html`'s Object Info screen has an explicit prior comment recording an owner requirement to keep Потребности as its own object-scoped surface ("Потребности остаётся отдельным object-scoped табом по явному требованию владельца"), which is direct evidence the owner treats task-requests as a first-class, separate concern from defects — not something to fold away. Removing a live, working, explicitly-requested feature to satisfy a tab-count in a planning doc is a worse failure mode than a documented, reversible deviation from that doc. Blocking the entire rebuild on this alone (option 3) wasn't warranted — it's a low-stakes, easily-revisited call, not one that needed to stall a multi-session project.
**Consequences**: All Chat Hub rebuild work (worker strip, tabs component, search-per-tab, empty states) targets 5 tabs. If the owner later says they actually meant 4 and wants Потребности folded into Объекты or removed from Chat Hub entirely, that's a small, isolated follow-up, not a rearchitecture.
**Affected files**: `frontend/app.html` (chat category tabs), `frontend/js/chat.js`, `docs/plan-phases/06-chat-hub-rebuild.md`.

---

*(No earlier decisions are recorded — prior sessions did not maintain this log. Everything before 2026-07-23 is undocumented architectural history; where it matters, it's referenced inline in other docs from session memory rather than reconstructed here as a formal decision.)*

---

**Date**: 2026-08-04
**Status**: Accepted
**Decision**: Closed needs (`Потребности`, `tasks.json`) are now RETAINED in the working JSON with `status:закрыто`+`closed_at` instead of being deleted on close.
**Context**: Раунд 3 задача 5.2 requires the Потребности screen to show a "Выполнены N" counter and a "Выполненные" filter/archive. The prior behaviour archived the closed task to a Google Sheet and then removed it from `tasks.json`, so the frontend had nothing to count or list for completed items.
**Options considered**: (1) fetch completed items from Google Sheets on the frontend; (2) keep closed tasks in JSON, filter to "Активные" by default in the UI.
**Chosen**: (2).
**Why**: The frontend has no Sheets access path and Sheets is explicitly a view-only mirror, not an app data source. Keeping closed tasks in JSON is a one-line retention change; the UI already defaults to the "Активные" filter so completed items don't clutter the main view. Sheets archive still happens best-effort, but only on the first close (`prev_status != 'закрыто'`) to avoid duplicate rows on re-close.
**Consequences**: `tasks.json` grows over time with closed items (acceptable at current scale — same flat-JSON tradeoff documented in DATABASE.md). Any consumer of `GET /api/tasks` that must exclude completed items filters `status != 'закрыто'` (Dashboard badge already does).
**Affected files**: `backend/main.py` (`update_task_status`), `frontend/js/tasks.js`, `frontend/js/object-info.js`, `tests/test_needs_workflow.py`.
