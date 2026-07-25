# Changelog

## Unreleased

### Added
- `docs/` directory: PROJECT_STATE, ARCHITECTURE, FEATURES, ROLES_AND_PERMISSIONS, API, DATABASE, UI_UX, DEPLOYMENT, TESTING, DECISIONS, TODO, SESSION_HANDOFF, SECURITY, ENVIRONMENT, TROUBLESHOOTING, RELEASE_PROCESS.
- `README.md`, `CLAUDE.md` (governance rules for this repo).
- `backend/.env.example`, `backend/requirements.txt` (neither existed before).
- `.gitignore` covering secrets and all runtime JSON/media data.
- GitHub PR/issue templates.

### Changed
- Backend (`/home/promonta/agent/miniapp/`) and frontend (`/var/www/miniapp/`) merged into one repo, `backend/` + `frontend/` subdirectories. Frontend's existing 14-commit git history preserved via `git subtree`.

### Documentation
- Corrected a stale claim from `server-structure.md` (2026-07-15 note): unknown Telegram user IDs get a **403**, not a silent `worker` role default — that changed with a whitelist hardening ("Фаза 10.1") since that note was written.
- Flagged one product-level permission gap for owner review (not silently fixed): `POST /api/objects/{object_id}/tasks` lets any authenticated worker add a task to any object, not just their assigned one. See `docs/ROLES_AND_PERMISSIONS.md`.

## 2026-07-25 (Mac session — Object Details tabs, security/UI plan closeout)

### Added
- **Object Details screen (6 tabs)**: tapping an object card opens Chat/Инфо/Задачи/Потребности/Дефекты/Этапы instead of the old single-card "Этапы объекта" screen. Chat tab is truly embedded under the tab bar (physically re-parents `#chat-thread-detail-view`, not a fullscreen overlay — user explicitly rejected the first fullscreen-overlay version). Инфо tab is a new feature: free-text work-items + document upload/viewer (new `OBJECT_INFO_FILE` store, `object_documents/` dir). Задачи/Потребности reuse existing endpoints (added `object_id` filter to `GET /api/tasks`, previously missing). Дефекты switched to the already-existing but unused `GET /api/mangel?object_id=` filter. Этапы got a visual roadmap with owner up/down reorder (`swap_stage_order()` in `objekte_lib.py`, lives outside the repo) and a worker-only "Готово" button restricted server-side to the object's actual current stage.
- **Unread badges for thread_key-based chat threads** (Объекты/Дефекты/Потребности tabs in the chat list) — `GET /api/chat/unread_by_thread` only ever counted group/DM threads before; extended to thread_key threads too.
- **Alert read-tracking**: derived `/api/alerts` (budget/tools/assignment) had no "read" concept — added `alert_dismissals.json` per-user dismiss layer, 24h TTL, so closing the alerts modal drops the Home counter but an unresolved problem resurfaces after a day instead of vanishing forever.
- **Colored avatars**: chat message header (name+time row, no bubble background — Connecteam-style restyle), Profile → Команда list, both via the existing `_chatAvatarHue()` technique.
- **"Назначить на объект" from worker profile** (`openAssignFromProfile()` in bubble-assign.js) — reverse flow to the existing drag-and-drop assignment.
- **NavigationHeader**: unified 3D ivory back-button (chevron SVG, press-state) applied to all ~12 screens via a one-time DOM upgrade pass — `NavigationManager`'s stack/back()/Telegram-BackButton logic was already in place from an earlier session, this was the missing visual piece from the plan.

