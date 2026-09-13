AUTONOMOUS_STATUS: IN_PROGRESS

# Autonomous Promonta Miniapp 3-Stage Plan - 2026-09-13

You are running unattended on the production VPS as Codex CLI.

The owner explicitly authorized autonomous work, tests, commits, pushes, production deploys, and updating `/home/promonta/agent/FILESYSTEM_MAP.md` until the three stages below are complete. Do not ask the owner questions. Make conservative product decisions from the existing app patterns.

## Hard Rules

- Work in `/home/promonta/agent/miniapp-repo`.
- Before changing code, inspect the existing implementation and tests for the exact area.
- Keep commits small and logical.
- Never print secrets, tokens, auth files, SSH keys, `.env` values, or Telegram/OpenAI credentials.
- Do not run two agents against the same dirty worktree. If another lock/run is active, stop.
- If the same task fails twice with the same blocker, write a short blocker note in this file, commit it if appropriate, then move to another actionable task.
- Prefer existing architecture and helpers. Avoid large rewrites unless the local code already points that way.
- Use `rg` for search.
- Use patch-style edits for manual code changes.
- After each meaningful code change: run focused tests first, then the full available backend/frontend contract suite when practical.
- Before production deploy: commit and push.
- Deploy with `bash scripts/deploy.sh` from the server repo.
- After deploy: verify `curl -fsS https://app.promonta.fun/api/health`.
- Update `/home/promonta/agent/FILESYSTEM_MAP.md` with changed app structure and latest deployed SHA after deploys.
- Update `docs/CHANGELOG.md` and `docs/SESSION_HANDOFF.md` with concise notes.
- When all stages are genuinely done and deployed, change the first line to `AUTONOMOUS_STATUS: DONE`, commit, push, deploy, update the server map, then stop.

## Current Baseline

Latest known deployed SHA before this autonomous runner was installed: `4f23082`.

Recent completed work already includes:

- Unified photo/news comment bottom sheet behavior.
- Instagram-like dark comment composer and reply/delete ownership basics.
- Feed save hardening and saved filters per tab.
- AI composer visibility.
- Objects FAB/card polish.
- Kontrol day filter swipe guard.

Audit these before touching them again. Fix only remaining defects.

## Stage 1 - Finish UX/UI Polish And Broken Interaction Tails

Goal: the app should feel like a polished iPhone-style Telegram miniapp, with stable sheets, no flicker, and consistent Instagram-like action patterns.

Checklist:

- Feed photo cards should look and behave closer to Instagram: media-first, clean header/footer, consistent like/comment/share/save icons, counters, and no black/broken media blocks when data exists.
- Comments must be one shared system everywhere: photo, news, weather/info, object-related entries, and chat-adjacent threads where applicable.
- Comments must open as a bottom popup/sheet, not a separate tab, with reliable backdrop tap-to-close.
- Emoji quick reactions in comments must be tappable and visibly append/send or react without dead taps.
- Sending a comment must not create keyboard/input-bar flicker, grey artifacts, or a visual jump. Newly sent comments should remain visible and scroll into view.
- Workers can delete only their own comments; owners/admins keep appropriate moderation ability if already supported by roles.
- Save/bookmark post must work for photos, news, and weather posts.
- Feed filters must be per tab: Photo saved posts only in Photo, News saved posts only in News, Weather saved posts only in Weather. Do not mix photo/news/weather in one saved list.
- Rename `Инфо` tab to `Погода` if not already done, and keep tab typography consistent.
- Add/verify new counters for fresh photo/news/weather items if existing product model supports unread/new counts.
- Chat UI should share the polished dark composer/comment style where appropriate, without showing stale previous chat during chat switch.
- AI tab must keep a real text input/composer visible and usable.
- Objects cards should be Apple-like, calm, readable; add-object button should be correctly positioned with motion/reduced-motion support.
- Kontrol day top filter strip should horizontally scroll like a messages filter strip and never trigger tab switching while swiping inside it.

Expected tests:

- Existing frontend contract tests for feed photo, comments, save filters, chat actions, AI composer, objects, finish wizard, and swipe guards.
- Add missing tests only where a bug can regress.

## Stage 2 - Worker Start/Finish, Geolocation, Photos, Voice Text

Goal: workers should start and finish shifts with evidence and almost no typing friction.

Checklist:

- Start shift must capture geolocation at shift start. Backend should store lat/lon/accuracy/timestamp when available and reject or clearly mark missing location according to existing privacy/permission design.
- Finish shift must capture geolocation at finish.
- Finishing without photos must be impossible.
- Finish requires at least 2 photos from different angles. Prefer allowing more than 2. UI copy should be practical, not verbose.
- Finish flow should be a sequential wizard: photos first, then a separate additional-work text step, then per-item/summary/confirmation step according to existing data model.
- Additional-work text step should support voice input/transcription where possible. Use existing audio/transcription/AI endpoints if present; otherwise implement a clean backend placeholder contract plus UI affordance that can be wired to speech transcription.
- Add ability to send/share current geolocation inside chat as a message/action.
- Dashboard should clearly show what already works now: who is currently working, who has not started shift, and relevant active shift state.
- Add overdue tasks into alerts.
- Owner object details should keep object-specific controls and summary blocks inside the object card/detail context instead of scattered unrelated panels.

Expected tests:

- Backend tests for start location payload, finish location payload, finish photo minimum, chat location message, overdue alerts.
- Frontend contract tests for finish wizard steps, disabled finish until photo minimum/location state, voice input affordance, and chat location button.

## Stage 3 - Manager Operations, AI Voice Command, Broadcast

Goal: the owner/manager should have one fast operational cockpit.

Checklist:

- Add/verify a manager daily summary block with this shape:
  - Greeting by time of day.
  - Object count.
  - Worker count.
  - Count/list of workers who have not started.
  - Important alerts such as missing materials and delay risk.
  - Short "others ok" style summary when no more issues exist.
- Task confirmation flow:
  - Manager assigns a worker a task.
  - Worker can confirm/accept.
  - If there is no reaction after 2 hours, show yellow warning.
  - If no reaction after 4 hours, show red/unconfirmed alert.
- Add/verify overdue task alerts in the same operational surface.
- Add a voice management command entry point. The owner should be able to say/write:
  `Поставь Ивану завтра задачу закончить потолок у Мюллера и скажи ему взять лазер.`
  The AI/parser should extract:
  - object: Muller
  - worker: Ivan
  - date: tomorrow
  - task: finish ceiling
  - comment: take laser
- Prefer a safe draft/confirmation object first if automatic assignment could be risky.
- Add a central voice/action button if it fits existing navigation without visual clutter.
- Add quick broadcast controls: send one announcement to everyone on an object or the whole company.

Expected tests:

- Parser/unit tests for the Russian management command.
- Backend tests for task confirmation escalation at 2h/4h.
- Frontend contract tests for summary, central action/voice button, and broadcast controls.

## Final Definition Of Done

- All three stages implemented or explicitly documented as blocked with the smallest possible remaining manual decision.
- Full test suite passes on server.
- Changes committed and pushed to `main`.
- Production deployed and health endpoint OK.
- `/home/promonta/agent/FILESYSTEM_MAP.md` updated with new/changed files and latest deployed SHA.
- `docs/CHANGELOG.md` and `docs/SESSION_HANDOFF.md` updated.
- First line changed to `AUTONOMOUS_STATUS: DONE`.
