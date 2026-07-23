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
