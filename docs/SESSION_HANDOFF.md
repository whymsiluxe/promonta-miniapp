# Session handoff — Promonta Miniapp UI overhaul (2026-07-25, long session)

## Where things stand

**Branch**: `main`. **Last pushed commit**: `5181b77` ("audit: full coverage matrix"). Everything after this point (object card v3 rewrite) is IN LOCAL SCRATCHPAD ONLY, NOT deployed, NOT committed.

## What triggered this phase

Owner sent a 62-section ChatGPT master audit + screenshots demanding a Telegram-safe-area/navigation/design overhaul. First pass: I fixed 8 concrete confirmed bugs (radio-widget offset, photo-comments Back→Profile navigation bug via NavigationManager overlay registration, comment-composer flexbox collapse, missing carousel swipe, object-scoped Needs backend filter, object-chat bottom-nav hide, object-card data duplication removal, KPI/avatar typography sizing) — all committed and deployed (commits up through `9ac5563`, then emoji-sweep `30f1806`).

Owner was angry that this only covered 8 of 62 sections and demanded a full honest coverage audit + continuation of the remaining work, escalating three areas into full separate redesign specs:
1. **Radio player** — full HomeRadioPlayer (background-image card, LIVE/TRACK modes, previous/play-pause/next, RadioController) + RadioMiniPlayer, replacing the old 82px black orb entirely. NOT STARTED yet.
2. **Object card** — full recomposition matching a ski-resort reference screenshot (hero photo with weather-island top-center overlay, worker-avatar overlap bottom-left, status-pill bottom-right, then title/clickable-maps-address/start-date/stage-summary-strip below). IN PROGRESS (see below).
3. **Chat Hub** — full messenger rebuild: expandable animated search circle, horizontal worker-avatar strip, 4 tabs (Общий/Личные/Объекты/Дефекты), direct 1:1 threads with deterministic unique-pair IDs, reactions, read receipts, dark Old-Money palette. NOT STARTED — this is the single largest remaining item, realistically its own multi-day project.

Then owner also sent a fourth spec: restructure Object Detail from 6 flat tabs down to 2 (Чат + Инфо), with Инфо containing: status block, new Описание (description) section, Работы (with Объёмы/Задачи sub-toggle), Этапы (can fold into Работы), Дефекты summary, Документы summary — all with compact empty-states (`Работы 0 [+ Добавить]`) instead of big "нет данных" placeholder text. NOT STARTED — explicitly told the owner I'd finish the object-card work first before starting this, since they're two different screens (list-preview card vs. detail screen) and I don't want to interleave incomplete edits across both.

I also published `docs/audit/AUDIT_COVERAGE_MATRIX.md` (commit `5181b77`) — an honest per-section status table against the full 62-section audit. Key finding in it: the earlier session's claim "mixed Montserrat/Manrope fonts is a FALSE audit claim" was **retracted** — `tokens.css` genuinely has `--font-heading: Manrope` and `--font-body: Montserrat`, two real families still in simultaneous use. Typography unification (single Manrope) is still NOT STARTED.

## Backend facts discovered this session (don't re-derive, just use)

- Google Sheets `Объекты` tab real header row: `['ID объекта', 'Объект', 'Адрес', 'Статус', 'Бюджет (EUR)', 'Потрачено (EUR)', 'потрачено в % от бюджета', 'Текущий этап', 'Папка на Drive', 'Дата создания', 'Последнее уведомление %', 'Заметка', 'Дата старта', 'Дата окончания']` — `Дата старта`/`Дата окончания` genuinely exist and are already returned by `GET /api/objects` (it does `dict(zip(header, r))`, nothing is filtered out) — frontend just never rendered them until now.
- No coordinates/lat-lon field exists anywhere for objects. Weather is NOT geocoded per-object from frontend — there's an existing cron-populated `/home/promonta/agent/.weather_feed.json` (list of per-object weather entries, matched by `object` field = the object's name string, includes `wave[0]` = today's forecast with `tmax`/`tmin`/`hourly[].weather_code`). Exposed via `GET /api/feed/weather` (returns the whole feed, not filtered per-object). My object-card code reuses this via a `_ensureObjWeatherLoaded()` one-time fetch + `_objWeatherByName` lookup map — avoids N+1 per-card weather requests.
- `GET /api/objects/{id}/stages` exists but is per-object (would be N+1 if called per card) — object card v3 deliberately does NOT call it, just shows the single `Текущий этап` string already present in the list response. Full stage timeline (DONE/ACTIVE/NEXT) stays in Object Detail only.

