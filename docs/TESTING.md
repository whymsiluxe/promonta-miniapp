# Testing

## Current state: NOT_IMPLEMENTED

No unit tests, no integration tests, no e2e tests, no test framework installed (not in `requirements.txt`, no `pytest`/etc.), no CI. All verification has historically been manual, directly against production, immediately after each change. This is the single largest quality-process gap in the project — see [TODO.md](TODO.md) P0.

Do not claim a check "passed" if it wasn't actually run. If asked to verify a change and no test suite exists, say so explicitly and fall back to the manual checklist below plus a direct `curl`/browser check.

## Manual verification checklist

Use this before and after any change that touches the corresponding area. None of this is automated — walk through it by hand in the actual Telegram client (or the live URL for backend-only checks).

### Worker flow

1. Open app as a `worker`-role Telegram account.
2. Home view loads with worker dashboard (not owner dashboard).
3. View own assigned object.
4. Start shift check-in (GPS + photo capture).
5. Pause / resume if that flow is in active use.
6. Finish shift (summary, extra work, next-day needs fields).
7. Submit a defect ticket (Mangel) with photo.
8. Submit a material need / task.
9. Send a chat message, including an attachment and a voice note.
10. Request absence (Abwesenheit), including a partial-day request.
11. View tools list.
12. Edit own profile (clothing sizes, if onboarding already complete).

### Owner flow

1. Open app as the `owner`-role Telegram account.
2. Owner dashboard (KPI bar, quick actions) loads, not worker dashboard.
3. View all workers on shift.
4. Assign a worker to an object/stage (bubble drag-and-drop UI).
5. Approve an absence request; reject one with a comment.
6. Change a defect ticket's status.
7. Issue and return a tool.
8. Open an object, view/edit stages.
9. Trigger and resolve a critical alert.
10. Open chat inbox, verify unread counts.

### Technical / cross-cutting

- Narrow mobile viewport (this is a Telegram Mini App — desktop browser testing is not representative).
- Actual Telegram WebView, not just a bare browser tab (initData won't populate outside Telegram).
- Keyboard-open state doesn't cover input fields (known historical bug class per `server-structure.md`/design-refs audits — verify still fixed).
- Safe-area insets respected (notch/home-indicator devices).
- Slow network / interrupted photo upload — does it fail cleanly or hang the check-in session (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md))?
- Long worker/object names don't break card layout (was previously fixed per frontend git log, `f8ec412`).
- Empty states (no objects, no tasks, no chat threads) render sensibly, not blank/broken.

## Backend smoke test

```bash
curl -s https://app.promonta.fun/api/health
```

Should return a healthy response. This is the fastest single check that the backend process is alive and reachable through Caddy.

## What "done" requires until real tests exist

For any functional change: walk the relevant checklist item(s) above in the live app (or against a synced-but-not-yet-live copy if a safe way to do that gets built — see TODO.md), and say plainly in the session/commit what was and wasn't manually verified. Do not mark a `FEATURES.md` row `WORKING` without having actually done this.
