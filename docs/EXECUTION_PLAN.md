# Promonta Miniapp — Recovery + Architecture + UX Round

## Context

**Live incident (RESOLVED during planning, root cause not yet fixed in code):** the owner's Telegram mini-app showed "Не удалось загрузить: авторизация" starting ~10:15 CEST today. Root cause traced and fixed manually:

`tests/test_worker_calendar_birthday.py`'s `BirthdayAlertTests.setUp()` calls `backend._save_roles({'1': 'owner', '100': 'worker'})` without first setting `MINIAPP_DATA_ROOT` (unlike sibling tests in the same repo, e.g. `test_daily_plan.py`, `test_round7_hardening.py`, which self-isolate via `os.environ['MINIAPP_DATA_ROOT'] = tmp` in code). The file's own docstring says it must be run as `MINIAPP_DATA_ROOT=$(mktemp -d) pytest ...` — an *external* env requirement, easy to forget. `DATA_ROOT` defaults to `/home/promonta/agent/miniapp` (the live prod data dir) when the var is unset. `docs/HANDOFF.md:328` instructs a resuming session to run `python3 -m pytest tests/ -q --tb=no` — with no `MINIAPP_DATA_ROOT` — as its very first step. The Production Control watchdog (installed yesterday, since removed) restarted the autonomous Claude process every 5 minutes for ~8.5 hours after the work was already done, and each restart re-read HANDOFF.md and likely re-ran the full suite, repeatedly overwriting prod's real `roles.json` (`{"872079437": "owner", "5298622655": "worker"}`) with the test fixture (`{"1": "owner", "100": "worker"}`). This locked the real owner and worker out with 403 ("Доступ не предоставлен").

Manual fix already applied: `roles.json` restored from the last known-good backup (`roles.json.bak-pre-add2091898960-20260728-095247`), owner confirmed the app loads again. The corrupted version is preserved at `roles.json.bak-corrupted-by-test-20260908`. **This plan must still fix the underlying test-isolation gap** so it cannot recur — that's Phase 0's real deliverable, not just the hotfix already done live.

**Broader request (owner, two-part brief):** (1) a real architecture/security/glove-UX audit of the whole miniapp — already run via 3 parallel Explore agents, findings below — and (2) a nav restructure: pull the Feed (currently a sub-tab buried inside Home) out into its own top-level tab, reorder nav to Feed/Dashboard/Chat/Objects/Profile with Chat centered, remove the Abwesenheit/Calendar tab from nav and fold a compact calendar widget into Dashboard instead (full calendar screen stays reachable via "Открыть календарь").

This is a large, multi-day scope. Owner wants it run as one continuous autonomous VPS session, phases executed sequentially without stopping for approval, EXCEPT the final deploy — no auto-deploy, stop after full verification and report for owner review.

**EXECUTION SAFETY OVERRIDE — do not reuse the previous endless watchdog pattern.** Yesterday's `systemd-run` + 5-minute-interval watchdog is what turned one unsafe test into 8.5 hours of repeated production-data corruption — it is explicitly rejected, not reused "same pattern as before." Use one controlled autonomous `systemd-run` session. If crash recovery is required: maximum 3 automatic restarts; restart only while `execution_state == RUNNING`; `COMPLETE`/`STOPPED_FOR_REVIEW`/`FAILED` permanently disables restart; resumed sessions must continue from HANDOFF.md/current git HEAD, never rerun completed phases; every pytest command must run with an isolated test `DATA_ROOT`; no production deployment from the autonomous session. Full mechanics in the "Execution mode" section at the end of this plan — this paragraph exists so the safety constraint is visible up front, not just at the bottom.

**Owner's explicit architectural decisions (override any ambiguity in the audit findings):**
- Vanilla JS stays. No React/Vue migration. The real problem is app.html's size and global-state sprawl, not the framework choice — fix via incremental extraction, not rewrite.
- Nav order: **Лента, Dashboard, Chat, Объекты, Профиль** (Chat is the center/3rd tab, both roles).
- Opening the app does NOT default to Feed just because it's leftmost — Owner still lands on Dashboard; Worker still lands on Today/DailyPlan if one exists (unchanged default-view logic, only the tab strip changes).
- Dashboard calendar is a **compact widget** (current week/month strip + upcoming events + "Открыть календарь" button), not the full month-grid — the full calendar remains the existing abwesenheit.js screen, reachable by tap. No second calendar backend or second data source — Dashboard's widget and the full screen render from the same data.
- Feed sub-tab order: **Фото, Новости, Инфо** (photos default-active) — note this order differs from the current in-Home sub-tab order (News, Photos, Weather); must physically reorder, not just relabel.

