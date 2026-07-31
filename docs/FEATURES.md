# Features

Status legend: WORKING (frontend+backend+persistence traced and confirmed) · BACKEND_ONLY (route exists, frontend caller not confirmed in this pass) · UNVERIFIED (code present, full flow not traced end-to-end in this recovery) · PARTIAL · MOCK · BROKEN · NOT_IMPLEMENTED.

Most rows here are **UNVERIFIED** rather than WORKING — this recovery pass read `main.py`'s route table and permission logic in detail, but did not trace every frontend JS module's fetch calls against every backend route line-by-line (that's a larger follow-up pass, see TODO.md). Treat UNVERIFIED as "present in code, believed functional based on session history, not re-confirmed today" — not as "broken" or "untrusted."

**Update 2026-07-31**: a release-readiness pass (see `docs/RELEASE_AUDIT.md`) re-traced Check-in, Chat, and Tools end-to-end via automated tests (151 tests, `tests/*.py`) — those 3 rows below flipped from UNVERIFIED to WORKING with a specific note on what was actually confirmed. The rest of the table is untouched from the prior recovery pass and still needs the same line-by-line trace described above before trusting it as WORKING.

| Module | Feature | Role | Frontend | Backend routes | Data store | Status | Notes |
|---|---|---|---|---|---|---|---|
| Auth | Telegram initData validation | all | `app.html` (Telegram WebApp SDK init) | `get_current_user()` gate on every route | — | WORKING | HMAC scheme verified correct in code read |
| Roles | Whitelist management | owner | UNVERIFIED which JS file | `/api/roles*` | `roles.json` | UNVERIFIED | Backend confirmed owner-gated |
| Objects | List/create/edit sites & stages | both (create=owner) | `js/objects.js` | `/api/objects*` | (JSON, via `objekte_lib.py` — not in this repo, lives in `/home/promonta/agent/`) | UNVERIFIED | `objekte_lib.py` is a *shared* Promonta-wide module, not miniapp-specific — see ARCHITECTURE note |
| Objects | Worker assignment (bubble drag-drop) | owner assigns | `js/bubble-assign.js` | `/api/objects/{id}/assign` | `object_assignments.json` | UNVERIFIED | Custom pointer-event drag, not HTML5 DnD (touch-compatible, per prior session notes) |
| Tasks | Create/list/complete | worker creates, owner completes | `js/tasks.js` | `/api/tasks*` | `tasks.json` | UNVERIFIED | See API.md note: only owner can mark complete |
| Tasks | AI extraction from free text | both | `js/tasks.js`(?) | `/api/tasks/extract` | — | UNVERIFIED | |
| Check-in | Start/finish shift, GPS+photo | worker | `js/checkin.js`, `js/worker-checkin-fab.js` | `/api/checkin*` | `checkin_meta.json` + `checkin_photos/` | WORKING (backend confirmed) | Own-data filter confirmed on `/finish` and every session-scoped route; `checkin_meta.json` now atomic write (2026-07-31); `object_id` from client now path-traversal-sanitized. Frontend flow not re-traced this pass. |
| Check-in | AI analysis (progress/defects/materials) | worker/owner | UNVERIFIED | `/api/checkin/{id}/analyze-*` | — | UNVERIFIED | |
| Abwesenheit | Request/approve absence, partial-day | worker requests, owner approves | `js/abwesenheit.js` | `/api/abwesenheit*` | `abwesenheit.json` | UNVERIFIED | Open-ended entries + approval workflow per prior session notes |
| Mangel | Defect tickets + comments | both | `js/mangel.js` | `/api/mangel*` | `mangel_tickets.json` | UNVERIFIED | |
| Tools | Inventory, checkout/return, history | both | `js/tools.js` | `/api/tools*` | Google Sheets via `backend/tools_lib.py` (now git-tracked, isolated import) | WORKING (redesigned+tested 2026-07-30/31) | Full redesign this session: compact summary, richer search, worker no longer types own name (backend derives from Telegram identity), real `/return` endpoint (was misusing `/checkout` w/ empty fields — real bug, fixed). 13+ backend tests cover checkout/return/holder-name logic. |
| Chat | 1:1 + object threads, attachments, voice | both | `js/chat.js` | `/api/chat/*` | `chat_messages.json`, `chat_reads.json`, `chat_thread_meta.json`, `chat_attachments/` | WORKING (backend confirmed) | Voice transcription via `faster-whisper` confirmed. Attachments/voice now validate content via magic-byte allowlist (2026-07-31 — were previously accepting any file type, real stored-XSS risk, closed). Unread counter bug fixed 2026-07-31 (thread-scoped messages were mis-attributed to the global group counter for every user). |
| Critical alerts | Push alert, ack/resolve with photo | owner creates, worker acts | `js/critical-alerts.js` | `/api/critical-alerts*` | `critical_alerts.json` + `critical_alert_photos/` | UNVERIFIED | Polling-based per prior session notes (not WebSocket) |
| Feed | News/photos, comments, reactions | both | `js/feed.js` | `/api/feed/*` | `feed_photos.json`, `news_reactions.json`, `news_reads.json` | UNVERIFIED | |
| Feed | Weather widget | both | `js/feed.js`(?) / `js/home.js` | `/api/feed/weather` | `.weather_feed.json` (shared, outside miniapp dir per server-structure.md) | UNVERIFIED | Object-selector tabs, hourly breakdown per prior notes |
| Profile | Skills/sizes/birthday, avatar | own | `js/profile.js` | `/api/profile/*` | `worker_profiles.json`, `avatars/` | UNVERIFIED | |
| Onboarding | First-run skills quiz | worker | `js/onboarding.js` | `PATCH /api/profile/me` (`quiz_completed`) | `worker_profiles.json` | UNVERIFIED | |
| AI chat | Assistant chat, model switch | both | `js/ai.js` | `/api/ai-chat*`, `/api/ai-model` | `ai_model.json`, `ai_chat_rate.json` | UNVERIFIED | Claude CLI bridge + GLM fallback |
| Documents | Angebot (quote) PDF | owner | UNVERIFIED which JS | `POST /api/angebot` | `angebote/*.pdf` | UNVERIFIED | Also has standalone `angebot-tab.html` — relationship to in-app flow unclear, verify before assuming either is dead |
| Documents | Rechnung (invoice) PDF | owner | `js/rechnung.js` | `POST /api/rechnung` | `rechnungen/*.pdf` | UNVERIFIED | |
| Radio | Background music widget | both | `js/radio.js` | none (client-side, hardcoded station URLs) | — | UNVERIFIED | Not backend-integrated by design |
| Navigation | Role-based bottom nav, swipe between tabs | both | `app.html` (`applyRoleNav()`), `js/swipe-nav.js` | — | — | UNVERIFIED | Chat/AI category tabs explicitly excluded from swipe gesture per recent decision (see git log `frontend`) |
| Legacy tabs | `angebot-tab.html`, `projects-tab.html`, `tools-tab.html` | ? | standalone HTML files | ? | ? | **UNVERIFIED — possibly dead** | Not confirmed linked from current `app.html` shell; do not delete without checking, do not assume live without checking either |

## Explicitly out of scope / not built (per prior owner decisions, recorded in server-structure.md)

- Material/warehouse inventory tracking (Materialverwaltung) — owner decision to exclude, not a bug.
- Fahrtenbuch (vehicle logbook) — same, owner decision to exclude.

## How to move a row from UNVERIFIED to WORKING

Trace the specific frontend JS call site → confirm it hits the listed backend route → confirm the backend route persists to the listed store → manually exercise the flow per [TESTING.md](TESTING.md)'s checklist → update this row and note the date verified. Don't flip a row to WORKING without having done this — see governance rules in [CLAUDE.md](../CLAUDE.md).
