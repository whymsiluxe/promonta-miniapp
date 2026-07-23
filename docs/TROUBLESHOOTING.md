# Troubleshooting

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
