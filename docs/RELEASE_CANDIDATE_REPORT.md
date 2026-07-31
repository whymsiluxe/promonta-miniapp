# Release Candidate Report — 0.9.0-rc1

Дата: 2026-07-31. Промonta Mini App — release-readiness pass (14 этапов) перед
переходом в ежедневное использование командой.

## Итоговый SHA

`7edb9f61f63b12435cce86a37a5b4c7076ca3622` (main)

## Все commits этой финализации

| SHA | Commit message |
|---|---|
| `f118987` | docs: add full release audit (P0/P1/P2 findings, external deps, untracked prod files) |
| `86c9e52` | security: harden uploads and chat attachments |
| `0577361` | reliability: make runtime JSON storage atomic, track mangel_lib.py in git |
| `33fe7c7` | security: enforce endpoint and object access rules, add access matrix |
| `ec14796` | fix: correct unread counters across chat threads |
| `abb9c4c` | ops: add versioned health and safer diagnostics |
| `7e1b123` | ops: add reproducible deploy and rollback scripts |
| `cca7bba` | ops: document and automate backup recovery |
| `1e69145` | docs: document personal data handling |
| `ea4e366` | docs: prepare release documentation and checklist |
| `7edb9f6` | fix: final Telegram WebView UX polish |

**Не запушено** (готово в рабочем дереве, блокировано правами GitHub-токена):
`.github/workflows/ci.yml`, `requirements-test.txt` — см. "Unresolved issues" ниже.

*(Примечание: коммиты `33fe7c7`/`0577361` в этом отчёте объединяют работу,
описанную в чате отдельными сообщениями по мере выполнения Этапов 2-3 —
итоговый список выше это то, что реально в `git log` на момент отчёта.)*

## Изменённые файлы (по всей финализации)

- `backend/main.py` — upload validation, atomic writes, access fixes, health/version endpoints, chat unread fix.
- `backend/mangel_lib.py` — новый в git (был untracked), atomic write.
- `backend/tools_lib.py`, `backend/roadmap_lib.py` — уже были в git с прошлой сессии, не изменены в этом пассе.
- `tests/test_upload_security.py`, `tests/test_atomic_storage.py`, `tests/test_chat_unread.py`, `tests/test_health.py` — новые.
- `docs/RELEASE_AUDIT.md`, `docs/ENDPOINT_ACCESS_MATRIX.md`, `docs/BACKUP_AND_RECOVERY.md`, `docs/DATA_PROTECTION.md`, `docs/RELEASE_CHECKLIST.md` — новые.
- `docs/PROJECT_STATE.md`, `docs/FEATURES.md`, `docs/TESTING.md`, `README.md` — обновлены.
- `scripts/deploy.sh` (расширен), `scripts/rollback.sh`, `scripts/cleanup_rollback_backups.sh` — новые/расширенные.
- `frontend/js/{mangel,feed,object-info,tasks,objects,abwesenheit,profile}.js`, `frontend/app.html` — UX-фиксы (double-submit guards, loading/error states, safe-area).
- `.github/workflows/ci.yml`, `requirements-test.txt` — написаны, не запушены (см. ниже).

## P0 закрыто

1. **Chat-вложения/голосовые/transcribe без magic-byte проверки** — принимали любой файл, только size limit. Реальный stored-XSS через `.html`/`.svg`, отдаваемый без `nosniff`. Закрыто: allowlist по реальному содержимому файла, расширение только из фиксированной таблицы, `nosniff` на serving-эндпоинте.
2. **Checkin object_id path-traversal** — клиентский Form-параметр использовался как сегмент пути без санитации от `../`. Закрыто: `os.path.basename()`.

## P1 закрыто

1. `mangel_lib.py` перенесён в git (был полностью вне репозитория, тот же класс риска что чинили для `tools_lib.py`).
2. `checkin_meta.json`, `chat_messages.json`, `chat_messages_archive.json`, `mangel_tickets.json` — переведены на atomic write (temp-file + `os.replace`).
3. `GET /api/objects/{object_id}/image/file` и `GET .../roadmap/notes` — несогласованные access-проверки относительно sibling routes, закрыто.
4. Chat unread-счётчик мис-атрибуция thread-scoped сообщений в общий group-счётчик — закрыто.
5. Health/version/readiness endpoints добавлены.
6. Deploy/rollback скрипты с полным pre-flight/backup/health-check циклом.

