# Testing

## Current state (updated 2026-07-31)

Automated backend test suite exists and is actively maintained: **151 tests**
across `tests/*.py`, plain stdlib `unittest` (no test framework dependency —
runnable directly, or via `pytest` which discovers `unittest.TestCase`
classes fine). All tests are fully offline — no real Google Sheets access, no
real Telegram API calls, `BOT_TOKEN` can be any string (only used for HMAC
signature math in the tests that exercise `validate_init_data`).

Test files, one per feature area (grows as new areas get covered — check
`tests/` directly for the current full list, this is a snapshot):

- `test_chat_backend.py` — chat thread pairing, self-DM rejection, reactions, prefs.
- `test_json_transaction.py` — `update_json_transaction` RMW-safety.
- `test_owner_kt_requirements.py` — object access scope, checkin geo requirements, transcribe route existence, chat attachment thread_key.
- `test_roadmap.py` — roadmap/stage checklist data model, progress calc, permissions.
- `test_tools.py` — Инструменты checkout/return flow, holder-name resolution, repo-tracked `tools_lib.py` import path.
- `test_upload_security.py` — magic-byte allowlist for chat attachments/voice/transcribe, path-traversal safety.
- `test_atomic_storage.py` — atomic JSON write, corrupt-JSON recovery, repo-tracked `mangel_lib.py` import path.
- `test_chat_unread.py` — unread counters across group/DM/object/mangel/task threads.
- `test_health.py` — `/api/health` and `/api/health/ready` fields, secrets-safety, readiness checks.

### Run the full suite

```bash
cd miniapp-repo
env $(cat /etc/claude-agent.env | grep -v '^#' | xargs -d'\n') /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/ -q
```

(needs the service's own venv — has `fastapi`/`pydantic`/`python-magic`
installed; bare system `python3` will fail on those imports. The
`/etc/claude-agent.env` sourcing only matters on the live VPS for `BOT_TOKEN`;
locally/in CI any `BOT_TOKEN` value works.)

To run a single file:

```bash
python3 -m unittest tests.test_tools -v
```

### CI

`.github/workflows/ci.yml` runs the same suite (plus syntax checks, required-
file presence, merge-conflict-marker scan, obvious-secrets scan) on every
push/PR — fully offline, `BOT_TOKEN` set to a dummy value in the workflow env.
*(Note: as of this writing the workflow file exists in the repo but the push
that would land it on GitHub was rejected — the deploying token lacked the
`workflow` OAuth scope. Confirm it's actually live on GitHub before relying on
it; push manually with a properly-scoped token if not.)*

### Frontend

`node --check` on every `frontend/js/*.js` file catches syntax errors — not a
real test suite (no assertions, no JS test runner configured). There is
still no automated visual/UI testing: `tests/smoke-nav-fab.js` (Playwright)
was written in an earlier phase but has never actually been executed in this
environment (missing system Chromium deps, no root to install them at the
time). Do not claim it "passed" without actually running it.

Do not claim any check "passed" if it wasn't actually run. If asked to verify
a change and no automated test exists for that area, say so explicitly and
fall back to the manual checklist below.

## Manual verification checklist

Use this before and after any change that touches the corresponding area —
still not automated, still requires walking through it by hand in the actual
Telegram client (or the live URL for backend-only checks). Automated tests
cover backend logic; they do not replace looking at the real rendered UI.

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
11. View tools list, take a free tool (no manual name entry — auto-filled from Telegram identity), return your own tool.
12. Try to return a tool held by someone else — must be rejected.
13. Edit own profile (clothing sizes, if onboarding already complete).

### Owner flow

1. Open app as the `owner`-role Telegram account.
2. Owner dashboard (KPI bar, quick actions) loads, not worker dashboard.
3. View all workers on shift ("Команда" screen — Сводка and План tabs).
4. Assign a worker to an object/stage (bubble drag-and-drop UI).
5. Approve an absence request; reject one with a comment.
6. Change a defect ticket's status.
7. Manage a tool (assign to a worker via the worker picker, or set to free — clears holder/holderId/object).
8. Open an object, view/edit stages.
9. Trigger and resolve a critical alert.
10. Open chat inbox, verify unread counts match across the nav badge and per-thread badges.

### Technical / cross-cutting

- Narrow mobile viewport (this is a Telegram Mini App — desktop browser testing is not representative).
- Actual Telegram WebView, not just a bare browser tab (initData won't populate outside Telegram).
- Keyboard-open state doesn't cover input fields.
- Safe-area insets respected (notch/home-indicator devices, bottom nav doesn't overlap content).
- Slow network / interrupted photo upload — does it fail cleanly or hang the check-in session (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md))?
- Long worker/object names don't break card layout.
- Empty states (no objects, no tasks, no chat threads) render sensibly, not blank/broken.
- Double-tap on a submit button doesn't create a duplicate record.

## Backend smoke test

```bash
curl -s https://app.promonta.fun/api/health
```

Should return `{"status": "ok", "service": "promonta-miniapp", "version": ..., "commit": ..., "time": ...}`. This is the fastest single check that the backend process is alive and reachable through Caddy. `/api/health/ready` requires owner Telegram auth (can't be curl'd directly without a signed initData header) — check it from inside the app instead, or see `scripts/deploy.sh` for the automated post-deploy check.

## What "done" requires

For any functional backend change: add or update a test in `tests/` covering
the actual behavior change, run the full suite, confirm 0 failures. For any
frontend change: `node --check` at minimum, plus walk the relevant manual
checklist item(s) above in the live app. Say plainly in the session/commit
what was and wasn't actually verified — do not mark something "tested" or
"working" without having actually run the check.
