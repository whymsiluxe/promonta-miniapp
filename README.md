# Promonta Mini App

Telegram Mini App for Promonta, a construction company operating in Chemnitz/Sachsen, Germany. Used internally by the owner and field workers to manage construction sites, worker assignments, shift check-in/out, absence requests, defect tickets, tool/equipment tracking, team chat, and a news/photo feed — all inside Telegram.

Live at: **https://app.promonta.fun/app.html** (Telegram WebApp, opens inside Telegram client)

## Status

Actively developed, in production. No formal versioning yet (pre-1.0). See [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) for the current operational snapshot — that file is the first thing to read after any session loss.

## Roles

- **owner** — full access: manage objects, assign workers, approve absence requests, resolve critical alerts, see budgets/financials.
- **worker** — field access: see own assigned object, check in/out with GPS+photo, request absence, report defects/material needs, chat.

Role is looked up from `roles.json` by Telegram user ID; unknown IDs get a hard 403 (whitelist-only access since a "Фаза 10.1" hardening — not a silent worker default). See [docs/ROLES_AND_PERMISSIONS.md](docs/ROLES_AND_PERMISSIONS.md).

## Tech stack

- **Frontend**: vanilla HTML/CSS/JS, no build step, no framework, no bundler. Single-page shell (`app.html`) + per-feature JS modules loaded as plain `<script>` tags from `js/`. Telegram WebApp JS SDK for host integration (initData, haptics, theming, safe-area).
- **Backend**: Python 3.12, FastAPI (`main.py`, ~93 routes, single file). Auth via Telegram WebApp `initData` HMAC validation — no separate login system, no JWT, no session cookies.
- **Data storage**: flat JSON files on disk (no database, no ORM, no migrations). See [docs/DATABASE.md](docs/DATABASE.md) for the full list of stores and known race-condition mitigations (atomic write + per-file locks).
- **AI features**: Claude (via `CLAUDE_BIN` CLI bridge) and GLM as fallback, for chat assistant and voice-note transcript extraction (`faster-whisper` for STT).
- **PDF generation**: `pypdf`, for Angebot (quotes) and Rechnung (invoices).

Full breakdown: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```
miniapp-repo/
├── backend/          FastAPI app (main.py) + PDF-generation JS helpers, .env.example
│   └── docs-source/  historical handoff docs kept for context, not current state
├── frontend/          Telegram Mini App frontend, own git history (14 commits) merged as subtree
│   ├── app.html        app shell, routing, role-based bottom nav
│   ├── angebot-tab.html, projects-tab.html, tools-tab.html   legacy standalone tab pages (status: see FEATURES.md)
│   └── js/              one module per feature area
└── docs/              see below
```

Runtime data (JSON stores, uploaded photos, generated PDFs, `.venv`, `node_modules`) lives on the VPS outside this repo and is never committed — see `.gitignore`. It contains personal data of employees and must not leave the server without authorization.

## Local development

**There is no local dev environment set up yet.** Development has historically happened by editing files directly on the production VPS with manual timestamped backups (`*.bak-pre-<change>-<timestamp>`) before each risky edit, then restarting the systemd service. This is fragile and is the main reason a lost session could not be reconstructed — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/TODO.md](docs/TODO.md) for the plan to fix this.

To run the backend locally (untested, first person to try this should update this section):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# requires BOT_TOKEN and other vars from .env.example
uvicorn main:app --reload --port 8001
```

Frontend has no build step — open `frontend/app.html` directly, but it expects Telegram WebApp context (`window.Telegram.WebApp`) and will not fully function in a plain browser tab without stubbing that out.

## Checks

**None are currently configured.** No lint, no typecheck, no automated tests, no CI. See [docs/TESTING.md](docs/TESTING.md) for the manual test checklist to run before any deploy, and [docs/TODO.md](docs/TODO.md) for the plan to introduce at least basic checks.

## Git workflow

- `main` — stable, deployed state.
- `docs/...`, `fix/...`, `feat/...`, `chore/...` — work branches. See [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md).
- Every functional commit should touch `docs/CHANGELOG.md`, `docs/PROJECT_STATE.md`, `docs/SESSION_HANDOFF.md`, and `docs/FEATURES.md` if applicable — see governance rules in [CLAUDE.md](CLAUDE.md).
- No force-push, no history rewriting without explicit owner approval.

## Recovering from a lost session

1. Read [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) and [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) first.
2. Run `git log --oneline -20` and `git status` in this repo.
3. Compare against the live VPS state — the production frontend is served from `/var/www/miniapp/app.html` and backend from `/home/promonta/agent/miniapp/main.py`; this repo is a curated copy. If they've diverged, the VPS is the source of truth until re-synced (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
4. Check `docs/TODO.md` for the next planned step.

## Secrets warning

This repo must never contain `BOT_TOKEN`, `GLM_KEY`, `WEBHOOK_SECRET`, real employee personal data, or any file under `backend/*.json` (all runtime data, gitignored). See [docs/SECURITY.md](docs/SECURITY.md) and [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).
