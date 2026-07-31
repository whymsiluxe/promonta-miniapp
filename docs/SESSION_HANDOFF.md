# Session handoff — release-hardening pass (2026-07-31)

See `docs/PROJECT_STATE.md` for the current authoritative summary and
`docs/CHANGELOG.md` (2026-07-31 entry) for full detail. Short version: chat
message actions (reply/copy/forward) shipped, then three successive P0/P1
audit-fix rounds closed worker-scope/privacy/corrupt-JSON/concurrency/Caddy
issues. Deployed SHA `526922f`, CI green, 202 tests passing.

**Not done, explicit blockers before pilot**: repo is public (needs manual
switch to private), GitHub PAT not rotated, no real Telegram E2E performed
by an agent (Safari MCP non-functional in this environment — owner doing
this manually with screenshots).

---

# Session handoff — Promonta Miniapp UI overhaul (2026-07-25, long session)

## Where things stand

**Branch**: `main`. **Last pushed commit**: `ddf77ff` ("design: restructure Object Detail from 6 flat tabs to 3 (Чат/Инфо/Потребности)"). Object card v3, typography unification, and the Object Detail 3-tab restructure are ALL DEPLOYED and PUSHED, code-verified + Playwright-smoke-checked (no new console errors), NOT confirmed against real object data (test env has no Telegram initData).

