# Plan phases index

Единый owner-план (6 ТЗ от 2026-07-27), разбит на 10 файлов, чтобы обрабатывать по одному и не держать весь контекст в памяти сразу.

| # | Файл | Тема | Порядок выполнения |
|---|---|---|---|
| 01 | `01-security-permissions-and-data.md` | Object-level permissions, geo required, min-2-photos, XSS, JSON/uploads, AI subprocess, path traversal | **1st — начинаем здесь** |
| 02 | `02-product-flows-worker.md` | Start/active shift, finish-shift wizard, voice input, dashboard, object card for owner | 2nd |
| 03 | `03-product-flows-needs-defects-tasks-chat.md` | Needs/Defects/Tasks workflows, chat data logic (thread_key, unread, polling) | 3rd |
| 04 | `04-telegram-ui-navigation.md` | Telegram safe-area, viewport controller, navigation single-source-of-truth, screen lifecycle | 4th |
| 05 | `05-design-system.md` | Design tokens, typography, Home/Profile/Calendar/Bubble Assignment | 5th |
| 06 | `06-chat-hub-rebuild.md` | Chat Hub full rebuild (dark theme, search, tabs, direct threads, reactions) | 6th |
| 07 | `07-object-card-rebuild.md` | Object Card full rebuild (ski-resort reference composition) | 7th |
| 08 | `08-radio-player-rebuild.md` | Radio player full rebuild (HomeRadioPlayer + RadioMiniPlayer) | 8th |
| 09 | `09-architecture-split.md` | Backend/frontend modular split, API client, UI states, offline queue | 9th (parallel-friendly) |
| 10 | `10-tests-docs-final.md` | Test infrastructure, E2E flows, visual regression, endpoint audit table, docs update | 10th (tests written alongside each phase, this is the catch-all/final pass) |

Правила работы (все 6 исходных ТЗ согласны):
- Маленькие логические блоки, отдельный коммит на каждый.
- После блока: `python3 -m py_compile backend/main.py` + `node --check frontend/js/*.js`.
- Верифицировать по реальному коду перед стартом каждого пункта, не доверять документации.
- Не ломать текущие route names/API без необходимости.
- Не переписывать с нуля, не мигрировать на React/новую БД без отдельного согласования.
- Bubble Assignment — сохранить.
- DSGVO/юридический compliance — вне скоупа.
- Не деплоить без явного разрешения на каждый раз.
- Не заявлять "проверено на iPhone" без реальной физической проверки.

Загружать в контекст только текущий файл фазы, не все 10 сразу.