## Object card v3 — exact current state of the edit (IN PROGRESS, not deployed)

Working file: `/private/tmp/claude-501/-Users-mac/bd3116d0-0e81-41b7-bef1-c3adc77c13da/scratchpad/objects.js` and `/private/tmp/claude-501/-Users-mac/bd3116d0-0e81-41b7-bef1-c3adc77c13da/scratchpad/app.html` — both edited locally, NOT yet copied back to the VPS repo, NOT deployed, NOT committed.

Changes made so far in `objects.js`:
- New `OBJ_STATUS_META` lookup (status string → {color, label}) replacing the old inline status-color ternary.
- New `_objStatusMeta()`, `_objStartDateLabel()` (formats `Дата старта` as "Начало: 25 июля 2026" via `toLocaleDateString('ru-RU', {day:'2-digit',month:'long',year:'numeric'})`), `_ensureObjWeatherLoaded()` (async, populates module-level `_objWeatherByName` cache from `/api/feed/weather`, one-shot), `_objWeatherIslandHtml()` (renders the weather-island markup if data exists for that object name, else empty string).
- Rewrote `renderObjectCard()` completely: hero now has weather-island (top-center) + worker avatars max-3-with-overlap-plus-N (bottom-left, first avatar 56px others 46px, -14px overlap) + status pill (bottom-right, uses `--pill-accent` CSS var driven by `OBJ_STATUS_META` color) instead of the old live-pill-with-budget-percent. Below hero: centered title, clickable maps-address (uses `openExternalLink()`, guards empty address with "Адрес не указан" and disables the click), start-date line (only rendered if `_objStartDateLabel()` returns non-empty), then a separate `.obj-stage-strip` pill row (still `stage-clickable` class, still opens Object Detail stages tab) replacing the old duplicated budget/status/stage chip row entirely. Kept: `.obj-mangel-link` (defects shortcut, now SVG icon not emoji), owner-only `.metrics` budget bar at the bottom (single source of budget truth, unchanged from the previous dedup pass).

Changes made so far in `app.html` (CSS only, one block replaced):
- Replaced the entire `/* OBJECT CARD V2 */` CSS block (was lines ~2024-2043) with a new `/* OBJECT CARD V3 */` block: `.obj-card-hero` height increased 120px→200px (room for 3 overlay elements), new `.obj-weather-island`, `.obj-hero-status-pill`, restyled `.obj-people-dot`/`.obj-people-add`/`.obj-people-more` (removed the old fixed 36px — now sized inline per avatar via the JS), `.obj-card-body` now `text-align:center` (title/address/date all centered per the reference composition), new `.obj-card-startdate`, new `.obj-stage-strip` (replaces old `.obj-chips-row`/`.obj-stat-chip`, which were deleted).

## What is NOT done yet on the object card (must finish before it's deployable)

