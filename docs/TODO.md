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

**Batch 1 — low-risk, high-value, no new dependencies** (done, branch `feat/ui-batch-1`, not yet deployed to production — owner wants to accumulate more before deploying):
- [x] Home: radio widget — owner decided **relocate, not remove** (was blocking bottom-nav zone conceptually). Moved to top-right under `--tg-safe-top` (Dynamic Island/status-bar safe zone), 82px glove-friendly size kept. Commit `02e19a1`.
- [x] Home: "4 АЛЕРТЫ" tile tappable → **already implemented** in both owner (`kpi-alerts` → `openAlertsView()`) and worker (`_openWorkerAlerts()`) dashboards. No code change needed.
- [x] Home: "Сообщения" tile shows last message preview — owner dashboard only (worker's compact 2x2 tile has no room without breaking layout). Reuses `last_preview` already returned by `GET /api/chat/my_threads`. Commit `b10c38f`.
- [x] Home: "Общий календарь" tile shows next upcoming event — was showing a static this-month count, now shows the actual nearest absence entry (who/reason/date). Commit `b10c38f`.
- [x] News: "Читать источник" via `tg.openLink()` — **already implemented** (`openExternalLink()` in `shared.js`, existing code, has a `window.open` fallback). No change needed.
- [x] News: Share button via `tg.shareURL()` — was missing entirely for news (existed for weather posts only, different data shape). Added `shareNewsLink()`, prefers `tg.shareURL(url, title)`, falls back to `navigator.share` then clipboard. Commit `dbdd4be`.
- [ ] ~~News: likes/dislikes via `tg.CloudStorage`~~ — **skipped, owner decision**: source of this ask was unclear/possibly not the owner's own intent ("хуй знает это не я писал"), and it would duplicate the existing server-side `news_reactions.json` store, risking cross-device desync. Not building without a clearer ask.
- [ ] ~~Theme: `tg.themeParams` auto-adaptation~~ — **skipped, owner decision**: light theme was deliberately fixed on 2026-07-22 after a bug where dark-Telegram users saw a broken old dark style; owner does not want theme auto-following Telegram again. Also skipped moving the manual theme toggle from `localStorage` to `tg.CloudStorage` — CloudStorage is async and would risk a flash-of-wrong-theme on load that localStorage's synchronous read avoids; not worth it for a device-local preference.

**Batch 2 — moderate effort, existing patterns to extend**:
- [ ] Objects: filters (city, status, budget), sort (progress/date/budget), search bar with 300ms debounce
- [ ] Objects: stacked-avatar team indicator on cards (people-dots already exist per `server-structure.md` — check if this already satisfies the ask before rebuilding)
- [ ] Chat list: last message + time + unread count (partially exists — `unread_by_thread` endpoint already returns counts, verify frontend renders preview text)
- [x] Chat thread: timestamp grouping ("Сегодня" etc.) — day-dividers added to thread detail view. Commit `98b0e25`.
- [ ] ~~Chat: attach location~~ — **rejected, owner decision (2026-07-23)**: check-in already captures GPS at shift start (`checkin_meta.json`), which already establishes the worker is on-site — a separate location-in-chat message would be redundant. Not building.
- [ ] ~~Tools: notification when overdue return~~ — **rejected, owner decision (2026-07-23)**: would need a new backend field + data migration for zero current benefit to the owner. Not building.
- [ ] ~~Tools: photo of condition at checkout/return~~ — **rejected, owner decision (2026-07-23)**: same reasoning, no backend endpoint accepts a photo on checkout currently and owner doesn't want the migration work for it. Not building.

**Batch 3 — higher effort / new UI patterns, needs its own scoping pass before starting**:
- [ ] Object detail: tabs (Overview/Tasks/Documents/History/Budget) — likely a real restructure of the object detail view, not a tweak
- [ ] Object detail: budget donut chart (needs a charting approach decision — no charting library currently in the project)
- [ ] Object detail: task Kanban board (To Do/In Progress/Done) — new interaction pattern, drag-and-drop
- [ ] Object detail: documents grid with preview instead of list
- [ ] Chat: swipe-to-reply gesture
- [ ] Chat: voice messages via `tg.startRecordVideo()`/`stopRecordVideo()` — note: those are Telegram's *video* recording APIs, not audio; the app already has voice notes via a different mechanism (`POST /api/chat/messages/voice`, faster-whisper transcription) — verify which is actually wanted before implementing, this may be describing an already-existing feature incorrectly
- [ ] Calendar: week/month/year views, color-coded by type, drag-and-drop event rescheduling, bottom-sheet on day tap
- [x] Profile: split into Мой профиль / Команда / Настройки — done as an in-page segmented-tab control (not separate routed views), zero markup deleted, all existing handlers/IDs preserved. Commit `aaef194`.
- [ ] Profile: interactive Stundenzettel chart instead of a number — deferred, same charting-library decision as budget donut/sparklines below.
- [ ] ~~Profile: skills as progress bars instead of a list~~ — **skipped, data doesn't support it**: `worker_profiles.json` stores `skills` as a flat `list[str]` (skill names only), no proficiency/level field anywhere in the backend model (`main.py` lines ~278-559). A progress bar needs a 0-100 value; faking one would misrepresent actual worker skill data. Needs a product decision (add a level field + UI to set it) before this is buildable, not a frontend-only task.
- [ ] ~~Profile: clothing sizes as an EU/US/UK conversion table~~ — **skipped, data doesn't support it**: sizes are stored as free-text strings (e.g. "52 / L", "XL", "44"), not a known size *system* per field — no way to know which system a given string is already in, so no reliable conversion is possible without asking workers to re-enter sizes in a structured format first. Same category of gap as skills above.
- [ ] ~~Tools: QR-code scanner for lookup~~ — **not needed for the current Telegram Mini App (owner decision, 2026-07-23)**. Camera-based QR scanning is a much better fit for a native phone app than a Telegram WebView. If a native app gets built, this belongs there, not here.
- [ ] Tools: availability-calendar-based booking (new feature, not in current data model — `object_assignments.json`-style scoping would need a tools equivalent)
- [ ] Home stat cards: sparkline mini-trend-graphs (needs a charting approach decision, same as budget donut)
- [ ] News: tag-based category filter
- [ ] Virtual scrolling for lists >20 items (vanilla equivalent: manual windowing or a small library — no framework virtualization available without React)
- [ ] Image lazy loading + blur placeholder (`loading="lazy"` + a blurred low-res placeholder — doable in vanilla JS, no library needed)

**Future native phone app backlog** (owner mentioned possibly building a native app later — logging ideas here so they aren't lost, not started):
- [ ] QR-code scanner for tool lookup — camera-based, natural fit for native, awkward in Telegram WebView.

**Explicitly deferred pending a security/architecture decision, not silently built**:
- [ ] Backend: rate limiting across all API routes (currently only AI chat has rate limiting per `ai_chat_rate.json`) — needs scoping, could affect legitimate burst usage (e.g. photo uploads during check-in)
- [ ] Backend: CSP headers — needs Caddy config change, touches `docs/DEPLOYMENT.md`
- [ ] `tg.initData` HMAC validation — **already implemented and verified correct** in `main.py` (see `docs/SECURITY.md`), the owner's list re-requesting this is already satisfied, not a gap
- [ ] "Don't store sensitive data in localStorage, only `tg.CloudStorage`" — worth an audit of current `localStorage` usage across `js/*.js` before assuming a violation exists; not yet checked in this pass
