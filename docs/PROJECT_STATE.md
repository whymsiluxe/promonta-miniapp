# Project state

**Last updated**: 2026-07-28 (autonomous session, Phase 06 Chat Hub rebuild in progress — see `docs/HANDOFF_PHASE05_10.md` and `docs/plan-phases/06-chat-hub-rebuild.md`).
**Branch**: `main` (GitHub default). `fix/security-reliability-p1` was superseded — its content shipped directly on `main` in earlier sessions (commits `d698a28`/`a564b6c`), confirmed 2026-07-25; that branch can be deleted, nothing left to merge from it.
**Repo**: https://github.com/whymsiluxe/promonta-miniapp — private (was made public 2026-07-23 for one-time ChatGPT read-only audit, reverted to private after this branch was pushed — see CHANGELOG).
**Working tree**: clean as of last commit in this session; not pushed to `origin` (this session has no confirmation it has push access/credentials configured the same way prior Mac sessions did — verify before assuming `origin/main` is current).

**Note (2026-07-28)**: the sections below this point (Incident log, mid-flight work, known bugs) describe state as of 2026-07-25 and predate a large amount of work done since (owner sent 6 new ТЗ on 2026-07-27, spawning `docs/plan-phases/01-10`; phases 01-04 are done, see those files' status markers and `docs/HANDOFF_PHASE05_10.md` for the authoritative current picture). Not rewritten wholesale this session — flagging so nobody trusts the stale detail below as current without checking `docs/plan-phases/` first.

## What this document is

The single place to check first after any session loss. If this contradicts something elsewhere, this file wins for "what's the current operational state" — other docs (ARCHITECTURE, FEATURES, etc.) are the detailed reference.

## Stack

Vanilla HTML/JS frontend (no build step) + FastAPI/Python backend + flat JSON file storage (no database) + Google Sheets for object/project data (via `objekte_lib.py`, shared with other Promonta agent scripts, not miniapp-specific). Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## Environments

Production only, single VPS (Hetzner, `162.55.53.147`, `app.promonta.fun`). No staging, no local dev environment set up yet. See [DEPLOYMENT.md](DEPLOYMENT.md).

## What's working

App is live, in active daily use. As of this update:
- Full doc-recovery completed (2026-07-23 morning): repo unified, secrets audited clean, documentation rebuilt from actual code.
- UI batch 1+2 shipped and deployed to production (2026-07-23 afternoon): radio widget repositioned under safe-area, Home tile previews (last chat message, nearest calendar event), news share button, Objects search/filter/sort, Chat thread list previews + day-grouping, Profile split into 3 tabs (Мой профиль/Команда/Настройки).
- **Old Money visual theme** shipped and deployed (2026-07-23 evening): replaces the previous beige/purple light theme with a deep-forest-green + gold restrained-luxury palette (`--bg-app: #0A0A0A`, `--accent: #0F3D2B`, `--accent-gold: #D4AF37`). Dark theme (`[data-theme=dark]`, green-neon) untouched. See [UI_UX.md](UI_UX.md) and [DECISIONS.md](DECISIONS.md).
- Google Sheets OAuth token incident (see below) resolved same day.

Most individual `FEATURES.md` rows are still marked **UNVERIFIED** — not suspected broken, just not re-traced end-to-end since the original recovery pass. See [TODO.md](TODO.md) REC-8.

## Incident log

**2026-07-23, ~17:00**: Objects screen stopped loading in production ("объекты не подгружаются"). Root cause: the Google OAuth refresh token used by `objekte_lib.py` to read the Objekte spreadsheet was revoked/expired (`invalid_grant` from Google, unrelated to the day's frontend deploys — confirmed by testing the token refresh directly and checking the OAuth consent screen's publish status, which was already "In production"). Fixed via manual browser re-authorization (owner) + token exchange over SSH; backend restarted. Full diagnostic/fix steps recorded in [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for next time. Old token backed up as `.gdrive_token.json.bak-<timestamp>` on the VPS (not in this repo — it's runtime credentials, gitignored).

## What's partially done / mid-flight

**`fix/security-reliability-p1` branch (2026-07-24)**: security/reliability audit fixes, pushed to origin but **not merged to main, not deployed**. Fixes the 15-site JSON-lock deadlock (roles/profile/assignments/chat-thread-meta/critical-alerts/abwesenheit), 4 authorization gaps (checkin_finish, checkin AI-analysis, mangel status, chat attachment thread access), missing upload validation on critical-alert resolve, a live 500 bug in checkin_manual, an unhandled malformed-input crash in validate_init_data, PII in the audit log, and splits the Потребности/Дефекты UI tab-mixing bug the user flagged live. Full detail in CHANGELOG.md's 2026-07-24 entry. Awaiting explicit go-ahead to merge + deploy.

Second track (UI/UX redesign, per a separate ChatGPT brief) planned but not started — see the local plan file, not yet in this repo's docs.

## What's broken / known bugs

- Chat/AI tab scroll behavior — unresolved as of last note (predates this recovery), 3 architecture attempts, landed on one not confirmed working by the user. See [UI_UX.md](UI_UX.md).

## What requires verification before trusting it

- Whether `angebot-tab.html` / `projects-tab.html` / `tools-tab.html` are live or dead frontend code.
- Whether FastAPI's `/docs` Swagger UI is publicly reachable (a real exposure if so — not yet checked).
- Most of the 93 backend routes' permission scoping beyond the ones spot-checked in the recovery pass (GPS check-in filtering, chat message deletion, tool checkout, critical alert ack/resolve — all confirmed correct).

## Security risks (flagged, not silently patched)

- `POST /api/objects/{object_id}/tasks` — any authenticated worker can add a task to any object, not just their own assignment. Low severity, product-level gap, not a data leak. See [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md).
- No automated secret-scanning or dependency-vulnerability checking exists (no CI at all yet).
- Personal/GPS employee data has no formal retention/deletion policy (GDPR-relevant, Germany-based employer) — see [SECURITY.md](SECURITY.md).

## Technical debt

- No local dev environment, no automated tests, no CI/CD. See [TODO.md](TODO.md) P0/P1.
- Frontend deploy is still manual (`scp` + backup + restart), no automated pipeline from `git push` to production — see [DEPLOYMENT.md](DEPLOYMENT.md) and [TODO.md](TODO.md) REC-1.

## Decisions made this session (owner, 2026-07-23)

- Old Money theme replaces light mode entirely (dark-neon theme untouched).
- Skipped: `tg.CloudStorage` for theme/reactions (async flash-of-wrong-state risk not worth it for device-local prefs), tools overdue-notification + photo-at-checkout (needs backend migration, owner doesn't want it now), chat location-attachment (redundant — check-in GPS already establishes on-site presence), QR scanner (deferred to a possible future native iOS app, not needed for the Telegram Mini App).
- Confirmed keeping "Размеры одежды" (clothing sizes) in Profile → Настройки — an earlier AI-generated prompt suggested removing it, owner said no.
- Considering a native iOS app eventually — backend/API would carry over close to as-is (it's already a plain REST API, only `initData` auth is Telegram-specific), but all frontend code would be rewritten from scratch (no shared code between vanilla-JS-Telegram-WebView and native iOS). QR scanner logged as the first candidate feature for that future app.

## Next recommended step

**(2026-07-28 update #2, supersedes the paragraph below)**: Phases 01-05 done. Phase 06 (Chat Hub full rebuild) is **in progress, not finished** — see `docs/plan-phases/06-chat-hub-rebuild.md` status section and `docs/CHANGELOG.md`'s "Phase 06 Chat Hub rebuild, partial" entry for the full list. Shipped and deployed this pass: the 5-vs-4-tabs decision (kept 5, see `docs/DECISIONS.md`), self-DM rejection, message reactions (backend + UI), a real mute/pin/archive data layer (backend only, no UI yet), a normalized `GET /api/chat/threads` endpoint (backend only, not consumed by frontend yet), the always-dark chat palette, a worker strip above the tabs, and a first (backend-only) unit test file. Still open, in priority order for the next session: the expandable search state machine, consolidating the 2 chat polling timers into 1, granular read receipts, and actually wiring the new normalized endpoint + mute/pin/archive to frontend UI. Phases 07-10 (Object Card rebuild, Radio polish, Architecture split, Tests/docs final) follow in order per `docs/plan-phases/README.md` once 06 is done.

Older/superseded: Continue Batch 3 UI items if desired (all need a specific library/architecture decision first — charting for budget donut/sparklines, Kanban board pattern for tasks, drag-and-drop calendar) — see [TODO.md](TODO.md).