## P2 — оставшееся (не блокирует выпуск)

- `objekte_lib.py` всё ещё вне git (тот же класс риска, не исправлен в этом пассе — отдельная задача).
- 75+ старых `.bak-*` файлов замусоривают репозиторий (не функциональная проблема).
- Несогласованный стиль owner-check (inline `if role != 'owner'` vs `Depends(require_owner)`) в нескольких местах — не унифицировано.
- `Finding #11` из UX-аудита (skills-edit toggle double-submit) — низкий приоритет, не закрыт в этом пассе.
- Полу-публичный avatar endpoint без явного design-комментария в коде.

## Тесты

**151 passed, 0 failed.** Полностью offline (mocked dependencies, `BOT_TOKEN`
может быть любой строкой). 9 test-файлов, покрывают: upload security, atomic
storage, access patterns, chat unread, tools checkout/return, health endpoints.

## Syntax-check

- Python: `python3 -m py_compile backend/*.py` — чисто.
- JS: `node --check` на всех `frontend/js/*.js` — чисто.

## CI

Workflow (`.github/workflows/ci.yml`) написан и **вручную верифицирован
шаг-за-шагом на сервере** (151 тестов, main.py импортируется, JS чист, нет
merge-конфликт маркеров, нет секретов, обязательные файлы на месте) — но **не
запушен на GitHub**. Причина: OAuth-токен, использованный для push, не имеет
scope `workflow`, требуемого GitHub для создания/обновления файлов в
`.github/workflows/`. Push с этим файлом был явно отклонён GitHub (`refusing
to allow an OAuth App to create or update workflow ... without workflow
scope`). Требуется либо токен с этим scope, либо ручной push человеком с
соответствующими правами.

## Security audit

Полный отчёт: `docs/RELEASE_AUDIT.md`. Итог: 2 P0 закрыто (upload validation,
path traversal), несколько P1 закрыто (см. выше), access matrix
задокументирована (`docs/ENDPOINT_ACCESS_MATRIX.md`) с explicit-флагами для
намеренно широких (не багов) паттернов доступа — "любой worker видит любой
объект/дефект" по решению владельца, задокументировано, не переделано.

## Access matrix coverage

`docs/ENDPOINT_ACCESS_MATRIX.md` покрывает все 140 routes из `main.py` —
метод, назначение, owner/worker доступ, object-scoping, тестовое покрытие.
Несколько несогласованностей найдено и закрыто в этом пассе (см. P1 выше).

## JSON storage audit

Полный список сторов и их atomicity-статус — `docs/RELEASE_AUDIT.md` раздел
"JSON File Stores". Критичные сторы (checkin/chat/mangel) теперь atomic;
несколько менее критичных (roles/profiles/tasks и др.) используют
`_atomic_write_json` за отдельными load+save вызовами (не
`update_json_transaction`) — теоретический RMW-race при одновременных owner-
действиях остаётся, низкий практический риск (редкие одновременные owner-
операции на один и тот же файл), не закрыто системно в этом пассе.

## Upload audit

Полный отчёт — `docs/RELEASE_AUDIT.md` раздел "Upload Endpoints". Все 13
upload-эндпоинтов теперь либо уже использовали magic-byte allowlist
(avatar/object-photo/document/feed/mangel/blocker — не менялись), либо
получили его в этом пассе (chat attachment/voice/transcribe).

## Health/version

`GET /api/health` — status/service/version/commit/time, unauthenticated,
без секретов. `GET /api/health/ready` — owner-only, дешёвые filesystem-
проверки (storage/uploads/tools_lib/mangel_lib/roles.json).

## Deploy/rollback status

`scripts/deploy.sh` расширен до 12-шагового pre-flight+backup+deploy+health-
check цикла, `scripts/rollback.sh` и `scripts/cleanup_rollback_backups.sh`
написаны. **Ни разу не запускались против production в рамках этого пасса** —
только `bash -n` syntax-check и построчная логическая проверка. Требуется
отдельное явное подтверждение перед первым реальным запуском.

## Backup status

