# Troubleshooting

## Objects screen won't load ("объекты не подгружаются")

**Root cause seen 2026-07-23**: `/api/objects` reads from a Google Sheet via `objekte_lib.py`'s OAuth flow (`.gdrive_creds.json` + `.gdrive_token.json` on the VPS, outside this repo). The refresh token can be revoked/expire independently of anything in this codebase — this is an **infrastructure/credentials issue, not a frontend or backend code bug**, even though the symptom looks like a UI problem.

Diagnose:
```bash
ssh -i ~/.ssh/promonta_hetzner root@162.55.53.147 "journalctl -u promonta-miniapp -n 50 --no-pager | grep -A5 'objekte_lib\|invalid_grant'"
```
If you see `urllib.error.HTTPError: HTTP Error 400` around `_token()` / `get_used_range` in `objekte_lib.py`, and the response body says `"error": "invalid_grant", "error_description": "Token has been expired or revoked."` — the Google OAuth refresh token is dead and needs re-authorization (not related to the app being in "Testing" vs "Production" publish status on Google Cloud Console — a token already issued stays dead regardless of publish status; publish status only affects the lifetime of *future* tokens).

Fix (manual, one-time browser step — cannot be done headlessly):
1. Get `client_id` from `/home/promonta/agent/.gdrive_creds.json` (`web.client_id`) and confirm `redirect_uris` (was `http://localhost` as of 2026-07-23 — an installed-app-style flow, not a real web redirect).
2. Build the authorization URL: `https://accounts.google.com/o/oauth2/v2/auth?client_id=<ID>&redirect_uri=http://localhost&response_type=code&scope=https://www.googleapis.com/auth/drive.file&access_type=offline&prompt=consent` (scope must match what's in the existing `.gdrive_token.json`'s `scope` field — was `drive.file` as of 2026-07-23).
3. Owner opens that URL in a browser, signs in with the Google account that owns the Objekte spreadsheet, approves — browser will try to load `http://localhost/?code=...&scope=...` and fail to connect (expected, nothing listens there) — the `code=` value is in the address bar.
4. Exchange the code for a new token server-side (do NOT put client_secret in any client-visible place): POST to `https://oauth2.googleapis.com/token` with `client_id`, `client_secret` (from the same creds file), `code`, `redirect_uri=http://localhost`, `grant_type=authorization_code`.
5. Backup the old `.gdrive_token.json`, write the new token response in its place, `systemctl restart promonta-miniapp`.
6. Verify: refresh-token-flow test (POST to the token endpoint with `grant_type=refresh_token` using the new refresh_token) should return 200, and `journalctl` after a fresh `/api/objects` call should show no `invalid_grant`.

This same credentials file/token is likely shared by other Promonta agent scripts beyond the miniapp (per `server-structure.md`, Google Sheets is used project-wide) — a dead token here may also be breaking other automations, worth checking if this recurs.

## App won't open / white screen in Telegram

1. Check the backend is up: `ssh` to VPS, `systemctl status promonta-miniapp`. If dead, `journalctl -u promonta-miniapp -n 100` for the crash reason — most common cause is `BOT_TOKEN` (or another required env var) missing from `/etc/claude-agent.env` after an edit.
2. Check Caddy is serving: `curl -I https://app.promonta.fun/app.html` from anywhere — should be 200. If not, `systemctl status caddy` on the VPS.
3. Check browser/Telegram console for JS errors — a syntax error in any `js/*.js` file loaded by `app.html` can blank the whole app since there's no bundler-level error isolation.

## `initData invalid` / Telegram auth failing

- Confirm `BOT_TOKEN` in `/etc/claude-agent.env` matches the actual bot's token from @BotFather (a token rotation on the Telegram side without updating the VPS env file is the most likely cause).
- Confirm the Mini App is actually being opened *through* Telegram (via the bot's menu button / inline button), not as a bare browser tab — `initData` is only populated by the Telegram client.

## API returns 403 for a user who should have access

- Check `roles.json` on the VPS — is their Telegram user ID present with the expected role? Unknown IDs default to `worker`, so an owner whose ID isn't listed will silently be treated as a worker, not blocked outright — check the specific endpoint's role requirement in [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md).

## Backend service won't start after an edit

1. `systemctl status promonta-miniapp` then `journalctl -u promonta-miniapp -n 50` for the traceback.
2. Most common causes: Python syntax error in `main.py`, a required env var missing, or a JSON data file corrupted (shouldn't happen given the atomic-write pattern, but if it does: the file's temp-write sibling or a recent VPS backup tarball is the recovery path — see [DATABASE.md](DATABASE.md)).
3. Rollback: restore the most recent `main.py.bak-pre-*` file from `/home/promonta/agent/miniapp/`, or `git checkout` the last known-good commit from this repo's `backend/main.py` and re-sync.

## Frontend change not showing up after deploy

Caddy serves `/app.html` and `/js/*` with `Cache-Control: no-store, no-cache, must-revalidate` specifically so this shouldn't be a server-side caching issue — check the Telegram client's own WebView cache (close and reopen the Mini App, or clear Telegram's cache) before assuming the deploy didn't take. Confirm the deployed file actually changed: `ssh` in and diff the live file against what you intended to ship.

## Photo/file upload fails or hangs

- Check available disk space on the VPS (`df -h /`) — media accumulates in `checkin_photos/`, `chat_attachments/`, `feed_photos/`, etc.; `promonta-miniapp-cleanup.service` prunes old attachments but only for the categories it's configured for (UNVERIFIED exact scope — check `cleanup_old_attachments.py`).
- Check the upload size against the known 8MB limit on chat attachments (other upload routes' limits are UNVERIFIED, see [SECURITY.md](SECURITY.md)).

## Shift check-in/check-out stuck

- Check `checkin_meta.json` on the VPS for the worker's session state — if a "finish" write failed partway (network drop mid-multipart-upload is the likely cause given photos are involved), the session may be stuck in "active" with no clean way to force-close from the UI. UNVERIFIED whether an owner-side override exists; if not, this is a real gap worth flagging to the owner rather than editing the JSON by hand under pressure.

## GitHub Actions / CI failed

Not applicable yet — no CI configured (see [TESTING.md](TESTING.md), [TODO.md](TODO.md)).

## When to escalate to the business owner directly

- Any suspected data exposure (see audit-log gap noted in [SECURITY.md](SECURITY.md) — GET requests aren't logged).
- Any incident touching worker GPS/photo data, given the GDPR exposure noted in SECURITY.md.
- Anything requiring a `BOT_TOKEN` rotation (breaks the running bot for all users until the env file and @BotFather are back in sync).