---

## Phase 0 — Fix the incident's root cause (test isolation), verify prod data path end-to-end

**0.1 — Fix `test_worker_calendar_birthday.py`:** add `os.environ['MINIAPP_DATA_ROOT'] = tempfile.mkdtemp()` at the top of `BirthdayAlertTests.setUp()` (and any other class in that file lacking it), matching the self-isolating pattern already used in `test_daily_plan.py:22` / `test_round7_hardening.py:25`. Remove reliance on the docstring's "run with external env var" instruction — the test must be safe to run bare.

**0.2 — Audit every test file for the same gap.** `grep -rn "_save_roles\|_atomic_write_json.*ROLES_FILE\|_save_.*_file\|ROLES_FILE," tests/*.py` and cross-check each hit sets `MINIAPP_DATA_ROOT` (via env or subprocess env) *before* importing/calling `backend`. Any file relying only on a docstring comment is a live footgun — fix in place.

**0.3 — Add a `conftest.py` safety net — set env at IMPORT TIME, not inside a fixture.** Pytest fixtures run *after* a test module is imported, so a fixture is too late to protect a module that imports `backend` at module scope (which many test files here do — `import main as backend` at the top of the file). `tests/conftest.py` must set the environment as plain module-level code, executed the instant conftest is collected, before any test module import:

```python
import os
import tempfile

_TEST_DATA_ROOT = tempfile.mkdtemp(prefix="promonta-pytest-")
os.environ["MINIAPP_DATA_ROOT"] = _TEST_DATA_ROOT
os.environ["PROMONTA_ENV"] = "test"
```

This must be top-level code in the file, not inside any `def` or fixture. Only *after* this, add an autouse fixture as a defense-in-depth assertion layer (not the mechanism itself):

```python
import pytest

@pytest.fixture(autouse=True, scope="session")
def _verify_test_isolation():
    import main as backend
    assert backend.DATA_ROOT != "/home/promonta/agent/miniapp", \
        f"DATA_ROOT resolved to production path: {backend.DATA_ROOT}"
    assert "promonta-pytest-" in backend.DATA_ROOT, \
        f"DATA_ROOT does not look like a pytest temp dir: {backend.DATA_ROOT}"
```

