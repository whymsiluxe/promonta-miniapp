# HANDOFF — 09.09.2026 evening autonomous run

**Started**: autonomous run, owner asleep.  
**HEAD at start**: 7d0d258  
**Branch**: main

---

## Status

### ITEM 1 — Composer keyboard lag
Status: **PENDING OWNER VERIFICATION** (no code change needed here)  
Deployed in 7d0d258 (localStorage cache survives Mini App reopen). Owner must test live.  
If still broken: fallback = snap with no animation (plain `position:absolute`, no `transform`).

### ITEM 2 — Reply-bar positioning
Status: **IN PROGRESS**  
Root cause: `.chat-input-bar` became `position:absolute; bottom:0` in 74b9e6f — removed from flex flow. `#chat-reply-bar` remained in flex flow but ends up at the very bottom of container, where the absolute input-bar overlaps it (z-index:2). Fix: make `#chat-reply-bar` also position:absolute above the input-bar.

### ITEM 3 — Team-add popup ~1s delay
Status: **IN PROGRESS**  
Root cause: handler did `await api('/api/objects')` (all objects) to resolve objectName before opening the sheet. Object detail page already has `_objDetailCurrentName` set in objects.js:935. Fix: use that variable directly, no API call needed.

### ITEM 4 — Task-note textarea keyboard lag
Status: **IN PROGRESS**  
Root cause: `.bottom-sheet-overlay` has no `height: var(--tg-vp-height)`, so keyboard shrinking the visual viewport doesn't shrink the overlay on Telegram fullscreen. `.assignment-sheet-panel` uses static `85vh`. Fix: add `height: var(--tg-vp-height, 100dvh)` to `.bottom-sheet-overlay`, update `.assignment-sheet-panel` max-height to use `--tg-vp-height`.

### ITEM 5 — Object completed → assignment blocked, no path forward
Status: **IN PROGRESS**  
Existing endpoint: `PATCH /api/objects/{id}/status` (main.py:3474, owner-only). Fix: in assignment-sheet.js confirm step, when catch yields "Объект завершён" error, show inline button to set status→"В работе" then auto-retry submit.

### ITEM 6 — Worker profile duplicate calendar
Status: **DEFERRED — needs owner clarification**  
See docs/OPEN_QUESTIONS_09sep2026.md. Not safe to remove UI without knowing what owner considers "the duplicate".

### ITEM 7 — Dashboard unread message count badge
Status: **IN PROGRESS**  
`#home-chat-badge` exists in home.js but was never populated. `_loadHomeChatSummary()` fetches `/api/chat/my_threads` but ignores unread count. `/api/chat/unread_count` already used for worker-tile. Fix: also call it in `_loadHomeChatSummary()` and update `#home-chat-badge`.

---

## Commits in this run

*(filled as work progresses)*

---

## Open questions

See `docs/OPEN_QUESTIONS_09sep2026.md`.