### Fixed
- **Checkin finish targeted the wrong object_id**: the new Stages-tab checkin shortcut used the *currently open* object's ID instead of the object the shift was actually running on (`_findActiveWorkerCheckinObjectId()`'s result was computed but not used) — finishing a shift from a different object's screen left the real session open server-side ("Смена идёт" never cleared). Live-reported and confirmed via journalctl (the finish POST returned 200 but targeted an unrelated/missing session).
- **Vertical swipe closed the whole Mini App, chat/AI screens only**: `switchView()` called `Telegram.WebApp.enableVerticalSwipes()` specifically for chat/AI based on a wrong assumption (that it also gates internal container scroll — it doesn't, that's a separate mechanism). Now always calls `disableVerticalSwipes()`, no per-view exception.
- **Global swipe-nav ate horizontal scroll on filter/tab rows**: `.obj-filter-row` (Objects list), `#tools-filters`, `.profile-tabs`, `.profile-period-pills`, `.wx-city-tabs`, `.wx-object-tabs` were all `overflow-x:auto` but missing from `swipe-nav.js`'s exclusion list — scrolling them sideways instead fired the global tab-switch. Audited every `overflow-x:auto/scroll` rule in `app.html` (9 total) instead of fixing these one at a time as reports came in.
- **Photo comments composer collapsed under the keyboard** — same root cause as the earlier chat keyboard-jank fix (`.photo-comments-modal` relied on bare `inset:0` + browser resize, which Telegram fullscreen doesn't shrink on keyboard open). Applied the same `--tg-vp-height` fix, plus swapped the `<input>` composer for a `<textarea>`.
- Remaining emoji flagged by the UI/UX plan: crown (👑, nav tab + profile role badge → brass dot indicator / plain text), lightning bolt (⚡, "Работа по фото" card → SVG), news feed reactions (👍👎📤 → SVG icons).
- **Server file permissions**: `/home/promonta/agent/miniapp-repo` had been fully owned by `root` (likely from an earlier Fable/autonomous run using root-level process access), blocking the `promonta` user from writing at all. Fixed with `chown -R promonta:promonta`; also copied git credentials from `/root/.git-credentials` to `/home/promonta/.git-credentials` so `promonta` can push without needing root going forward. Documented in `~/.claude/server-structure.md` on the Mac side.

### Verified as already done (plans were stale, not re-implemented)
Re-checked line-by-line and confirmed already shipped in earlier sessions (commits `d698a28`/`a564b6c`/`2f4b511`/dated comments from `22.07`/`24.07`): the entire Security & Reliability P1 plan (all 15 deadlock sites, every authorization gap, audit-log PII redaction), UI/UX Phase 0 (z-index assignment-popup bug), Phase 3 (RaisedTab 3D cards, KPI rebalance, compact weather card), Phase 4a (multi-photo posts, gallery picker), and most of Phase 5 (Profile accordions collapsed by default). Both plan files at `/Users/mac/.claude/plans/` on the Mac side annotated with STATUS notes so they stop looking actionable.

### Not verified
None of today's ~20 commits were tested on a physical device/real Telegram client — only code review, `node --check`/`py_compile`, and inline-script parsing. Flagging honestly per this project's no-test-framework reality; next session should start with live verification, especially the embedded chat tab and the checkin object-id fix.

### Open
- Tools screen still 404s from Google Sheets — the OAuth token was never re-consented for that specific spreadsheet after the last token reissue (same root cause as the earlier Objekte fix). Needs the owner to walk through Google's consent screen again; deferred at their request ("не срочно").
- A checkin session opened 2026-07-22 on OBJ-001 (user 872079437) is still unclosed server-side — left untouched, not this session's data to close without confirmation.

## 2026-07-25 (audit fixes — Grok/MiniMax external review)

### Fixed
- **Swagger/OpenAPI exposed** (`backend/main.py`): `FastAPI(...)` now sets `docs_url=None, redoc_url=None, openapi_url=None` — `/docs`, `/redoc`, `/openapi.json` were reachable on the backend port (127.0.0.1:8001/docs returned 200 before the fix, 404 after), exposing the full route/schema map. Public `app.promonta.fun/docs` was a false alarm on investigation — Caddy's SPA `try_files` fallback served `app.html` there regardless, not real Swagger UI — but the backend-level fix closes the actual exposure and is correct defense-in-depth regardless.
- **Dead legacy files servable directly**: `angebot-tab.html`, `projects-tab.html`, `tools-tab.html` (unreferenced by `app.html`/any JS, last touched 2026-07-08, predate current auth model) were served as-is by Caddy on `/var/www/miniapp/` before falling through to the SPA. Archived to `frontend/.archived-legacy/` in repo, moved to a timestamped backup dir on the live frontend host — confirmed all three paths now 200-fallback to the SPA shell instead of serving their own content.

### Added
- **CSP + security headers** (`/etc/caddy/Caddyfile`, not repo-tracked): `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`. `script-src`/`style-src` keep `'unsafe-inline'` (app.html has one inline `<script>` block + 18 `onclick=` attributes — removing needs a separate frontend refactor, not bundled here). `X-Frame-Options` deliberately omitted — would conflict with Telegram's WebView iframe embedding; `frame-ancestors` in the CSP already scopes that correctly. Google Fonts domains added to `style-src`/`font-src` after live-testing caught the initial policy blocking them. Verified via Playwright against the live page: zero CSP violations in console.
- **`scripts/deploy.sh`**: repo→VPS sync (backend `main.py` + frontend `frontend/`) with `py_compile` pre-check, timestamped backups both sides, optional `--restart` flag for the backend service (off by default). Replaces the ad-hoc manual SSH+cp+backup sequence used throughout this session's prior work.

### Deferred (explicit owner decision)
- **Rate limiting on upload/checkin endpoints** — only `/api/ai-chat` has a rate limit today (20/hr). Checkin-photo AI-analysis endpoints and general uploads have none. Owner's call: all current users are trusted (own workers), not urgent — skipped for now, revisit if abuse/cost-spam ever becomes a real incident.

## 2026-07-24 (evening — autonomous session)

### Fixed
- **Chat embed stranded** (`frontend/app.html` `switchView()`): navigating away from Object Detail via bottom nav while Chat tab was active left `#chat-thread-detail-view` embedded inside `#obj-detail-panel-chat` instead of `#view-chat`, breaking regular chat until back-button was pressed. Fix: call `unembedObjectChat()` unconditionally at the top of `switchView()` (no-op when not embedded).
- **Checkin inaccessible from Stages tab** (`frontend/js/object-info.js`): the old `openStagesView()` showed a checkin-bar; the new 6-tab object detail screen's Stages tab only showed the roadmap. Fix: `_appendCheckinShortcut()` added at bottom of Stages panel for workers — calls `_openCheckinStatusScreen()` modal (same flow as FAB, no DOM duplication). Owners see no shortcut.

### Not yet deployed
Frontend changes committed+pushed but not copied to `/var/www/miniapp/` (requires root). See SESSION_HANDOFF.md.

## 2026-07-24 (fix/security-reliability-p1)

### Fixed
- **Deadlock (P0)**: removed redundant outer `with _lock_for(FILE):` wrapper at 15 call sites (roles, profile, object-assignments, chat-thread-meta, critical-alerts, abwesenheit) — `_atomic_write_json` already locks internally; the outer lock caused a guaranteed self-deadlock on nested acquire (non-reentrant `threading.Lock`), hanging every future request touching the same file. Same bug class as the 2026-07-17 `create_task`/`update_task_status` fix, not swept to these files at the time.
- **Authorization gaps**: `checkin_finish` (any worker could finish any other user's shift), checkin AI-analysis endpoints (no ownership check + unused rate limit not wired), `update_mangel_status` (missing owner gate, inconsistent with sibling status endpoints), `post_chat_attachment` (skipped `_check_thread_access` for thread-scoped uploads).
- **Upload validation**: `resolve_critical_alert` had no content-type/size check — now matches the 8MB + image/* pattern used elsewhere.
- **Live 500 bug**: `checkin_manual` referenced `idempotency_key` without declaring it as a parameter — every call failed (confirmed via audit.log: zero successful entries ever).
- **Robustness**: `validate_init_data` malformed `auth_date` now returns a clean 401 instead of an uncaught 500.
- **PII in logs (P1)**: `audit_log_middleware` no longer stores the full request body — was logging chat text, notes, and profile fields in plaintext.
- **UX**: Потребности split into its own view (`view-tasks`), separate from Дефекты — was a sub-tab sharing `view-mangel` via a `window._pendingMangelTab` side-channel.

## 2026-07-23 (recovery)

- **chore**: preserve recovered project state before documentation rebuild (backend code snapshot).
- **chore**: merge frontend git history (14 commits) as `frontend/` subtree.

---

Prior history (before this recovery) is not itemized here — it lived only in `.bak-pre-*` filenames on the VPS and in the frontend repo's own 14-commit log (visible via `git log -- frontend/`), not in a changelog. Going forward, every functional change should get an entry here per the rules in `CLAUDE.md`.
