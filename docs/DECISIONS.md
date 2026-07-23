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

*(No earlier decisions are recorded — prior sessions did not maintain this log. Everything before 2026-07-23 is undocumented architectural history; where it matters, it's referenced inline in other docs from session memory rather than reconstructed here as a formal decision.)*
