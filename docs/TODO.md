# TODO

## P0 — blocking / foundational

- **REC-1**: Set up a real deploy path from this repo to the VPS (rsync/scp script or CI job), replacing direct SSH edits + `.bak-pre-*` convention. *Why*: direct-edit-on-prod is what caused the original session-loss/doc-drift problem. *Status*: TODO.
- **REC-2**: Decide what to do with the stale local Mac copy at `~/Projects/promonta/miniapp/frontend/` (dated Jul 8-12, now superseded by this repo). *Why*: risk of someone accidentally treating it as current. *Status*: TODO — needs owner/user decision, not unilateral deletion (destructive-action rule).
- **REC-3**: Full endpoint-by-endpoint permission audit (all 93 routes, not just the ones spot-checked in this recovery — GPS/chat/tools were checked, most others weren't). *Why*: `docs/ROLES_AND_PERMISSIONS.md` currently says most routes are unverified. *Status*: TODO.
- **REC-4**: Verify whether FastAPI's auto-generated `/docs` (Swagger UI) is reachable through Caddy in production. *Why*: if so, it exposes the full route/schema list publicly. *Status*: TODO, quick check (`curl https://app.promonta.fun/docs`).
- **REC-5**: Determine if `angebot-tab.html`, `projects-tab.html`, `tools-tab.html` are still linked from `app.html` or are dead code. *Why*: can't safely delete or maintain without knowing. *Status*: TODO.

## P1 — important

- **REC-6**: Introduce at least one automated check (even just a Python syntax check / `python -m py_compile main.py` in a pre-push hook) — there is currently zero automated verification of any kind.
- **REC-7**: Add `load_dotenv()` to `main.py` (or document that it's intentionally absent) so local development can use a `.env` file instead of manually exported shell vars.
- **REC-8**: Trace every FEATURES.md row currently marked UNVERIFIED to WORKING or its true status, one feature area at a time, per the checklist in TESTING.md.
- **REC-9**: Decide whether `POST /api/objects/{object_id}/tasks` should be assignment-scoped (see ROLES_AND_PERMISSIONS.md finding).
- **REC-10**: Confirm upload size limits are consistent across all upload routes (chat=8MB confirmed, others unverified).

## P2 — improvements

- Sanitized fixture/seed data for local development and any future automated tests (currently no safe way to run this app without touching production data).
- CODEOWNERS file (needs the owner's actual GitHub username — not guessed in this pass).
- Branch protection on `main` once the repo has collaborators beyond the owner.

## P3 — future ideas

- Staging environment (currently production-only).
- Consider whether the JSON-file data layer needs to become a real database — not urgent at current scale (see DATABASE.md), but worth revisiting if concurrency or reporting needs grow.

## Explicitly out of scope (owner decision, not a gap)

- Material/warehouse inventory (Materialverwaltung).
- Fahrtenbuch (vehicle logbook).

## UI/UX follow-ups carried from prior sessions (not yet independently re-verified)

- Chat/AI tab scroll bug — last known state: 3 approaches tried, landed on "variant B", **not confirmed working by the user**. Verify before touching this area again.
- 2026-07-22 late-session visual redesign (luxury splash, flat-square icons, warm palette) was mid-flight when the session that prompted this recovery was lost — give it a look before assuming it's in a finished state.

## UI batch 2026-07-23 (owner request, prioritized by risk/effort — vanilla JS, no React)

Source: owner-provided audit list. React/TSX starter code in that list does not apply — this is a vanilla HTML/JS app, no bundler, no React. Section 8 (React.memo, code-splitting, useCallback) is skipped entirely as inapplicable; section 6 (performance) items are reinterpreted for vanilla JS where a vanilla equivalent exists.

Being worked in dedicated branches (`feat/ui-batch-1`, etc.), one screen/feature per commit, pushed incrementally so progress is visible on GitHub. Full list, ordered by what's being tackled first:

**Batch 1 — low-risk, high-value, no new dependencies** (in progress):
- [ ] Home: remove radio widget
- [ ] Home: "4 АЛЕРТЫ" tile becomes tappable → opens alerts view (partially exists via `_renderAlerts()`, verify/extend)
- [ ] Home: "Сообщения" tile shows last message preview
- [ ] Home: "Общий календарь" tile shows next upcoming event
- [ ] News: "Читать источник" opens via `tg.openLink()` instead of default anchor behavior (verify current behavior first)
- [ ] News: Share button via `tg.shareURL()`
- [ ] News: likes/dislikes persisted via `tg.CloudStorage` instead of (or in addition to) the existing `news_reactions.json` backend store — needs a decision: is CloudStorage replacing server-side storage (breaks cross-device sync) or supplementing it (optimistic UI)? Flagging before building, not assuming.
- [ ] Theme: adopt `tg.themeParams` for color adaptation, persist any user override via `tg.CloudStorage`

**Batch 2 — moderate effort, existing patterns to extend**:
- [ ] Objects: filters (city, status, budget), sort (progress/date/budget), search bar with 300ms debounce
- [ ] Objects: stacked-avatar team indicator on cards (people-dots already exist per `server-structure.md` — check if this already satisfies the ask before rebuilding)
- [ ] Chat list: last message + time + unread count (partially exists — `unread_by_thread` endpoint already returns counts, verify frontend renders preview text)
- [ ] Chat thread: timestamp grouping ("Сегодня" etc.)
- [ ] Chat: attach location (photo/document attachment already exists per API.md — location is the new part)
- [ ] Tools: notification when overdue return (backend logic needed — check if any expiry field exists in the tool data shape first)
- [ ] Tools: photo of condition at checkout/return

**Batch 3 — higher effort / new UI patterns, needs its own scoping pass before starting**:
- [ ] Object detail: tabs (Overview/Tasks/Documents/History/Budget) — likely a real restructure of the object detail view, not a tweak
- [ ] Object detail: budget donut chart (needs a charting approach decision — no charting library currently in the project)
- [ ] Object detail: task Kanban board (To Do/In Progress/Done) — new interaction pattern, drag-and-drop
- [ ] Object detail: documents grid with preview instead of list
- [ ] Chat: swipe-to-reply gesture
- [ ] Chat: voice messages via `tg.startRecordVideo()`/`stopRecordVideo()` — note: those are Telegram's *video* recording APIs, not audio; the app already has voice notes via a different mechanism (`POST /api/chat/messages/voice`, faster-whisper transcription) — verify which is actually wanted before implementing, this may be describing an already-existing feature incorrectly
- [ ] Calendar: week/month/year views, color-coded by type, drag-and-drop event rescheduling, bottom-sheet on day tap
- [ ] Profile: split into Мой профиль / Команда / Настройки — restructure, not a tweak
- [ ] Profile: interactive Stundenzettel chart instead of a number
- [ ] Profile: skills as progress bars instead of a list
- [ ] Profile: clothing sizes as an EU/US/UK conversion table
- [ ] Tools: QR-code scanner for lookup (needs a camera/QR library decision)
- [ ] Tools: availability-calendar-based booking (new feature, not in current data model — `object_assignments.json`-style scoping would need a tools equivalent)
- [ ] Home stat cards: sparkline mini-trend-graphs (needs a charting approach decision, same as budget donut)
- [ ] News: tag-based category filter
- [ ] Virtual scrolling for lists >20 items (vanilla equivalent: manual windowing or a small library — no framework virtualization available without React)
- [ ] Image lazy loading + blur placeholder (`loading="lazy"` + a blurred low-res placeholder — doable in vanilla JS, no library needed)

**Explicitly deferred pending a security/architecture decision, not silently built**:
- [ ] Backend: rate limiting across all API routes (currently only AI chat has rate limiting per `ai_chat_rate.json`) — needs scoping, could affect legitimate burst usage (e.g. photo uploads during check-in)
- [ ] Backend: CSP headers — needs Caddy config change, touches `docs/DEPLOYMENT.md`
- [ ] `tg.initData` HMAC validation — **already implemented and verified correct** in `main.py` (see `docs/SECURITY.md`), the owner's list re-requesting this is already satisfied, not a gap
- [ ] "Don't store sensitive data in localStorage, only `tg.CloudStorage`" — worth an audit of current `localStorage` usage across `js/*.js` before assuming a violation exists; not yet checked in this pass
