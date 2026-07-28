# API

FastAPI backend, all routes in `backend/main.py`, prefixed `/api/`. Every route requires `Depends(get_current_user)` (Telegram `initData` HMAC auth — see [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md)); routes additionally gated `Depends(require_owner)` are marked **[owner]** below. No OpenAPI/Swagger UI has been confirmed exposed — FastAPI generates one by default at `/docs` unless explicitly disabled; UNVERIFIED whether that's reachable through Caddy (worth checking, since it would list every route+schema to anyone who finds the URL).

This is a route inventory grouped by feature area, built by grepping all `@app.get/post/patch/delete` decorators (93 confirmed) and spot-checking permission logic for the highest-risk ones (see ROLES_AND_PERMISSIONS.md for the routes actually read in detail). Request/response body shapes were **not** individually traced for every route in this pass — for exact field names, read the corresponding Pydantic `BaseModel` class near each route in `main.py` directly; don't guess from the URL.

## Meta / self

- `GET /api/health` — liveness check, no auth semantics of note beyond the standard gate.
- `GET /api/me` — current user's identity + role.

## Roles [owner-managed]

- `GET /api/roles` **[owner]** — whitelist + pending (notified-but-unwhitelisted) users.
- `POST /api/roles` **[owner]** — add/update a user's role.
- `DELETE /api/roles/{target_user_id}` **[owner]** — remove from whitelist.

## Objects (construction sites) & stages

- `GET /api/objects` — list, includes `assigned_users` and `image_path` per object.
- `POST /api/objects` **[owner]** — create.
- `PATCH /api/objects/{object_id}/status` **[owner]**.
- `GET /api/objects/{object_id}/stages` — list stages.
- `POST /api/objects/{object_id}/stages` **[owner]** — add stage.
- `PATCH /api/objects/{object_id}/stages/{row_num}` **[owner]**.
- `DELETE /api/objects/{object_id}/stages/{row_num}` **[owner]**.
- `POST /api/objects/{object_id}/assign` **[owner]** — assign worker to object/stage.
- `DELETE /api/objects/{object_id}/assign/{user_id}` **[owner]** — unassign.

## Tasks

- `GET /api/objects/{object_id}/tasks`, `GET /api/tasks` — list.
- `POST /api/objects/{object_id}/tasks` — any authenticated user, **not scoped to their own assignment** (see finding in ROLES_AND_PERMISSIONS.md).
- `POST /api/tasks` — create (general, not object-scoped).
- `POST /api/tasks/extract` — AI-assisted: turns free text into structured task(s).
- `PATCH /api/tasks/{task_id}` **[owner]** — edit.
- `PATCH /api/tasks/{task_id}/complete` **[owner]** — mark done. Note: only owner can complete, not the assignee — UNVERIFIED whether this is intentional (owner sign-off required) or a gap; worth a product-owner confirmation if a worker ever asks why they can't close their own task.

## Check-in / shifts

- `POST /api/checkin/start` — begin a shift session (GPS + photo).
- `POST /api/checkin/manual` — manual entry (no live GPS capture — e.g. for backfilling).
- `POST /api/checkin/{session_id}/finish` — end shift, summary/extra-work/next-day-needs fields.
- `POST /api/checkin/{session_id}/analyze-progress` / `analyze-defects` / `analyze-materials` — AI analysis of check-in photos, extracts structured findings.
- `GET /api/checkin` — list sessions; non-owner filtered to own records only (verified, see ROLES_AND_PERMISSIONS.md).
- `GET /api/checkin/{session_id}/photo/{which}/{index}` — serves a specific check-in photo; role-checked ownership per 2026-07-15 audit notes (not re-verified line-by-line here).
- `GET /api/checkin/stundenzettel` — timesheet export.

## Absence / calendar (Abwesenheit)