**Explicit regression test required**: prove that running `unset MINIAPP_DATA_ROOT && python3 -m pytest tests/test_worker_calendar_birthday.py -q` (i.e. exactly the command that caused today's incident, with no env var set beforehand) still resolves to a temp `DATA_ROOT`, never to `/home/promonta/agent/miniapp`. Add this as a standing test (e.g. `tests/test_data_root_isolation.py`) that fails loudly if conftest's import-time guard is ever removed or bypassed — this is P0, not optional cleanup.

**0.4 — Fix `docs/HANDOFF.md`'s resume instructions** (line 328 and anywhere else `pytest tests/` is written bare) to always show `MINIAPP_DATA_ROOT=$(mktemp -d) python3 -m pytest tests/ -q --tb=no`, matching what the per-file docstrings already say — the instruction that got followed was the one missing the safeguard.

**0.5 — Verify current prod data path is sane end-to-end**, using a real Telegram initData request (not a bare curl), per the owner's brief 0.4/0.5/0.6:
- `/api/session`, `/api/me`, `/api/objects`, `/api/feed/photos`, `/api/feed/news`, `/api/feed/weather`, `/api/chat/unread_count`, `/api/abwesenheit/all`, `/api/critical-alerts/pending` all return real data, not empty/error.
- Confirm Google Sheets read path (Объекты, Этапы tabs) returns actual rows — read-only, no writes.
- Confirm `roles.json` now matches `ALLOWED_CHAT` identities and stays stable across a service restart (no test run in between).

**0.6 — Frontend bootstrap hardening** (owner's brief section 0.6, concrete code-level asks — verify then fix what's real):
- `_homeLoaded = true` set before successful load (home.js) → must only flip true on confirmed success; failed initial load must retry on next visit.
- Silent-catch data functions in home.js → must surface a visible per-card error+Retry state, not blank.
- `prefetchTracked`'s cached-promise semantics (a rejected original promise must not poison a later retry — `.catch(() => null)` returned to splash while the poisoned original stays cached) → fix so a failed prefetch is evictable/retryable, not permanently cached as failure.
- `loadedViews`-style one-shot booleans anywhere else in the frontend → same fix pattern (init-once, refresh-many lifecycle, not init-once-ever).

**0.7 — Global frontend error boundary**: add `window.onerror`/`unhandledrejection` handlers that record build SHA + view + error type + safe stack summary (no tokens/PII), and show "Не удалось загрузить данные [Повторить]" instead of a silent blank screen — without replacing the whole UI for one failed noncritical module.

**0.8 — Deploy script fix (`deploy_frontend.py`)**: replace the regex-based HTML tag-balance checker (confirmed yesterday to false-positive on `<header>` mentioned inside CSS comments) with Python's real `html.parser.HTMLParser`, as already verified ad hoc during yesterday's manual deploy. Also add: SHA verification after copy, a basic health/smoke check (hit `/api/health` post-restart) before declaring success, and a clear pass/fail report — matching the owner's "validate → backup → copy → verify SHA → health/smoke → restart if needed → report" sequence.

**0.9 — Build-version cache-busting**: add a deterministic build marker (git SHA) injected at deploy time, append `?v=<SHA>` to JS/CSS `<script src>`/`<link href>` references in `app.html`, expose `window.__APP_BUILD_SHA__`, and set `app.html` itself to no-cache/revalidate at the Caddy/nginx level while JS/CSS may cache by the versioned URL. Replaces the stale hardcoded `<!-- build: 20260713-154810 -->` comment as the *only* build identity — keep the comment updated too (human-readable) but make the querystring the enforced mechanism.

**0.10 — Test/production data firewall (fail-closed, not just this one test fixed).** Today's incident was not "a careless test" — it was an architecture gap: nothing physically prevented a test process from writing to the production data directory. Fixing `test_worker_calendar_birthday.py` and adding a conftest guard (0.1-0.3) closes today's specific hole, but a *future* forgotten `MINIAPP_DATA_ROOT` in some other test must not be able to repeat this. Implement a central, environment-identity-based guard in the backend's storage bootstrap itself (not per-test):

- Add `PROMONTA_ENV` support to `main.py`'s `DATA_ROOT`/config resolution (near line 34), but **do NOT modify or restart the production systemd service (`/etc/systemd/system/promonta-miniapp.service`) in this round** — this plan is explicitly no-deploy, and touching the live service's environment is itself a production change that belongs in the approved deploy step, not during development/verification. The app must remain fully backward-compatible when `PROMONTA_ENV` is unset (i.e. today's actual production, which sets nothing, keeps working exactly as now).
- Pytest's conftest sets `PROMONTA_ENV=test` (part of the same import-time block in 0.3) — this is the only place `PROMONTA_ENV` actually gets set in this round.
- In `main.py`'s `DATA_ROOT` resolution: if `PROMONTA_ENV=test` (or more generally, if the running process is pytest — detectable via `PROMONTA_ENV` and/or `"pytest" in sys.modules`) and the resolved `DATA_ROOT` equals `/home/promonta/agent/miniapp`, raise `RuntimeError("REFUSING TO RUN TESTS AGAINST PRODUCTION DATA ROOT")` immediately at import time, before any file I/O. **This safety property must hold now, in this round, without needing the production service changed** — the guard triggers on the test side (`PROMONTA_ENV=test` + prod path), not on requiring the prod side to declare itself.
- This guard belongs in one central place (the module that defines `DATA_ROOT` and the JSON-store path constants), not duplicated per-test.
- Add a test proving the guard itself works: simulate `PROMONTA_ENV=test` + `DATA_ROOT=/home/promonta/agent/miniapp` and assert the `RuntimeError` fires.
- This must hold even if a developer/agent forgets to isolate one specific future test — `roles.json`, `worker_profiles.json`, `checkin_meta.json`, `tasks.json`, `daily_plan_store.json`, chat stores, mängel stores, alerts, contract state — none of them must be reachable by a test process pointed at the prod path, regardless of which specific test forgot isolation.
- In the final report, provide the exact production systemd unit change needed to complete the firewall (`Environment=PROMONTA_ENV=production` added to `promonta-miniapp.service`) as a **documented step for the approved deployment**, not something applied now.

**Stop condition for Phase 0** (owner's exact bar — do not proceed to Phase 1 until all true): backend returns real data via authenticated request; frontend bootstrap consumes it; Objects/Dashboard render; no fatal console/startup JS error; failed requests show visible Retry; static frontend build is coherent (no mixed old-JS/new-HTML state); the test/production firewall (0.10) is in place and its own regression test passes. Commit: `fix: restore miniapp data loading and bootstrap reliability`.

---

## Phase 1 — Security fixes (from completed audit, concrete findings — fix don't re-audit)

**CRITICAL CORRECTION on item #1 below — this is schema drift, not a confirmed leak.** The audit agent read `main.py`'s `BUDGET_FIELDS` and `objekte_lib.py`'s column access and found they use different key strings, then assumed `objekte_lib.py`'s `'% бюджета'` is "the real column" and `main.py`'s `'потрачено в % от бюджета'` is "wrong." That assumption was never verified against the actual live Google Sheet header — it could just as easily be the other way around, or both could be stale aliases of a header that changed at some point. **Do not blindly replace one key with the other.** Before touching any code:

1. Read the actual current header row of the "Объекты" tab in the live Google Sheet (read-only, no writes) and confirm which string is the real column name today.
2. Given `main.py`'s `/api/alerts` also reads `'потрачено в % от бюджета'` with a fallback to `'Потрачено %'` (a *third* variant), and `objekte_lib.py` expects `'% бюджета'`, treat this as **schema drift across three call sites**, not a single typo.
3. Build one canonical accessor, e.g. `get_budget_percent(obj)`, that recognizes all known historical aliases (`'% бюджета'`, `'потрачено в % от бюджета'`, `'Потрачено %'`) and returns the value regardless of which one the Sheet currently uses. Use this helper everywhere budget-percent is read: worker-DTO field stripping, budget calculations, owner alerts, object DTO normalization, threshold checks — one source of truth instead of four call sites each guessing a key name.
4. Worker-facing DTO stripping must remove **all** recognized aliases unconditionally (`Бюджет (EUR)`, `Потрачено (EUR)`, and every alias `get_budget_percent` recognizes) — this is the actual privacy-safety fix, independent of which alias turns out to be "correct."
5. Add tests covering every historical alias as input to the DTO-stripping path and to `get_budget_percent`.
6. **Do not claim in the final report that there is a confirmed live Worker data leak, or that owner alerts are confirmed broken, until this is verified against the actual current Sheet header** — report it as "schema drift found and fixed with a canonical accessor + tests" unless the live-header check independently proves the leak/alert-break claim.

| # | Finding | Fix | File | Severity |
|---|---|---|---|---|
| 1 | Budget-percent field name schema drift across `main.py`'s `BUDGET_FIELDS`, `main.py`'s `/api/alerts` fallback chain, and `objekte_lib.py`'s threshold check — three different key strings for what should be one field, unverified against the live Sheet header (see correction above) | Read live Sheet header first; build `get_budget_percent(obj)` canonical accessor recognizing all aliases; use it at every read site; strip all budget fields (EUR amounts + all percent aliases) from worker DTOs unconditionally; add alias-coverage tests | `main.py:1763`, `main.py:2679`, `objekte_lib.py:342,354` | High (pending live-header verification) |
| 2 | `GET /api/chat/attachments/{fname}` crashes with an unhandled 500 (`AttributeError` on `.get('file')` when `attachment` key is explicitly `None`, which every plain-text chat message has) — blocks legitimate photo/voice attachment fetches for any worker once any text message exists in active/archived chat (true in prod today) | `m.get('attachment') or {}` instead of `m.get('attachment', {})` | `main.py:4826-4827` | Medium |
| 3 | `TASKS_FILE` (Потребности/needs) read-modify-write has zero lock protection — every other JSON store in the app (chat, mängel, roles, checkin) was already fixed for this exact race; concurrent create/update can silently lose a task or revert an owner's status-close | Wrap `create_task`/`update_task_status` in `update_json_transaction`, matching the pattern used everywhere else | `main.py:6068-6151` | Medium |
| 4 | `require_angebot_access` permits a `'manager'` role that can never actually be assigned (`set_role` hard-rejects anything but owner/worker) — dead code today, but a live escalation path if `set_role`'s validation is ever loosened without re-auditing this check | Remove the `'manager'` branch, or add a comment+test pinning that only `owner` may pass | `main.py:3009-3011` | Low |
| 5 | Stale hardcoded dates in `tests/test_needs_access_control.py` (`2026-08-01`..`2026-08-31`) make 2 tests fail against today's date — not a real access-control gap (the protection they test works correctly), but a false-negative risk: a future real regression in `has_active_object_access` wouldn't be caught | Relativize the fixture dates (`date.today() ± timedelta(...)`) instead of hardcoding | `tests/test_needs_access_control.py:24` | Low (test hygiene) |

Do NOT touch: auth/HMAC mechanism, session tokens, route auth coverage, file-upload validation, secrets handling — all confirmed solid in the audit, no changes needed there.

Commit: `security: fix budget-field leak, chat-attachment crash, tasks-file race`.

---

## Phase 2 — Production Control foundation re-verification

Owner's brief lists 16 items claimed done in the prior Production Control round (Rounds 1-7, HANDOFF.md). Given yesterday's incident *originated* from that round's test-running process corrupting prod data, treat HANDOFF.md's claims as unverified until re-checked against actual code — not because the work is assumed wrong, but because the process that produced it just proved capable of silent data corruption.

Spot-check each of the 16 items against the actual code path (not the HANDOFF.md prose), fix only what's genuinely missing:
1. Multi-worker DailyPlan independent acceptance
2. One worker's finish doesn't complete all workers'
3. Per-worker amendment acknowledgment
4. Server-side Check-in ↔ DailyPlan validation (not trusted client state)
5. Accepted plan survives app reload before Start
6. Durable Finish projector/outbox
7. Real Google Sheets Plan_дня sync (not a stub)
8. Inter-process locking for DailyPlan store
9. Corrupt-store quarantine
10. Owner matrix correct schema keys
11. Contract RED risk computed from actual contract dates
12. Pause-subtracted productivity calculation
13. Team productivity not misrecorded as exact solo KPI
14. Multiple stage items in one day supported
15. Assigned-worker-without-DailyPlan Start flow exists
16. Blocker idempotency

Google Sheets tabs (План_этапов, План_дня, Нормы_работ, Факт_дня, Производительность) — confirm they exist in the same spreadsheet without having overwritten Объекты/Этапы/Расходы; confirm manual Sheet edits propagate to the app (not just app→Sheets one-way).

Commit: `fix: harden production control foundations` (only if gaps found — otherwise fold verification notes into HANDOFF.md and skip an empty commit).

---

## Phase 3 — Navigation restructure

**3.1 — Extract Feed into `#view-feed`.** Currently `app.html:4915-4949` embeds Feed's 3 sub-tabs (`#feed-news-content`, `#feed-photos-content`, `#feed-weather-content`) directly inside `#view-home`, with `home.js:87` calling `initFeedTabs()`. Move the DOM block itself (not a clone) out to a new top-level `#view-feed` container with its own `<header>Лента</header>`. Reorder sub-tabs to **Фото, Новости, Инфо** (currently News/Photos/Weather) with Фото as default-active — this is a real reorder, not just a relabel.

**3.2 — Refactor `feed.js` selectors.** Current code assumes `#view-home .doc-type-opt[data-feed]`-style scoping (hardcoded to the old parent). Introduce a `getFeedRoot()` helper and update `_initFeedSwitch`, `_initFeedSwipe`, `initFeedTabs`, `_selectFeedTab`, unread-badge handling, and deep-link targets to use it — no view-home assumptions left. Reuse 100% of existing feed.js logic (photo upload/gallery, news list, weather, birthdays, comments, activity alerts) — this is a relocation, not a rewrite.

**3.3 — Update nav bar markup and dispatch.** Add a 6th nav item is explicitly rejected by the owner — instead, `abwesenheit` is removed from both `#bottom-nav-owner` (`app.html:5444-5464`) and `#bottom-nav-worker` (`app.html:5465-5484`), and `feed` is added in its place at position 1, giving: Feed, Home(Dashboard), Chat, Objects, Profile — still 5 icon slots, Chat now centered (3rd of 5, was 2nd of 5). Update the view-switch dispatcher (`app.html:5669` area, which already has a stub `if (viewName === 'feed') initFeedView();`) — build out `initFeedView()` for real using the relocated feed.js logic.

**3.3b — Add short visible labels under each nav icon.** Current nav is icon-only, no text — for glove use and quick recognition, add compact labels: **Лента | Главная | Чат | Объекты | Профиль**. Note the nav label for the Home tab is "Главная" (short, fast to read), while the view's own on-screen `<header>` title is "Dashboard" (per 3.6) — these are intentionally different (nav label optimizes for speed, screen title optimizes for clarity). Do not rely on icon meaning alone for primary navigation.

**Glove correction — usability over compactness.** Do not preserve the old icon-only nav height at the cost of tiny text or a shrunk touch target. Each nav item (icon + label together) must remain a comfortable touch target, minimum ~52px effective height. Label text: roughly 11-12px minimum, high contrast, single line, no truncation. It is acceptable and expected for the bottom nav to become modestly taller than today's icon-only bar to fit this — don't fight for the old height. Once the real new nav height is known, recalculate every hardcoded assumption that depends on it: `--app-bottom-nav-height`, body bottom padding, the Today persistent bar's position, the RadioMiniPlayer, the Objects FAB, and the Worker Check-in FAB — all of these must derive from the actual measured new nav height, not a stale hardcoded value carried over from the icon-only bar.

**3.4 — Update every hardcoded nav-order array.** `grep -rn "\['home','chat','objects','abwesenheit','profile'\]" frontend/` and similar (swipe-nav.js's `SWIPE_VIEWS`, any TAB_ORDER constant in app.html) — replace with `['feed','home','chat','objects','profile']` everywhere, no stale copy left. Global swipe order becomes Feed↔Dashboard↔Chat↔Objects↔Profile; feed-internal swipe (Фото↔Новости↔Инфо) stays a same-level convenience, not conflicting with the outer swipe or with photo-carousel/chip/calendar/chat gestures already in those views.

**3.5 — Update all deep links.** Anywhere code does `switchView('home')` then selects a feed sub-tab (activity alerts, comments, news/photo notifications) — grep and redirect to `switchView('feed')` + correct sub-tab, preserving return context (back-navigation must land where the user actually came from, per `NavigationManager`'s existing overlay-stack behavior).

**3.6 — Rename Home to Dashboard visually only.** Keep internal `viewName='home'`/`data-view="home"` for backward compatibility (per owner's explicit instruction) — only the visible `<header>` title changes to "Dashboard". Opening the app: Owner still lands on Dashboard (unchanged), Worker still lands on Today/DailyPlan-first logic if a plan exists (unchanged) — leftmost tab position does not change default landing view.

**3.7 — Dashboard calendar widget, staffing-first (not a mini month-grid).** Add a compact block directly in `#view-home`'s dashboard content (after the KPI bars, near the existing quick-action row) — NOT a miniature month calendar. Its primary job for the Owner is operational staffing visibility: answer "кто где сегодня и кто где завтра" without opening the full calendar. Layout, in this order:

1. **Сегодня** — one line per worker: `<name> → <assigned object>` or `Отсутствует` / `Свободен`.
2. **Завтра** — same shape, plus a one-line summary (e.g. "3 назначения · 1 человек свободен").
3. A compact date strip (small, secondary — not the visual focus).
4. `[Открыть календарь]` button.

Worker's version of the widget shows only their own row (today/tomorrow assignment or absence state) — no other worker's data, matching current full-calendar privacy behavior (no exposing another worker's absence *reason*).

Extract a small reusable piece of `abwesenheit.js`'s data-loading (`loadAbwesenheit()`, `/api/abwesenheit/all`, `/api/workers/{id}/calendar`) into a shared function callable from both the widget and the full screen, so both render from one source — no second calendar backend, no duplicated fetch logic. Full month planning remains entirely behind "Открыть календарь" → existing `switchView('abwesenheit')` full screen (unchanged, still reachable, no longer via bottom nav — reachable via this Dashboard button and any other existing deep link, e.g. the current Home quick-action tile that already points there).

Commit: `refactor: split feed from dashboard navigation`, then `feat: add dashboard calendar widget`.

---

## Phase 4 — Worker glove-UX fixes (from completed audit, concrete findings)

Priority order (daily-use flows first, per audit):

1. **`checkin.js`'s required survey fields have no voice input** — the two required `<textarea>` fields ("Что сделано за день?"/"Что нужно подготовить на завтра?", `checkin.js:394` validates non-empty) force typing with dirty/gloved hands in a required daily flow, while the exact same pattern already has a working voice solution in `finish-wizard.js` via `attachVoiceInputButton` (shared.js:398). Wire the same helper onto `checkin-survey-done`/`checkin-survey-next`.
2. **`--c-brass` text contrast (2.98–3.25:1, fails WCAG AA's 4.5:1 for normal text)** used as actual status/date/error body text in several places (`.my-task-card-dates`, `.wo-th-badge`, `.wo-absence-reason`, `.js-error-state`, status badges) — darken the color or increase font-weight/size where it carries information a worker must act on. Keep as decorative-only where it's genuinely just an accent.
3. **Small daily-flow touch targets**: `.checkin-pause-btn` (32px circular stepper, tapped repeatedly in the required end-of-shift survey) and `.voice-input-btn` in `mangel.js` (35px, corner-positioned inside a textarea — undercuts its own "avoid typing" purpose). Bump both toward the ~48-56px glove-friendly range; for the voice button specifically, match finish-wizard's full-width `.fw-voice-btn` pattern instead of a small corner icon.
4. **`mangel.js` lacks the idempotency-key + `navigator.onLine` pre-check pattern** that `checkin.js` and `finish-wizard.js` already have — backport both (the pattern already exists twice in this codebase, no new design needed) so a defect-ticket retry after an ambiguous network failure can't create a duplicate.
5. Lower priority, batch if time allows: normalize `.fw-close-btn`/`.mangel-modal-close` to a consistent ~40px+ sizing; `.status-opt` segmented control height in Object Info.

Owner's brief also specifies broader Worker Today-screen standards (min 52-56px touch targets, 19-21px item titles, no color-only status, haptic on state transitions, large tappable persistent strip) — apply these as the concrete sizing/contrast targets for items 1-3 above and to the Today persistent bar if it currently has a small "Открыть →" sub-button rather than a fully-tappable strip (verify current state first, fix only if the gap is real).

**6. One-thumb / glove-mode test for every Worker primary flow.** For DailyPlan, Finish, and checklist completion specifically: run a "can this be done without precise tapping?" check on each primary action. Concretely:
- Primary actions must never be a tiny icon, corner button, small checkbox, or text link — DailyPlan/Finish rows/cards must be full-width and, where the action is "view details," the whole card should be tappable, not just a small icon on it.
- The Finish button: minimum 56px height. Reason-selection options (e.g. blocker/status reasons): minimum 52px each, full-width where the list allows it.
- Two destructive/opposite actions (e.g. a status pair, cancel-vs-confirm) must never sit directly adjacent with no spacing between them.
- Never require hover, long-press, drag, or swipe for a *mandatory* step in a workflow — those interactions may exist as optional shortcuts (per 3.4's feed-swipe-is-optional precedent) but the primary path must always be a plain tap.

Commit: `ux: improve worker glove usability`.

---

## Phase 5 — Architecture preparation ONLY (no large extraction this round)

**Do NOT perform a large `backend/main.py` router extraction in this run. Do NOT perform a large `app.html` decomposition in this run.** This release already touches bootstrap, navigation, Feed ownership, Dashboard, Calendar, Production Control, worker UX, offline behavior, and deployment tooling in one pass — stacking a 7600-line backend module split or a full app.html decomposition on top makes regression diagnosis significantly harder if anything goes wrong, for cosmetic benefit this round doesn't need. Large structural extraction gets its own later round, after this release is manually verified working in Telegram.

In this round, ONLY do the following, each justified by a concrete need that already exists elsewhere in this plan (not speculative cleanup):
- Identify module boundaries and write them down (see below) — do not act on most of them yet.
- Add a public method on `daily_plan_lib` (or the relevant `_lib.py`) wherever a route currently reaches into a private function like `dpl._load_store()` — fix only the call sites this plan's other phases already touch, not a sweep of the whole codebase.
- Build the `getFeedRoot()` helper and calendar-data-sharing function that Phase 3 already requires (3.2, 3.7) — these are needed regardless, not extra scope.
- Normalize the one concrete DTO inconsistency already found (the `BUDGET_FIELDS`/`% бюджета` key-name drift from Phase 1) if fixing it naturally touches `normalizeObjectDto()` — don't go looking for more DTO drift beyond what Phase 1 already surfaced.

Create `docs/ARCHITECTURE_REFACTOR_BACKLOG.md` listing the recommended future extraction slices (main.py routers by domain: auth/objects/checkin/feed/chat/workers/production_control/contracts; app.html's CSS/bootstrap/kontrol-day/contracts split into files) — a plan for a future round, not work done now. No mass moving of routes between files, no mass extraction of inline app.html code done solely for cleanliness in this round.

Commit: `docs: record architecture refactor backlog` (plus whatever small, justified extractions land as part of Phase 1/3's own commits — don't create a separate large refactor commit this round).

---

## Phase 6 — Network resilience (Worker Today offline fallback)

Per owner's brief: after a successful DailyPlan acceptance, cache the accepted plan snapshot in IndexedDB (or equivalent) for read-only offline fallback. If the connection drops, Worker's Today screen must still show the last-accepted plan with a clear "Офлайн · показан последний принятый план" banner — never silently pretend cached data is current, never mark execution complete locally as if server-confirmed while offline. Finish-flow offline queueing is explicitly out of scope for this round ("can be designed separately if safe") — only the read-only Today cache is required now.

Commit: fold into the glove-UX or a dedicated `feat: offline-cache worker today plan` commit.

---

## Phase 7 — Performance + observability (lighter pass)

- Audit Dashboard's startup request count for N+1/duplicate `/api/objects`-style calls; parallelize independent fetches; ensure a failed promise never becomes permanently cached (ties into Phase 0.6's prefetch-cache fix — same root mechanism).
- Feed photos: confirm thumbnail-first loading exists or add it; avoid downloading full-resolution images during bootstrap; verify blob URLs are revoked.
- Add an owner-only diagnostics view/endpoint (`System status`: Backend/Sheets/Objects/Feed/Chat/DailyPlan-sync/Drive-contracts/Build-SHA, each ✓/!/status) so a future "данные не грузятся" report is diagnosable in under a minute — this directly addresses today's incident class.

Commit: `perf: dashboard request parallelization` / `feat: owner diagnostics screen`.

---

## Testing & Verification

- Full backend pytest suite before Phase 0 changes (baseline) and after every phase — **always with `MINIAPP_DATA_ROOT=$(mktemp -d)` explicitly set**, never bare `pytest tests/`.
- `node --check` on every frontend JS file; real `html.parser`-based validation on `app.html` (same method used to verify yesterday's deploy).
- Manual smoke test via real Telegram initData (not bare curl) for the critical journeys the owner listed: Owner launch→Dashboard→Calendar→Feed(Photo/News/Info)→Chat→Objects→Worker Card→Контроль дня→Profile; Worker launch→Today→Accept→Start→Chat→Objects→Dashboard calendar→Finish→fact→prep-tomorrow; No-plan-worker launch→Start-without-plan→owner alert; network-failure→visible Retry→Retry succeeds; deploy-A→deploy-B→build-SHA matches across app.html and all JS.
- Nav-specific: tap nav, swipe nav, Telegram Back, nested overlays (comments, Worker Card, Object Detail, chat thread) all still work with the new 5-tab order; bottom nav stays visible on nested screens except keyboard-hiding cases (current behavior, must not regress).

## Deploy

**Do NOT auto-deploy.** After all phases complete and verification passes: run the full test suite, `node --check`, `py_compile`, HTML parse, and a deployment dry-run (validate-only, no copy) using the Phase 0.8 fixed `deploy_frontend.py`. Stop there. Final report to the owner must include: START SHA, FINAL SHA, root cause of the data-loading incident (confirmed above), P0/P1/P2 findings with fix+test for each, confirmation of the new nav order and Feed sub-tab order/default, Dashboard calendar owner/worker behavior confirmation, glove-audit changes list, security findings+fixes list, Production Control re-verification results, test summary with exact remaining failures/warnings, files changed, and a deploy command **plan only** (not executed) — ending in **READY FOR OWNER REVIEW** or **NOT READY** with the specific blocker.

## Execution mode — autonomous, but bounded (not the previous infinite-restart watchdog)

**The previous watchdog design is explicitly rejected.** Yesterday's `systemd-run` + 5-minute-interval watchdog restarted the autonomous process ~100 times over 8.5 hours *after the actual work was already done*, and each restart re-ran an unisolated test suite against production data — the watchdog is what turned one unsafe test into 8.5 hours of repeated corruption. A watchdog is not inherently wrong, but it must be bounded and state-aware, never a blind infinite loop.

One controlled `systemd-run` session, with restart/resume governed by an explicit state file (not implied by "is the unit still running"):

1. Progress is persisted continuously in `docs/HANDOFF.md` (existing pattern, keep it).
2. A separate execution-state file, **outside any production data directory** (e.g. `docs/EXECUTION_STATE.txt` in the repo), holds exactly one of: `RUNNING`, `COMPLETE`, `FAILED`, `STOPPED_FOR_REVIEW`.
3. A watchdog may restart the process **only when** the state file reads `RUNNING`.
4. Once the state becomes `COMPLETE`, `STOPPED_FOR_REVIEW`, or `FAILED`, the watchdog **must stop permanently** — remove its own cron/timer entry, don't just skip a cycle.
5. Maximum automatic restarts: **3**, tracked in the state file or a counter file alongside it. On the 4th failure, transition to `FAILED` and stop — never restart forever.
6. Never restart on a fixed short interval (5 minutes) once work is plausibly finished — a restart should only fire on an actual crash/usage-limit event, not a blind timer that outlives the work.
7. Every resumed session's very first actions, before any pytest invocation: `export PROMONTA_ENV=test` and `export MINIAPP_DATA_ROOT=$(mktemp -d)`, plus the hard assertion `test "$MINIAPP_DATA_ROOT" != "/home/promonta/agent/miniapp"` before the test command runs at all — belt-and-suspenders on top of the Phase 0.10 in-code firewall.
8. A resumed session must inspect current git HEAD and `docs/HANDOFF.md` and must **not** re-run phases already marked complete unless verification explicitly failed for that phase — no redoing finished work on every restart (this is also what turned yesterday's incident from "one bad write" into "dozens of bad writes").
9. Tests must never write into `/home/promonta/agent/miniapp` — enforced by 0.10, restated here as an execution-mode invariant.
10. **No production deployment from the autonomous session** — the Deploy section above already says do-not-auto-deploy; restating it here because it's also an execution-mode safety property, not just a workflow step.

No stopping between phases for interactive approval — that part of the original request stands. Stop only when the state file reaches `COMPLETE`/`STOPPED_FOR_REVIEW`/`FAILED`, matching the Deploy section's gate.
