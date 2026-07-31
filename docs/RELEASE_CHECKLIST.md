# Release checklist

Run through this before any production deploy of an accumulated batch of
changes (not necessarily every single commit — use judgement for small fixes,
always use this for a release-candidate-sized batch like the one that
produced this document).

## Automated (must be green before proceeding)

- [ ] Full test suite: `pytest tests/ -q` → 0 failed.
- [ ] Python syntax: `python3 -m py_compile backend/*.py` → no errors.
- [ ] JS syntax: `node --check` on every `frontend/js/*.js` → no errors.
- [ ] `git status --short` → clean working tree, everything committed.
- [ ] CI green on GitHub (once `.github/workflows/ci.yml` is actually pushed
      — see `docs/PROJECT_STATE.md` "Known blockers" if it isn't yet).
- [ ] No secrets in the diff (`BOT_TOKEN` value, private keys, refresh
      tokens, `.sheets.json`, `roles.json`) — CI checks this, but double-check
      manually if CI isn't confirmed live yet.

## Backup

- [ ] `scripts/deploy.sh` creates a fresh timestamped backup automatically —
      confirm the backup directory is non-empty after the script's own
      check passes (it exits non-zero if not, but verify with your own eyes).
- [ ] Confirm the existing `promonta-backup.timer` ran successfully within
      the last 24h (`systemctl status promonta-backup.service`) — this is
      the actual user-data backup, separate from the deploy-time backup.

## Deploy

- [ ] SHA to deploy is confirmed (`git rev-parse HEAD` on `main`, matches
      what was tested).
- [ ] `scripts/deploy.sh` run — watch for the first non-zero exit, it stops
      immediately on any failed step.
- [ ] `/api/health` returns 200 with the expected `commit` field matching
      the deployed SHA.
- [ ] `/api/health/ready` checked from inside the app as owner (can't curl
      it directly — needs signed Telegram initData) — all `checks` fields
      `ok`.
- [ ] `systemctl status promonta-miniapp.service` → active, no recent
      restart loop in `journalctl -u promonta-miniapp -n 50`.

## Manual live verification (Telegram, not curl/code review)

### Worker test

- [ ] Login/whitelist works for a real worker account.
- [ ] Assigned object visible, accept/decline an assignment.
- [ ] Start shift: GPS + photo required, actually blocks without them.
- [ ] Pause/resume shift.
- [ ] Finish shift: summary fields, ≥2 photos required.
- [ ] Chat: send text, send an image attachment, send a voice note — all
      three round-trip correctly (image displays, voice plays + transcribes).
- [ ] Report a defect (Mangel) with a photo.
- [ ] Submit a material need / task.
- [ ] Request absence (full day and partial day).
- [ ] Tools: take a free tool (no manual name field — confirm it's gone),
      confirm holder name auto-fills from Telegram identity.
- [ ] Tools: return own tool — confirm status flips to "Свободен", holder/
      object cleared.

### Owner test

- [ ] Dashboard loads with owner KPIs, not worker view.
- [ ] Команда screen: Сводка and План tabs both load, counts look sane.
- [ ] Assign a worker to an object/stage.
- [ ] Approve one absence request, reject another with a comment.
- [ ] Change a defect ticket's status.
- [ ] Tools: manage a tool — assign to a specific worker via the picker
      (not free text), confirm the resulting holder card is clickable
      (opens user card — confirms `holderId` was actually saved).
- [ ] Tools: set a tool back to "Свободен" — confirm holder/holderId/object
      all cleared together (not left half-set).
- [ ] Trigger and resolve a critical alert.
- [ ] Chat inbox: unread badges look correct across group/DM/object threads
      (this was a real bug fixed 2026-07-31 — worth extra attention here).

### Cross-worker access test (Worker A vs Worker B)

- [ ] Worker B cannot see Worker A's GPS/photos from A's check-in session.
- [ ] Worker B cannot pause/finish A's shift.
- [ ] Worker B cannot return a tool currently held by A.
- [ ] Worker B cannot open Owner-only screens/actions.
- [ ] Worker B sees only objects/chats they're actually supposed to (per
      the app's existing "any worker sees any object/defect" design — verify
      this matches actual owner expectations, it's an intentional broad-access
      decision documented in `docs/RELEASE_AUDIT.md`, not a bug to "fix").

## Post-deploy

- [ ] Recent backend logs reviewed for unexpected errors
      (`journalctl -u promonta-miniapp -n 100`).
- [ ] Disk space checked (`df -h /`) — no sudden jump.
- [ ] If anything above fails: `scripts/rollback.sh <backup-dir>` — the exact
      path is printed by `deploy.sh` at the end of its run.

## Sign-off

Deploy is only "done" once every checked box above is actually checked by
a real action, not assumed. If Telegram E2E wasn't performed, say so
explicitly — do not mark this checklist complete with unchecked manual items.
