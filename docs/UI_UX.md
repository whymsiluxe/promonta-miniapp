# UI/UX

Vanilla HTML/CSS/JS, no design-system framework. Telegram Mini App — must respect Telegram's WebView constraints (safe-area, dynamic viewport, host header).

## Navigation

Role-based bottom nav, two parallel DOM blocks (`#bottom-nav-owner` / `#bottom-nav-worker`) switched by `applyRoleNav()` in `app.html`, not one nav with conditionally-hidden items.

- **Owner**: Home / Objects / Mängel (labeled "Дефекты") / Chat / Profile.
- **Worker**: Home / Chat / Start-Finish (center FAB, shift checkin) / Календарь (Abwesenheit) / Profile. Mängel entirely hidden from worker.

Swipe-between-tabs gesture (`js/swipe-nav.js`) explicitly excludes chat category tabs and Kanban/Mangel views from the global swipe handler (per recent frontend commits) — a generic re-enable of swipe-everywhere would likely reintroduce the bug that exclusion fixed.

## Dashboards (role-specific, not a shared component)

- **Owner Home**: KPI bar, quick-actions grid, weather card (full), object budget rings (SVG progress circles).
- **Worker Home**: 2×2 tile grid (Messages/Tasks/Alerts-important/Alerts-critical, 3D CSS icons), two wide tiles (Objects/Tools), compact weather card, activity feed.

## Design language (per July 2026 sessions)

- Dark weather-card theme (`#0a0a0a` background, `1px solid var(--border-color)`) extended across worker tiles, owner quick-actions, object/tool cards, feed cards, abwesenheit request cards.
- 3D volumetric CSS icons (radial-gradient sphere + inset highlight/shadow) replaced emoji in most of the newer UI, including a per-tool-type icon resolver (`_toolIcon3d()` in `tools.js`, keyword-matches tool name to icon).
- **2026-07-22 late-session redesign** (not yet independently re-verified in this recovery pass, flagging so it isn't assumed stable without a look): splash screen redesigned from a space theme to a "luxury cinematic" gold palette; Home screen icons changed from volumetric spheres to flat color squares with a floating stacked-card animation; a warm color palette applied across CSS root variables and hardcoded values in `feed.js`/`profile.js`. If revisiting this area, check it actually rendered correctly — this was mid-session work when the prior Claude Code session was lost.

## Known bugs, fixed (per session history — spot-check before assuming still fixed)

- Chat/AI fullscreen view had dark text on dark background in several places (status-switch, doc-type-switch, ai-model-select, modal-btn.secondary) — fixed per frontend git log (`3806ad7`, `bcff167`).
- `#chat-thread-detail-view` wasn't a flex container, so the message input bar didn't stick to the bottom of the screen — fixed (`display:flex` + flex-column).
- Accordion (tasks-body/history-body) used a fixed `max-height` causing leftover empty space when collapsed — fixed with grid `0fr`/`1fr` technique (`271bc45`).
- Modal z-index (300/500) sat below the floating alert bubble (1200) — fixed, modals now `z-index: 5000` (`44e977d`).
- Long object/worker/task names broke card layout — fixed with `text-overflow: ellipsis` (`f8ec412`).
- Disabled buttons only changed opacity, no other visual cue — fixed to also change background/color (`7a34c16`).
- A chat-navigation feature was attempted then **rolled back** (2026-07-22, ~23:23) after it broke something — see git history / prior session notes if re-attempting this area; don't assume the rollback reason is still relevant without checking what was tried.

## Known unresolved (do not claim fixed without checking current code)

- A chat/AI-tab scroll bug was worked on across 3 different architecture attempts, ended on an approach ("variant B") that was **not confirmed working by the user** as of the last note on it. Treat as open until someone explicitly verifies it in the live app.

## Accessibility / localization

- Russian is the primary UI language (owner and current workers are Russian-speaking). German and Ukrainian localization: NOT_IMPLEMENTED — no i18n system found, strings are hardcoded Russian throughout the JS modules.
- WCAG AA contrast fix applied to secondary/warning text on beige cards (`c240ec4`) — spot-fix, not a systematic contrast audit.

## What has not been independently re-verified in this recovery pass

Almost all of the above is carried forward from prior session notes (claude-mem observations), not re-tested against the live app today. Before relying on any "fixed" claim here for a change in the same area, actually open the app and look — see [TESTING.md](TESTING.md).
