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

## Operational risk found 2026-07-28: two Claude processes can write to this repo concurrently, unlocked

Discovered mid-session: `autonomous-miniapp.timer` (runs this phase-05-10 continuation every 3h) and the separate always-on Telegram-bot agent process (`bot.py`'s persistent `claude -p` session at `/home/promonta/agent`, which the owner can direct to edit here too — the top-level `CLAUDE.md` tells it to read this repo's own `CLAUDE.md` before working here, and it mostly did: its commits were small and well-scoped) were both live at the same time and both editing this working tree. Result: this session had 3 files staged-but-not-yet-committed for unrelated work; the other process's own commit (`git commit -a` or similar) swept those staged files into its commit, producing `9609941` — a commit whose message ("radio: add Гоп FM + Russian Hits stations...") doesn't mention the chat-polling-consolidation content it also contains. Verified byte-for-byte afterward: no content lost or corrupted, purely a commit-message/attribution problem, corrected in `docs/CHANGELOG.md`'s full write-up. Not fixed by rewriting history (needs owner approval per `CLAUDE.md`, and rebasing with a second live writer is its own hazard). **If you're a future session and see a commit whose diff doesn't match its message, check `docs/CHANGELOG.md` for a corrective note before assuming corruption.** A real fix (some kind of lock, or not running both agents against the same repo unattended) is an ops decision for the owner, not something to build unilaterally.

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

**(2026-07-28 update #4, supersedes the paragraph below)**: Phases 01-05 done. Phase 06 (Chat Hub full rebuild) is **in progress, not finished** — see `docs/plan-phases/06-chat-hub-rebuild.md` status section. This session: chat polling consolidated into 1 controller (was the top Phase 06 priority), plus several live owner requests handled ahead of the formal phase sequence (radio stations expanded to 21 total + infinite carousel + mini-player/FAB overlap fix, bottom-nav tab slide+fade transition) — all documented in `docs/plan-phases/08-radio-player-rebuild.md`'s status section and `docs/CHANGELOG.md`. **Also see the new "Operational risk found 2026-07-28" section above** — a concurrent-write race with the Telegram-bot agent process mislabeled one commit's content, corrected in the docs, no data lost. Current priority order for Phase 06 (per its own file): 1) expandable search state machine (largest remaining piece), 2) wire the normalized `GET /api/chat/threads` endpoint to frontend, 3) pin/mute/archive UI on top of the existing backend data layer, 4) granular read receipts (blocked on an architecture decision about per-message tracking). Phases 07-10 (Object Card rebuild, remaining Radio polish, Architecture split, Tests/docs final) follow once 06 is done, per `docs/HANDOFF_PHASE05_10.md`.

Older/superseded: Continue Batch 3 UI items if desired (all need a specific library/architecture decision first — charting for budget donut/sparklines, Kanban board pattern for tasks, drag-and-drop calendar) — see [TODO.md](TODO.md).
