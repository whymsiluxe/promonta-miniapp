# Deployment

There is exactly one environment: **production**, on a single VPS. No staging, no local dev parity (see [TODO.md](TODO.md) P0 for the plan to fix this).

## Infrastructure

- **Host**: Hetzner Cloud, CX23 Cost-Optimized x86, Ubuntu, Nürnberg. IPv4 `162.55.53.147`.
- **Access**: SSH key `~/.ssh/promonta_hetzner` (Mac-side), user `root`. Full access registry: `~/Projects/promonta/configs/ACCESS.md` (Mac, not in this repo).
- **Reverse proxy / TLS**: Caddy, automatic Let's Encrypt, domain `app.promonta.fun`.
  - `/api/*` → `reverse_proxy 127.0.0.1:8001` (FastAPI backend)
  - `/app.html`, `/js/*` → static files from `/var/www/miniapp/`, `Cache-Control: no-store, no-cache, must-revalidate` (no cache-busting by filename hash, so this header is load-bearing — removing it would serve stale JS to users)
- **Backend process**: systemd unit `promonta-miniapp.service`, `uvicorn miniapp.main:app --host 127.0.0.1 --port 8001`, `WorkingDirectory=/home/promonta/agent`, `EnvironmentFile=/etc/claude-agent.env`, `Restart=always`.
- **Cleanup**: `promonta-miniapp-cleanup.service` — removes old chat/critical-alert/checkin attachments (`cleanup_old_attachments.py`), timer-driven.

## Two directories, one app — important

- **Backend source + runtime data**: `/home/promonta/agent/miniapp/` (owned by user `promonta`). Contains `main.py`, JSON data stores, `.venv`, uploaded media.
- **Frontend, served to browsers**: `/var/www/miniapp/` (owned by `root`). Contains `app.html`, `js/*.js`, and independently had its own git history before this recovery (now merged into `frontend/` in this repo — see [DECISIONS.md](DECISIONS.md)).

These are **not** the same directory and edits to one do not affect the other. A `frontend_staging_work/` directory exists under the backend path but was last touched 2026-07-14 and is stale — do not assume it reflects current frontend state.

## How a frontend change reaches production

Historically: edit `/var/www/miniapp/app.html` (or a `js/*.js` file) directly on the VPS via SSH, after copying it to a timestamped `.bak-pre-<description>-<timestamp>` backup in the same directory. No deploy script currently does this reliably — `deploy_frontend.py` is referenced in older internal notes but was not found on disk during the 2026-07-15 session; treat it as **NOT_IMPLEMENTED** until verified otherwise. This repo's `frontend/` subtree, cloned from `/var/www/miniapp`'s own git history, is the first real version control this workflow has had.

**Going forward** (see [CLAUDE.md](../CLAUDE.md) governance): edit in this repo, commit, then sync the changed file(s) to `/var/www/miniapp/` via `scp`/`rsync` and this repo's git history becomes the actual audit trail, replacing the `.bak-pre-*` convention. The `.bak-pre-*` files should still be made before any production overwrite, as a last-resort rollback if the deploy itself breaks something before you can `git revert`.

## How a backend change reaches production

Edit `/home/promonta/agent/miniapp/main.py` (or the helper `.js` PDF-generator files) directly, backup first (`main.py.bak-pre-<description>-<timestamp>` convention already in use — many examples exist on disk), then:

```bash
systemctl restart promonta-miniapp
systemctl status promonta-miniapp   # confirm it came back up
curl -s http://127.0.0.1:8001/api/health   # or via the public domain
```

Same as frontend: this repo should become the real source, synced to the VPS path rather than edited there directly, going forward.

## Rollback

No automated rollback. Manual: restore the relevant `.bak-pre-*` file (VPS-side, plentiful history exists for `app.html`, `home.js`, etc.) or `git checkout <previous-commit> -- <file>` in this repo followed by re-sync to the VPS. For backend, `systemctl restart` after restoring `main.py` from backup.

## Backup / restore

See [DATABASE.md](DATABASE.md) — daily full-directory tarball via `backup.sh`, 14-day retention, pulled to Mac/iCloud separately. This is a data backup, not a deployment/release mechanism.

## What this repo does NOT do (yet)

- No CI/CD.
- No automated deploy from git push.
- No staging environment to test against before hitting production.
- No health-check-gated rollout.

These are real gaps, not oversights to silently work around — see [TODO.md](TODO.md) P0/P1 for the plan.
