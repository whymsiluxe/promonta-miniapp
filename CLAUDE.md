# CLAUDE.md — governance for this repo

This file is a mandatory operating protocol for any Claude Code session (or human developer) working in this repo, `promonta-miniapp`. It exists because a prior session was lost without any of its decisions, in-progress work, or reasoning being recorded anywhere durable — the app's code had moved three weeks ahead of its own documentation, and the frontend/backend lived in different directories with no shared version control. This file's job is to make that specific failure mode impossible to repeat silently.

## At the start of every session

Read, in order:
1. `README.md`
2. This file
3. `docs/PROJECT_STATE.md`
4. `docs/SESSION_HANDOFF.md`
5. `docs/TODO.md`

Then run:
```bash
git status
git status --short
git branch --show-current
git log --oneline --decorate -10
git remote -v
```

Only after that, state briefly: current branch, current commit, any uncommitted changes, what the last session finished, what's next, and any known risks. Only then start changing code.

## Source of truth

- The **code** is the source of truth for current behavior. Documentation is a required reflection of it, not the other way around.
- If code and docs disagree, that's a bug in the docs — fix it, don't just note it and move on, unless fixing it requires information you don't have (then write `UNKNOWN — requires verification`, don't guess).
- Never mark a feature `WORKING` in `docs/FEATURES.md` without having traced the actual flow (frontend call → backend route → persistence) yourself in this session. A UI existing doesn't mean the backend works. A backend route existing doesn't mean the UI calls it correctly. A route existing doesn't mean its permission check is correct — check it.

## Documentation is mandatory, not optional, for functional changes

Every commit that changes behavior must also touch, as applicable:

- **Always** if the change is functional at all: `docs/CHANGELOG.md`, `docs/PROJECT_STATE.md`, `docs/FEATURES.md` (if it changes a feature's status).
- **API changed** → `docs/API.md`.
- **Data storage changed** (new JSON store, new field, anything that would need a migration if this were a real database) → `docs/DATABASE.md`, `docs/ARCHITECTURE.md`.
- **UI/UX changed** → `docs/UI_UX.md`.
- **Role/permission changed** → `docs/ROLES_AND_PERMISSIONS.md` and `docs/SECURITY.md`.
- **Deploy/environment changed** → `docs/DEPLOYMENT.md`, `docs/ENVIRONMENT.md`, `docs/TROUBLESHOOTING.md` if it creates a new failure mode.
- **An architectural decision was made** (chose one approach over another for a non-obvious reason) → append to `docs/DECISIONS.md`. Never edit old entries to look different in hindsight — add a new entry and mark the old one superseded if the decision changes.

If a session is about to end and the docs above weren't updated for something real that changed, update them before stopping — don't leave it "for next time." There might not be a next time in the same context; that's exactly what happened before this recovery.

## Before every commit

1. `git status`, `git diff`, review the staged diff.
2. Grep for secrets before staging anything new: token/key/secret/password patterns. This repo has zero hardcoded secrets as of the 2026-07-23 recovery — keep it that way.
3. There is no lint/typecheck/test suite yet (see `docs/TESTING.md`, `docs/TODO.md`). Don't claim one passed. If you add one, wire it in here and update this section.
4. Manually verify the change per the relevant checklist in `docs/TESTING.md`.
5. Update the documentation files listed above as applicable.

## Commit style

Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `security:`. Small, logically single-purpose commits — don't bundle a documentation rebuild with a UI redesign with a bugfix in one commit. Keep code, its docs update, and its changelog entry together in the same commit where practical.

## After every commit

1. `git status` — working tree should be clean, or the remainder explained.
2. Push to the current work branch, not directly to `main`/`master` without a reason (this is currently a single-owner repo, so direct-to-main is more tolerable than it would be with a team, but still leave a clean commit trail).
3. No force-push. No history rewriting without the owner's explicit go-ahead — if a secret does end up in history, stop, don't push, tell the owner what leaked and that it needs rotating, and wait for a decision before touching history.
4. Report the commit hash and what was and wasn't verified.

## If a session is interrupted before finishing

1. Update `docs/PROJECT_STATE.md` and `docs/SESSION_HANDOFF.md` with exactly what's done, what's not, what files changed, and the next concrete step — enough that a fresh session with zero memory of this conversation could pick it up correctly. This is not a formality; it's the entire reason this file exists.
2. Commit what's safe to commit on a `wip/...` branch (`wip: preserve current progress for session recovery`), push it, don't merge to main/master.

## Absolute prohibitions

- No `git reset --hard`, `git clean -fd`, `git checkout .`/`git restore .` without first checking `git status` and understanding exactly what would be discarded, and confirming with the user if anything uncommitted is at risk.
- No force-push, no rewriting published history without explicit owner approval.
- No public GitHub repos for this project. Private only.
- No committing `.env*` (except `.env.example`), tokens, keys, credentials, or the runtime JSON data stores under `backend/*.json` and the various `*_photos/`/`avatars/`/`angebote/`/`rechnungen/` directories — these contain real employee personal data and business documents. See `.gitignore`; don't loosen it without a specific reason logged in `docs/DECISIONS.md`.
- No claiming a function "works" without having traced or tested it this session. No marking something `DONE` in `docs/TODO.md` without its acceptance criteria actually met.
- No silent security fixes — if you find a permission gap or vulnerability, document it (`docs/SECURITY.md` / `docs/ROLES_AND_PERMISSIONS.md`) and flag it to the user before or alongside fixing it, don't just quietly patch and move on. The user needs to know what was wrong in their production app.
- No large UI/UX redesign, framework swap, or database migration started casually — these need the same brainstorming/planning step any nontrivial change gets, and shouldn't be mixed into a recovery/documentation/bugfix commit.
- No direct edits to `/var/www/miniapp/` or `/home/promonta/agent/miniapp/` on the VPS without also syncing the change back into this repo (`/home/promonta/agent/miniapp-repo/`) and committing it. Skipping this is exactly how the repo and reality drifted apart before.

## Known deliberate limitations of this project (not gaps to "fix" without asking)

- No database, no ORM, no migrations — flat JSON files by design, adequate at current scale. See `docs/DATABASE.md` for when this should be revisited.
- No CI/CD, no automated tests yet — real gaps, tracked in `docs/TODO.md`, not to be silently worked around by fabricating fake passing results.
- Material/warehouse inventory and vehicle logbook (Fahrtenbuch) features are explicitly out of scope per an owner decision — don't build them without being asked again.