Существующий `promonta-backup.timer`/`.service` (ежедневно 03:00, весь
`/home/promonta/agent`, retention 14 копий, Mac→iCloud) подтверждён рабочим
и задокументирован в `docs/BACKUP_AND_RECOVERY.md`. Новый
`scripts/cleanup_rollback_backups.sh` протестирован на реальном единственном
backup — работает корректно.

## Documentation status

README.md, docs/TESTING.md, docs/PROJECT_STATE.md, docs/FEATURES.md
актуализированы под текущий код. Новые: RELEASE_AUDIT.md,
ENDPOINT_ACCESS_MATRIX.md, BACKUP_AND_RECOVERY.md, DATA_PROTECTION.md,
RELEASE_CHECKLIST.md, этот отчёт.

## Git status --short

```
?? .github/workflows/
?? requirements-test.txt
```

(untracked — ждут push с правильным токеном, см. "Unresolved issues")

## Deploy не выполнялся

Подтверждаю явно: ни один из commits этого release-readiness пасса **не был
задеплоен на production**. Serving-пути (`/home/promonta/agent/miniapp/`,
`/var/www/miniapp/`) не трогались с момента предыдущего деплоя (commit
`f19f421`, тот же коммит что задокументирован как "текущий production" в
начале этого пасса). Все изменения существуют только в git-репозитории на
сервере (`/home/promonta/agent/miniapp-repo`) и на GitHub.

## Unresolved issues (не скрыто)

1. **CI не запушен** — блокировано GitHub OAuth scope. Требует действия
   пользователя.
2. **Живая Telegram E2E-проверка не выполнена** — Safari MCP browser
   automation не функционирует в этом окружении (`safari-helper` не
   отвечает на вызовы кроме `list_tabs`; переустановка npm-пакета и
   codesign-исправление не помогли; вероятная причина — недостающее
   разрешение macOS Accessibility, требующее ручного клика в System
   Settings, не скриптуемо). Точный план ручной проверки — ниже.
3. **`objekte_lib.py` всё ещё вне git** — не исправлено в этом пассе.
4. **Production deploy не выполнялся** — требует отдельного подтверждения.
5. Несколько P2-пунктов из `docs/RELEASE_AUDIT.md` не закрыты (см. раздел
   "P2 — оставшееся" выше) — намеренно, низкий приоритет.

## Точный план финального production deploy

1. Получить/настроить GitHub-токен со scope `workflow`, запушить
   `.github/workflows/ci.yml` + `requirements-test.txt` (или запушить
   вручную с достаточными правами).
2. Дождаться зелёного CI на GitHub для подтверждения (сейчас проверено
   только вручную на сервере).
3. Выполнить живую Telegram E2E-проверку по сценарию ниже.
4. Только после (1)-(3): получить явное подтверждение пользователя на
   production deploy.
5. Запустить `scripts/deploy.sh` (создаёт backup автоматически, полный
   pre-flight, останавливается на первой ошибке).
6. Проверить `GET https://app.promonta.fun/api/health` — `commit` совпадает
   с задеплоенным SHA.
7. Проверить `/api/health/ready` изнутри приложения как owner.
8. Пройти `docs/RELEASE_CHECKLIST.md` целиком (Worker/Owner/cross-worker
   сценарии).
9. Если что-то не так — `scripts/rollback.sh <backup-dir>` (путь печатается
   `deploy.sh` в конце).

## Требует ручной Telegram-проверки (сценарий)

См. `docs/RELEASE_CHECKLIST.md` полностью — короткая версия:

**Owner**: dashboard, Команда (Сводка+План), назначение работника, одобрение/
отклонение отсутствия, смена статуса дефекта, управление инструментом
(назначить конкретному worker через picker, освободить — confirm holder/
holderId/object все очищаются вместе), критичный алерт, чат (unread badges).

**Worker A**: вход, назначенный объект, принятие назначения, старт смены
(GPS+фото обязательны), пауза, финиш смены (≥2 фото), чат (текст+фото+
голосовое), дефект с фото, потребность, отсутствие, взять свободный инструмент
(имя автоподставляется, ручного поля нет), вернуть свой инструмент.

**Worker B**: не может менять смену A, не может вернуть инструмент A, не
может открыть Owner-only действия, видит только разрешённые объекты/чаты.

**Не считать этот E2E выполненным без реального Telegram WebView** — код-
ревью и автотесты (проведённые в этом пассе) не заменяют его.