1. **`_openObjTeamSheet('${oid}')`** is referenced in the new `renderObjectCard()` (the "+N" avatar overflow click handler) but **the function does not exist anywhere in the codebase yet** — was mid-way through verifying this with `grep` when the session got interrupted to write this handoff. Must either implement a real bottom-sheet showing the full team list, or fall back to something that already exists (e.g. just open Object Detail, or reuse whatever team-list UI Profile→Команда already has).
2. **`openUserCard`/`openExternalLink`** — confirmed to exist in `frontend/js/shared.js` (grep found the file, did not yet re-verify the exact function signatures/behavior match what the new card code expects — should double check `openUserCard(userId)` signature before trusting it silently works).
3. Old `.card-stage` CSS rule (lines ~640-649 in app.html, a *different*, older rule than the deleted V2 block — used elsewhere too, e.g. `.stage-wait` sub-class) was NOT touched — need to verify the new `.obj-stage-strip` doesn't rely on any of that old rule's cascade accidentally, since `stage-clickable` class name is still shared between old and new markup.
4. **No `node --check` / inline-script verification run yet** on either edited file post-changes.
5. **Nothing copied to the VPS repo, nothing deployed to `/var/www/miniapp/` or `/home/promonta/agent/miniapp/`, no `.bak-pre-*` backups taken, no commit, no push.** The local scratchpad files are the only copy of this work right now — if this session dies before the next deploy step, redo the sync from the scratchpad paths above, not from scratch.
6. Not yet tested visually via Playwright at all for this specific change (previous fixes this session all got a Playwright smoke-check after deploy; this one hasn't reached that step).

## Immediate next steps (in order) when resuming

1. Finish verifying `_openObjTeamSheet` — implement it or replace the call site with an existing equivalent.
2. Re-verify `openUserCard`/`openExternalLink` signatures in `shared.js` actually match usage.
3. `node --check` both scratchpad files.
4. Deploy pattern: backup `.bak-pre-objcardv3-<timestamp>` in both `miniapp-repo` and live paths (`/var/www/miniapp/`), copy, verify inline scripts via `/tmp/check_inline.py` on the VPS, curl-check `app.html`/`js/objects.js` return 200, Playwright-navigate and check console for new errors.
5. Commit + push with a descriptive message (do NOT claim "Old Money"/"reference composition matched" as DONE without an actual screenshot comparison — the owner has explicitly called out overclaiming twice this session already).
6. THEN move to: Object Detail 6→2-tab restructure (owner's fourth spec, detailed above) — separate task, separate commit.
7. THEN: typography unification (single Manrope, drop Montserrat from `--font-body` and the Google Fonts `<link>`) — small, fast, high-value, was queued but deprioritized when owner said "Object card first."
8. THEN: Radio player full rebuild (own spec, see above) — sizeable but self-contained.
9. Chat Hub — explicitly the largest remaining item, treat as its own multi-session project, do not attempt to rush it alongside the others.
10. emoji→SVG in JS files (~93 occurrences across 11 files) — BLOCKED, waiting on owner to send an icon-style reference image (they said "жду референс-картинку" and have not sent one yet as of this handoff).
11. Backend permission audit (106 routes), AI subprocess security, upload validation, CSV injection guard — all explicitly deferred to "next stage," not started.

## Standing rules for this whole effort (don't relitigate, just follow)

- Never claim "unified"/"fixed"/"done" without actual verification — owner has caught two overclaims this session (typography, and the original "8 of 62" framing) and reacted with real anger both times. When in doubt, say PARTIAL and say exactly what's missing.
- Deploy pattern established all session: edit in `/home/promonta/agent/miniapp-repo` → verify (`node --check`/`py_compile`/`check_inline.py`) → `.bak-pre-<label>-<timestamp>` copy to both `/home/promonta/agent/miniapp/` (backend) and/or `/var/www/miniapp/` (frontend) → restart `promonta-miniapp.service` ONLY with explicit owner go-ahead each time → Playwright smoke-check the live URL → commit → push. One logical fix per commit.
- No test framework exists in this project. Every "test" claim in the audit documents (Playwright E2E suites, unit tests, visual regression baselines) is aspirational per the ChatGPT audit's own spec, not yet real infrastructure — don't pretend otherwise, don't claim tests exist when they don't.
- Full plan file with the original 8-step (now superseded/expanded) plan lives at `/Users/mac/.claude/plans/cozy-honking-leaf.md` on the Mac side — read it for the earlier Fable-reviewed context if needed, but the scope has grown substantially past what's written there as of this handoff.