- `GET /api/abwesenheit` — own or relevant entries.
- `GET /api/abwesenheit/all` **[owner]** — everyone's.
- `POST /api/abwesenheit` — create request.
- `PATCH /api/abwesenheit/{entry_id}/status` **[owner]** — approve/reject.
- `PATCH /api/abwesenheit/{entry_id}/close` — worker closes their own open-ended entry early (per `server-structure.md` design notes — not re-verified here whether it's owner-gated or self-service; check code before assuming).
- `DELETE /api/abwesenheit/{entry_id}` — delete.

## Defects (Mangel)

- `GET /api/mangel`, `GET /api/mangel/{ticket_id}`, `GET /api/mangel/counts` — list/detail/counts.
- `POST /api/mangel` — create ticket.
- `PATCH /api/mangel/{ticket_id}/status` — update status.
- `GET /api/mangel/{ticket_id}/comments`, `POST /api/mangel/{ticket_id}/comments` — comment thread.
- `GET /api/mangel/photos/{fname}/file` — photo retrieval.

## Tools / equipment

- `GET /api/tools`, `GET /api/tools/{serial}/history` — list/history.
- `POST /api/tools` **[owner]** — register new tool.
- `PATCH /api/tools/{serial}` **[owner]** — edit.
- `PATCH /api/tools/{serial}/checkout` — any authenticated user, self-checkout by design (verified — see ROLES_AND_PERMISSIONS.md).

## Chat

- `GET /api/chat/messages`, `GET /api/chat/my_threads`, `GET /api/chat/threads/status`, `GET /api/chat/unread_count`, `GET /api/chat/unread_by_thread` — read-side (legacy/raw-storage shape, still what the live frontend uses).
- `GET /api/chat/threads?type=GENERAL|DIRECT|OBJECT|DEFECT|TASK` (2026-07-28, Phase 06) — normalized shape (`id`/`type`/`title`/`avatar_url`/`subtitle`/`last_message`/`unread_count`/`muted`/`pinned`/`archived`/`version`, `online` on `DIRECT` entries) across all 5 chat tab types. Additive, kept alongside the legacy endpoints above — no frontend UI reads it yet, groundwork for the Chat Hub rebuild. No cursor/pagination (see code comment: `CHAT_MAX` caps stored messages at 200 total).
- `POST /api/chat/messages` — send text. Rejects `to_user_id == self` with 400 (2026-07-28).
- `POST /api/chat/messages/attachment` — send file (8MB limit per prior session notes, UNVERIFIED still current). Rejects self-DM like above.
- `POST /api/chat/messages/voice` — send voice note (transcribed server-side via `faster-whisper`). Rejects self-DM like above.
- `DELETE /api/chat/messages/{msg_id}` — own messages only, or any if owner (verified). Also prunes that message's reactions (2026-07-28).
- `POST /api/chat/messages/{msg_id}/reactions` (2026-07-28, Phase 06) — body `{reaction}`, one of the fixed set `👍✅👀❗`; toggles that reaction for the caller on that message (uniqueness per message_id+user_id+reaction), returns the updated per-message summary. Same access check as reading the message (thread membership).
- `POST /api/chat/read` — mark read.
- `POST /api/chat/threads/close` / `reopen` **[owner]**.
- `POST /api/chat/threads/prefs` (2026-07-28, Phase 06) — body `{thread_key|to_user_id, muted?, pinned?, archived?}`, sets any subset of the three per-user flags on a thread. New real data layer (`chat_thread_meta.json`'s `user_prefs`), not wired to any frontend UI yet.
- `GET /api/chat/attachments/{fname}` — file retrieval, membership-checked per 2026-07-15 audit notes (not re-verified here).

## Critical alerts

- `GET /api/critical-alerts/pending` — list.
- `POST /api/critical-alerts` **[owner]** — create.
- `POST /api/critical-alerts/{alert_id}/ack` — any user, acknowledges (verified — by design).
- `POST /api/critical-alerts/{alert_id}/resolve` — any user, yes/no + note + photos (verified — by design).
- `GET /api/critical-alerts/{alert_id}/photo/{filename}` — photo retrieval.

## Feed (news/photos)

- `GET /api/feed/news`, `GET /api/feed/photos`, `GET /api/feed/birthdays`, `GET /api/feed/weather` — read-side.
- `POST /api/feed/photos` — post a photo.
- `GET /api/feed/photos/{photo_id}/comments`, `POST .../comments`, `DELETE .../comments/{comment_id}` — comment thread.
- `GET /api/feed/photos/{photo_id}/file` — file retrieval.
- `POST /api/feed/news/{post_id}/react`, `POST /api/feed/weather/react` — reactions.

## Profile / workers / users

- `GET /api/profile/me`, `PATCH /api/profile/me` — own profile (skills, sizes, birthday, onboarding).
- `POST /api/profile/me/avatar` — upload avatar.
- `GET /api/profile/stats` — own stats.
- `GET /api/profile/{user_id}/avatar` — someone else's avatar (public-within-app image, presumably low sensitivity).
- `GET /api/workers`, `GET /api/workers/{target_user_id}/calendar` — worker directory + calendar.
- `GET /api/users/{target_id}/card` — user summary card.

## Alerts (derived, not the critical-alerts entity)

- `GET /api/alerts` — computed alerts (budget/tools/assignment-type), generated on the fly, not a persisted store.

## AI

- `GET /api/ai-model`, `POST /api/ai-model` — select active AI model (Claude/GLM).
- `POST /api/ai-chat` — chat with AI assistant.
- `POST /api/ai-chat/upload` — attach a file/image to an AI chat turn.

## Documents (Angebot / Rechnung)

- `POST /api/angebot` — generate a quote PDF.
- `POST /api/rechnung` — generate an invoice PDF.

Both use the sibling `.js` files (`angebot_free.js`, `rechnung.js`) as templating/calculation helpers invoked from Python — UNVERIFIED exact invocation mechanism (subprocess vs. embedded JS runtime); check `main.py`'s import/call site before assuming either.