**IMPORTANT gotcha hit this session, watch for it again**: `git commit -F /tmp/<file>` on the VPS can silently pick up a STALE root-owned file left over from a previous session if your `scp` to that same `/tmp/<name>` path fails with "Permission denied" (root-owned files block promonta's write) — the commit will succeed with a totally unrelated old commit message and you won't notice unless you check `git log` after. Fix used: write commit messages to `~/tmp_msgs/` (a promonta-owned dir you create yourself, e.g. `mkdir -p ~/tmp_msgs`) instead of `/tmp/` directly, and always `cat` the file remotely to confirm content before using it in `git commit -F`. This bit twice in a row this session (`4782523` and one before it both got wrong messages, fixed via `git commit --amend -F <verified-file> && git push --force-with-lease`).

**Remaining work, not started**: Radio player full rebuild, Chat Hub full rebuild, emoji→SVG in JS (blocked on owner's icon reference image), backend permission audit + security hardening (P2, deferred). See sections below for full spec details on each — do not re-derive from scratch, they're fully written out already.

## Object Detail 3-tab restructure — DONE, deployed, commit `ddf77ff`

Final structure (changed twice mid-session per owner's evolving instructions — this is the FINAL agreed structure, don't second-guess it): **Чат / Инфо / Потребности**, same 3 tabs for both owner and worker roles.

- **Инфо** tab now renders, in order: owner-only status editor (moved here from the list-preview card in an earlier session pass), Описание (new — `GET/PATCH /api/objects/{id}/description`, owner-only write, backed by the existing `object_info.json` per-object store, no new file/no Sheets column), Работы section with an Объёмы|Задачи sub-toggle (Объёмы = existing work-items list `/api/objects/{id}/info-items`; Задачи = existing owner→worker task checklist `/api/objects/{id}/tasks`, both reused as-is just relocated), Этапы (compact roadmap summary, reuses `_loadObjStages`, worker also gets the checkin start/finish shortcut here same as before), Дефекты (compact summary: open-count badge, up to 3 recent open tickets, "Все дефекты"/"+ Добавить дефект" buttons — the add button does a `setTimeout` + programmatic click on the existing `#mangel-new-btn` on the Дефекты screen rather than duplicating its open-form logic), Документы (compact summary with count badge, same pattern).
- **Потребности** tab: object-scoped, restored to a real top-level tab after initially being folded into Инфо then explicitly un-folded per owner instruction. Reuses the pre-existing `renderObjectNeedsTab`/`_loadObjNeeds` logic essentially unchanged, just re-wired into the 3-tab dispatcher and swipe-tab-order array (`OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'needs']`).
- Empty states throughout: compact single-row + inline action button (`Работы 0 [+ Добавить]` pattern), not big placeholder sentences — this was an explicit, repeated owner instruction, applied to every section in Инфо.
- Deleted dead code: old `renderObjectTasksTab`/`renderObjectDefectsTab`/`renderObjectStagesTab`/`_loadObjDefects` (superseded by the new `_renderObj*` functions that render into the new Инфо sub-containers instead of their own top-level `obj-detail-panel-*`).
- Global Потребности screen (Home-widget entry point, `#view-tasks`) was NOT touched — confirmed already correctly separate from the object-scoped tab, no change needed there.

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

## Object card v3 — DONE, deployed, commit `cea952e`

Shipped: weather-island (top-center, reuses existing per-object weather feed via `GET /api/feed/weather`, matched by object name, one-shot cached in `_objWeatherByName`), worker avatars overlap-cluster bottom-left (max 3 + N-more, first 56px/rest 46px/-14px overlap), status pill bottom-right (semantic color via `OBJ_STATUS_META`), centered title/clickable-maps-address/start-date (newly surfaced — `Дата старта` column existed in Sheets all along, `GET /api/objects` already returned it, frontend just never rendered it), single `.obj-stage-strip` replacing the old duplicated budget/status/stage chips.

Resolved during build: `_openObjTeamSheet` didn't exist — the "+N" avatar overflow click now routes to `openObjectDetail()` instead of a dedicated team bottom-sheet (judged disproportionate for a rare 4+-worker case). `openUserCard`/`openExternalLink` signatures confirmed correct in `shared.js` before use. Old `.card-stage` CSS rule (a different, older rule, still used by `my-tasks.js`) confirmed NOT referenced by the new markup — no collision.

**Still explicitly NOT done** (documented as PARTIAL in the commit message, not hidden): no live visual verification against real object photos/weather/team data (test env has no Telegram initData); no full DONE/ACTIVE/NEXT stage timeline (deliberately deferred, would need N+1 per-card `/api/objects/{id}/stages` calls).

## Typography unification — DONE, deployed, commit `871414a`

`--font-body` genuinely resolved to Montserrat while `--font-heading` resolved to Manrope — confirmed real via `grep`, not a false audit claim (see `docs/audit/AUDIT_COVERAGE_MATRIX.md` section 2 for the full correction writeup). Both tokens now point to Manrope; Montserrat weight-list removed from the Google Fonts `<link>` entirely, Manrope now fetches 400/500/600/700/800 (the 400/500/600 that used to be fetched for Montserrat are now fetched for Manrope, since `--font-body` needs those weights too). Grep-confirmed no other Montserrat references remain in the live `app.html`/`tokens.css` (only stale `.bak-pre-*` files and `.archived-legacy/` dead pages still mention it, neither served). Playwright screenshot taken post-deploy showing the unified font rendering (not a pixel-perfect brand-style claim, just confirms the font actually loads and renders, which it does).

## Immediate next steps (in order) when resuming

1. **Radio player full rebuild** (own spec, detailed in "What triggered this phase" above) — IN PROGRESS as of this handoff, not yet started coding. Delete the 82px black orb entirely (not just hide/offset it — the owner explicitly said the earlier offset-only fix does not count as fixing this). Build `HomeRadioPlayer` (background-image card matching the purple reference screenshot's composition but in Old Money palette — deep forest/charcoal/brass, not purple neon; previous/play-pause/next controls; LIVE-vs-TRACK-mode progress display; loading/buffering/error/offline states) and `RadioMiniPlayer` (compact, appears over bottom-nav only while playing, hides during keyboard/modal/fullscreen-photo). Centralize playback in a single `RadioController` (no duplicate `Audio` elements, no duplicate listeners on repeat Home visits). Owner also asked for a switcher on the dashboard to pick radio station/genre (e.g. techno or whatever stations exist) — check what station list the current audio-source backend actually supports before designing this, don't assume multiple stations exist if the current implementation is single-stream.
2. **Chat Hub full rebuild** (own spec, detailed in "What triggered this phase" above) — NOT STARTED, the single largest remaining item, treat as its own multi-session project. Dark Old-Money palette (see the exact hex tokens in the original spec message if resuming this), animated expandable search circle, horizontal worker-avatar strip, 4 tabs (Общий/Личные/Объекты/Дефекты), real direct 1:1 threads with deterministic unique-pair thread IDs (no duplicate threads for A→B vs B→A), reactions, read receipts, unread badges, proper empty/loading/error states per tab.
3. **emoji→SVG in JS files** (~93 occurrences across 11 files: `home.js` 16, `profile.js` 12, `objects.js` 9, `ai.js` 7, `tools.js` 7, `chat.js` 5, `mangel.js` 5, `feed.js` 4, `abwesenheit.js` 3, `tasks.js` 3, `checkin.js` 2) — BLOCKED, waiting on owner to send an icon-style reference image. They said "жду референс-картинку" — check if one has arrived before starting; do not invent a style unilaterally again (already got explicit pushback for doing exactly that once this session).
4. **Backend permission audit (all 106 routes)**, AI subprocess security review, upload magic-byte validation, CSV formula-injection guard, path-traversal sweep — all explicitly deferred to "next stage" per the owner's own priority split earlier this session (typography/radio/object-card/object-detail were "urgent," these are "next stage"). Not started.

## Standing rules for this whole effort (don't relitigate, just follow)

- Never claim "unified"/"fixed"/"done" without actual verification — owner has caught two overclaims this session (typography, and the original "8 of 62" framing) and reacted with real anger both times. When in doubt, say PARTIAL and say exactly what's missing.
- Deploy pattern established all session: edit in `/home/promonta/agent/miniapp-repo` → verify (`node --check`/`py_compile`/`check_inline.py`) → `.bak-pre-<label>-<timestamp>` copy to both `/home/promonta/agent/miniapp/` (backend) and/or `/var/www/miniapp/` (frontend) → restart `promonta-miniapp.service` ONLY with explicit owner go-ahead each time → Playwright smoke-check the live URL → commit → push. One logical fix per commit.
- No test framework exists in this project. Every "test" claim in the audit documents (Playwright E2E suites, unit tests, visual regression baselines) is aspirational per the ChatGPT audit's own spec, not yet real infrastructure — don't pretend otherwise, don't claim tests exist when they don't.
- Full plan file with the original 8-step (now superseded/expanded) plan lives at `/Users/mac/.claude/plans/cozy-honking-leaf.md` on the Mac side — read it for the earlier Fable-reviewed context if needed, but the scope has grown substantially past what's written there as of this handoff.
