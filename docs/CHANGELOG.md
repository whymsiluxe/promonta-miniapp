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

## 2026-07-23 (recovery)

- **chore**: preserve recovered project state before documentation rebuild (backend code snapshot).
- **chore**: merge frontend git history (14 commits) as `frontend/` subtree.

---

Prior history (before this recovery) is not itemized here — it lived only in `.bak-pre-*` filenames on the VPS and in the frontend repo's own 14-commit log (visible via `git log -- frontend/`), not in a changelog. Going forward, every functional change should get an entry here per the rules in `CLAUDE.md`.
