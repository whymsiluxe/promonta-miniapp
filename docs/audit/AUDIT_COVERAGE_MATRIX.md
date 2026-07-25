# Audit Coverage Matrix — ChatGPT 62-section master audit vs. actual repo state

Generated 2026-07-25. Source: the full master-prompt audit document (62 numbered sections) pasted by the owner across this session. Every section is listed with an honest status — no section is silently dropped. Where a fix landed, the commit hash is given; where it did not, that is stated plainly.

Status legend: **DONE** (implemented, code-verified, deployed) / **PARTIAL** (some of the requirement shipped, real gaps remain) / **NOT STARTED** / **BLOCKED** (needs owner decision or external resource) / **DEFERRED BY OWNER** (explicit decision to skip) / **FALSE** (the audit's claim was checked against code and found incorrect).

| # | Section | Status | Evidence / Commit | What's missing |
|---|---|---|---|---|
| 0 | Главная цель проекта (vision statement) | N/A | — | Not a discrete deliverable, guides everything below |
| 1 | Ограничения (no DSGVO, no rewrite, no microservices) | DONE (respected) | Whole session | Constraints followed throughout |
| 2 | Источник истины (code over docs) | DONE (practice) | All fixes this session code-verified before acting | — |
| 3 | Скриншоты как спецификация | DONE | 20 screenshots reviewed, symptoms mapped | — |
| 4 | Telegram system UI overlap (P0) | PARTIAL | `a887fc2` (radio Home offset) | Only the radio-widget instance fixed. No systematic sweep of every fixed/sticky element against safe-area confirmed complete; no `TelegramViewportController` module built |
| 5 | Telegram Viewport Controller (dedicated module) | NOT STARTED | — | No `frontend/js/core/telegram-viewport.js` created. Existing `_applyTelegramSafeArea()` inline in app.html works but is not the prescribed dedicated module with full CSS-variable contract (`--tg-content-safe-*`, `--app-keyboard-height`, etc.) |
| 6 | Fullscreen necessity review | NOT STARTED | — | `requestFullscreen()`/`expand()` still called unconditionally on every load (confirmed `app.html:3815-3816`); the "only use fullscreen for photo viewer" redesign not done |
| 7 | Telegram control exclusion zone (systemic, not `padding-top:44px`) | PARTIAL | Radio fix is a point patch, not a systemic zone | No enforced exclusion-zone component; each screen still hand-manages its own top padding via `--tg-safe-top` |
| 8 | Debug safe-area dev tool | NOT STARTED | — | No diagnostic overlay built |
| 9 | Navigation — single source of truth | PARTIAL | `NavigationManager` exists (pre-dated this audit), overlay-stack now has 1 real consumer (`f3492f5`) | Route-stack vs 5-tab-stack question still single-stack (documented decision, not audit's per-tab spec); many screens still use manual `style.display`/inline `onclick` alongside NavigationManager |
| 10 | Back из комментариев → Profile bug | **DONE** | `f3492f5` — root-caused and fixed, `registerOverlay` wired | Verified code-level + Playwright smoke only; no physical-device confirmation |
| 11 | Убрать дублирующие back-кнопки | NOT STARTED | — | Telegram native BackButton and custom `.chat-back-btn` can still coexist; no suppression logic added |
| 12 | Per-tab navigation state | NOT STARTED | — | Single shared stack remains (documented architectural choice from Phase 0.5, not revisited) |
| 13 | Screen lifecycle (mount/activate/deactivate/unmount contract) | NOT STARTED | — | No formal lifecycle interface exists; cleanup is ad-hoc per screen |
| 14 | Визуальное направление (Old Money definition) | PARTIAL | `tokens.css` has forest/brass/ivory tokens (prior session) | Not audited against every screen this session; some decorative widgets confirmed still neumorphic |
| 15 | Design System v2 (full token rewrite) | FALSE (partially) / PARTIAL | Design-system agent this session confirmed: font vars already unified (`--font-heading`/`--font-body`), NOT the "mixed Montserrat/Manrope chaos" the audit claimed | **Correction issued in this doc, section 2 below**: `--font-heading` and `--font-body` still point to *two different families* (Manrope/Montserrat) — the audit's *conclusion* (visually inconsistent) is right even though the earlier session's "FALSE, already unified" claim was an overstatement. Full token-matrix (`--color-canvas` etc exact hex values from the audit) not applied 1:1 |
| 16 | Типографика (single Manrope family, remove Montserrat) | NOT STARTED | — | `--font-body: Montserrat` still active; Montserrat still loaded via Google Fonts link. See TYPOGRAPHY_INVENTORY.md |
| 17 | Spacing/radius/shadow tokens | NOT STARTED | — | No 4/8/12/16/20/24/32 spacing scale audit done; radius/shadow values not consolidated to 3 tokens |
| 18 | Icon system (SVG, no emoji) | PARTIAL | `30f1806` — 8 functional emoji in app.html replaced with SVG | JS files still have ~93 emoji occurrences (`objects.js` 9, `home.js` 16, `profile.js` 12, etc.) — NOT started, blocked pending owner's icon-style reference image |
| 19 | Home restructure | NOT STARTED | — | KPI/alert-card hierarchy from the audit's spec not rebuilt |
| 20 | Radio player (HomeRadioCard + MiniPlayer) | PARTIAL → now full redesign requested separately | `a887fc2` only fixed offset/collision | Owner has since escalated this to a full separate spec (background-image player, LIVE/TRACK modes, RadioController) — **NOT STARTED** against the new spec |
| 21 | Bottom navigation lightening | NOT STARTED | — | Nav still uses current shadow/blur values, not re-tuned |
| 22 | Photo carousel + comment composer | **DONE** (the two confirmed concrete bugs) | `5c6c627` (composer flexbox), `ec603cc` (swipe) | Reusable `PhotoCarousel` component per audit's spec (mode=card/mode=viewer, preload, lazy-load) NOT built — the fix was scoped to the specific broken modal, not a new shared component |
| 23 | Comment Composer (reusable component) | PARTIAL | Same fix as #22 patches the one broken instance | No shared `Composer` component extracted; chat composer and photo-comment composer remain separate implementations |
| 24 | Общий чат (bubble grouping, avatars, date dividers) | NOT STARTED | — | No message-grouping/avatar-per-message rework done this session |
| 25 | Chat data logic (monotonic cursor, not just timestamp) | NOT STARTED | — | Backend still uses append-only JSON + timestamp-based polling, no cursor/version contract |
| 26 | Object chat composer sdvinut | **DONE** (bottom-nav visibility) + PARTIAL (full reusable ChatThread) | `e21b2d7` | Fixed nav-hide only; the audit's "reusable ChatThread component with fullscreen/embedded modes, no global DOM reparenting" NOT built — `embedObjectChat()` still physically reparents the one global `#chat-thread-detail-view` node |
| 27 | Objects list screen (search/filter/pagination) | NOT STARTED | — | No pagination/lazy-load added; search+filter already existed pre-session |
| 28 | Object card deep audit | PARTIAL → now full redesign requested separately | `a7d4d34` — removed status-switch/budget/stage dupes | Owner has since escalated to full reference-composition rebuild (weather island, worker avatar overlay, maps-address, stage-summary strip) — **NOT STARTED** against the new spec |
| 29 | Object Detail IA (4 groups instead of 6 flat tabs) | NOT STARTED | — | Still 6 flat tabs (Чат/Инфо/Задачи/Потребности/Дефекты/Этапы), no Overview/Работа/Чат/Файлы regrouping |
| 30 | Задачи объекта (Tasks +-button bug) | BLOCKED | — | Confirmed UNVERIFIED without live device/console repro; requires the owner or a live session to reproduce, cannot fix blind |
| 31 | Потребности объекта (role-specific UI, state machine) | PARTIAL | `fd20d6a` — object-scoped visibility filter fixed | Full state machine (NEW/ACKNOWLEDGED/IN_PROGRESS/ORDERED/DELIVERED/DECLINED/CANCELLED), type/quantity/unit/urgency fields, owner processing UI — NOT built. Current model only has title/description/object_id/priority/status(3-value) |
| 32 | Голосовое создание потребности (preview before create) | NOT STARTED | — | AI voice-extract flow (if it exists) not audited for auto-create-without-confirmation risk |
| 33 | Profile screen rework | NOT STARTED | — | Accordion default-state, CSV button demotion, etc. from the audit not done |
| 34 | Calendar rework | NOT STARTED (prior session did a partial pass) | — | Not touched this session |
| 35 | Bubble Assignment | NOT STARTED | — | Not touched this session |
| 36 | Frontend architecture (core/components/screens reorg) | NOT STARTED | — | No new directory structure created; all fixes this session were surgical edits to existing files |
| 37 | API client (single client, retries, idempotency) | NOT STARTED | — | No unified `api.js` rewrite |
| 38 | UI states (Skeleton/EmptyState/ErrorState components) | NOT STARTED | — | No shared state components built |
| 39 | Offline queue (IndexedDB) | NOT STARTED | — | Explicitly deferred as disproportionate to project scale in the earlier plan |
| 40 | Backend audit (all 106 routes, full table) | **NOT STARTED** | — | This is the single largest unclaimed item. No route-by-route permission/scope/risk table exists yet |
| 41 | AI security (subprocess sandboxing) | NOT STARTED | — | `--dangerously-skip-permissions` usage, cwd/env exposure not audited this session |
| 42 | Path traversal audit | NOT STARTED | — | No systematic `os.path.join`/`open()` sweep done this session (prior sessions did partial IDOR fixes, not the same thing) |
| 43 | JSON storage / lost updates | PARTIAL | `_atomic_write_json` + per-file locks already existed (prior session); confirmed correct in this session's earlier read | Full read-modify-write transaction lock across multi-store operations not audited this session |
| 44 | Check-in / shifts state machine | PARTIAL | `2b3ff13` (GPS-suspect flag), `03cd526` (2-photo minimum) | Full DRAFT/STARTING/ACTIVE/FINISHING/COMPLETED/CORRECTION_REQUIRED state machine not built; concurrency test not written |
| 45 | Resource-level permissions (single permission service) | NOT STARTED | — | `require_owner()`/`require_object_access()` etc partially exist ad-hoc per route, not consolidated into one service |
| 46 | Uploads (magic-byte validation, size caps) | NOT STARTED | — | No magic-byte/decompression-bomb protection added this session |
| 47 | Google Sheets integration hardening | NOT STARTED | — | Silent `except: pass` around sync calls not swept this session |
| 48 | CSV/dates/time (formula injection guard) | NOT STARTED | — | Not audited this session |
| 49 | Logging/health (liveness vs readiness) | NOT STARTED | — | Not touched this session |
| 50 | Backup (restore verification) | NOT STARTED | — | Not touched this session |
| 51 | Test infrastructure (Playwright + Telegram mock) | NOT STARTED | — | Confirmed repeatedly: no test framework exists in this project. Every fix this session was manually Playwright-smoke-checked, not covered by a persistent suite |
| 52 | Required E2E flows | NOT STARTED | — | No automated E2E suite exists |
| 53 | Visual regression baselines | NOT STARTED | — | No baseline screenshots stored/compared automatically |
| 54 | Accessibility / field conditions | NOT STARTED | — | Not audited this session |
| 55 | Performance budget | NOT STARTED | — | Not measured this session |
| 56 | Backend architectural direction (modular package) | NOT STARTED | — | `main.py` remains a single ~4000-line file |
| 57 | Phase ordering (PHASE 0-10) | PARTIAL | Phase 0 (audit) + slices of Phase 1 (safe-area) done | Phases 2-10 not started |
| 58-61 | Git workflow / required docs / acceptance criteria / final report | PARTIAL | Small commits maintained throughout; this document is the first `docs/audit/*` file created | `FRONTEND_SCREEN_MAP.md`, `TELEGRAM_SAFE_AREA_AUDIT.md`, `NAVIGATION_STATE_MAP.md`, and the other 10 prescribed audit docs NOT created — only this coverage matrix exists so far |
| 62 | Начало работы (initial 22-step checklist) | PARTIAL | Most read-only discovery steps were done via 3 parallel agents this session | Formal write-up of findings into the prescribed docs/audit/*.md files incomplete |

## Section 2 — Correction to the earlier "typography is FALSE" claim

The design-system Explore agent earlier in this session reported: *"тезис аудита ChatGPT о смешанных Montserrat/Manrope fonts не подтверждается — только 2 переменные, `--font-heading`/`--font-body`, никакого хардкода system-ui."*

This was **technically accurate but materially misleading**. It checked that no *literal* font-family string leaked outside the two CSS variables — true. It did **not** check what those two variables actually resolve to. They resolve to:

```css
--font-heading: 'Manrope';
--font-body: 'Montserrat';
```

Two different font families are still loaded and used simultaneously across the entire app (headings in one typeface, body text in another). The owner's underlying complaint — inconsistent/unprofessional typography — was **correct**. The earlier session's "FALSE" verdict is retracted here. Corrected status: audit section 16 (single Manrope family) is **NOT STARTED**, not resolved.

## What this matrix proves

Of the ~57 substantive, actionable sections in the master audit (excluding pure preamble/vision sections 0 and constraint sections 1-3):
- **2 fully DONE** (back-button overlay bug, object-scoped Needs visibility)
- **~12 PARTIAL** (real progress, real gaps remain, mostly the P0/P1 concrete bugs from the screenshots)
- **~40 NOT STARTED**
- **1 BLOCKED** (Tasks button, needs live repro)
- **1 correction issued** (typography)

The 8 commits from the earlier "8-step plan" covered the concrete, reproducible bugs visible in the owner's screenshots — a real subset of section 4, 10, 22, 23, 26, 28, 31 partially. They did not constitute, and were never claimed by this document to constitute, coverage of the full 62-section audit. That gap is now explicit rather than implicit.
