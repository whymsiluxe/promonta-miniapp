# TODO

## P0 — blocking / foundational

- **REC-1**: Set up a real deploy path from this repo to the VPS (rsync/scp script or CI job), replacing direct SSH edits + `.bak-pre-*` convention. *Why*: direct-edit-on-prod is what caused the original session-loss/doc-drift problem. *Status*: TODO.
- **REC-2**: Decide what to do with the stale local Mac copy at `~/Projects/promonta/miniapp/frontend/` (dated Jul 8-12, now superseded by this repo). *Why*: risk of someone accidentally treating it as current. *Status*: TODO — needs owner/user decision, not unilateral deletion (destructive-action rule).
- **REC-3**: Full endpoint-by-endpoint permission audit (all 93 routes, not just the ones spot-checked in this recovery — GPS/chat/tools were checked, most others weren't). *Why*: `docs/ROLES_AND_PERMISSIONS.md` currently says most routes are unverified. *Status*: TODO.
- **REC-4**: Verify whether FastAPI's auto-generated `/docs` (Swagger UI) is reachable through Caddy in production. *Why*: if so, it exposes the full route/schema list publicly. *Status*: TODO, quick check (`curl https://app.promonta.fun/docs`).
- **REC-5**: Determine if `angebot-tab.html`, `projects-tab.html`, `tools-tab.html` are still linked from `app.html` or are dead code. *Why*: can't safely delete or maintain without knowing. *Status*: TODO.

## P1 — important

- **REC-6**: Introduce at least one automated check (even just a Python syntax check / `python -m py_compile main.py` in a pre-push hook) — there is currently zero automated verification of any kind.
- **REC-7**: Add `load_dotenv()` to `main.py` (or document that it's intentionally absent) so local development can use a `.env` file instead of manually exported shell vars.
- **REC-8**: Trace every FEATURES.md row currently marked UNVERIFIED to WORKING or its true status, one feature area at a time, per the checklist in TESTING.md.
- **REC-9**: Decide whether `POST /api/objects/{object_id}/tasks` should be assignment-scoped (see ROLES_AND_PERMISSIONS.md finding).
- **REC-10**: Confirm upload size limits are consistent across all upload routes (chat=8MB confirmed, others unverified).

## P2 — improvements

- Sanitized fixture/seed data for local development and any future automated tests (currently no safe way to run this app without touching production data).
- CODEOWNERS file (needs the owner's actual GitHub username — not guessed in this pass).
- Branch protection on `main` once the repo has collaborators beyond the owner.

## P3 — future ideas

- Staging environment (currently production-only).
- Consider whether the JSON-file data layer needs to become a real database — not urgent at current scale (see DATABASE.md), but worth revisiting if concurrency or reporting needs grow.

## Explicitly out of scope (owner decision, not a gap)

- Material/warehouse inventory (Materialverwaltung).
- Fahrtenbuch (vehicle logbook).

## UI/UX follow-ups carried from prior sessions (not yet independently re-verified)

- Chat/AI tab scroll bug — last known state: 3 approaches tried, landed on "variant B", **not confirmed working by the user**. Verify before touching this area again.
- 2026-07-22 late-session visual redesign (luxury splash, flat-square icons, warm palette) was mid-flight when the session that prompted this recovery was lost — give it a look before assuming it's in a finished state.
