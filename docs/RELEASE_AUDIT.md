# Promonta Mini App — Release Audit

Дата: 2026-07-30
Аудит проведён на: `main` @ `f19f421a336c8cf0d2f50dc817684c5798cb5c28`
Production-сервис: `promonta-miniapp.service` (текущий деплой = f19f421, все файлы верифицированы md5sum-сверкой repo↔serving на момент последнего deploy)

Этот документ фиксирует фактическое состояние кода на момент аудита. Не опирается на старые отчёты/README — все выводы получены прямым чтением `backend/main.py` (5707 строк, 140 роутов), всех `backend/*_lib.py`, и untracked runtime-модулей на сервере.

---

## 1. Модули приложения — статус

| Модуль | Статус | Комментарий |
|---|---|---|
| Telegram auth (initData HMAC) | ✅ готов | Корректная HMAC-SHA256 схема, `hmac.compare_digest`, auth_date TTL 1ч. См. раздел 4. |
| Роли (Owner/Worker) + whitelist | ✅ готов | `roles.json` whitelist, неизвестный user_id → 403 + уведомление owner. |
| Объекты (CRUD, фото, документы) | ⚠️ требует исправления | Фото объекта отдаются без object-access проверки (см. P1-2). |
| Назначения (assignments) | ✅ готов | `can_access_object` учитывает только `accepted` статус; pending/declined корректно исключены. |
| Смены / Check-in (GPS, фото, паузы) | ✅ готов, но JSON не atomic | Ownership-проверки на всех routes корректны. `checkin_meta.json` пишется НЕ atomic (P1). |
| Инструменты | ✅ готов | Недавно полностью пересмотрен (return endpoint, holder_id, isolated tools_lib import). |
| Roadmap / этапы | ⚠️ требует ручной проверки | Осознанно open для всех workers (не object-scoped) — задокументированное решение владельца, но стоит явно зафиксировать в матрице прав. |
| Дефекты (Mängel) | ⚠️ требует исправления | `mangel_lib.py` вне git, non-atomic write (см. P1-1, P1-3). |
| Отсутствия (Abwesenheit) | ✅ готов | Ownership-проверки корректны. |
| Чат (группа/DM/threads/вложения) | ⚠️ требует исправления | Вложения без magic-byte проверки — P0. Unread-счётчики не проверялись в этом аудите (Этап 5 отдельно). |
| Профиль | ⚠️ требует ручной проверки | Аватар отдаётся без owner-check (см. P2-1) — вероятно by-design (полу-публичный, как user-card), но не задокументировано явно. |
| Feed (погода/новости/дни рождения/фото) | ✅ готов (by design открытый) | Все фото/комментарии доступны всем авторизованным — соответствует "общая лента компании". |
| Critical Alerts | ✅ готов | Ownership + basename-санитация на фото. |
| Dashboard/Alerts (owner-агрегаты) | ✅ готов | Все require_owner. |
| AI Chat | ✅ готов | Owner-only, кроме `/api/ai-chat/worker` (осознанно открыт всем). |
| Angebot/Rechnung (PDF) | ✅ готов | `require_angebot_access`. |

---

## 2. P0 — блокируют выпуск

### P0-1. Chat-вложения/голосовые/transcribe принимают любой файл без проверки содержимого

`POST /api/chat/messages/attachment` (main.py:3046), `POST /api/chat/messages/voice` (main.py:3161), `POST /api/transcribe` (main.py:3106) — единственная проверка: размер ≤8МБ. **Никакой magic-byte/allowlist проверки** (в отличие от `sniff_image()`/`sniff_image_or_pdf()`, уже используемых для аватаров/фото объектов/документов/feed/mangel/blocker-фото).

Расширение сохранённого файла берётся из `os.path.splitext(file.filename)` — клиентского значения. Файл `evil.html`/`evil.svg` сохранится с этим расширением и позже отдаётся через `FileResponse(path)` (main.py:3260) **без** `X-Content-Type-Options: nosniff` и без явного `Content-Disposition`. FastAPI/Starlette угадывает `Content-Type` по расширению → сохранённый `.html`/`.svg` отдастся как `text/html`/`image/svg+xml` и выполнится инлайн в Telegram WebView (Safari/Chrome-based) — реальный stored-XSS в контексте чата.

Дополнительно: `ext` из `os.path.splitext` не проверяется на управляющие символы — при специально сконструированном `file.filename` с `/`/`..` внутри имени (до последней точки) `ext` может содержать `/`, что теоретически ломает `os.path.join` в неожиданный путь (path-traversal риск, ниже вероятность эксплуатации чем XSS, но должно быть закрыто той же правкой).

### P0-2. Checkin `object_id` из клиента используется как сегмент пути без санитации

`POST /api/checkin/start` (main.py:4714) — `object_id` берётся из `Form`, обрезается `.strip()[:100]` (main.py:4754) и используется как каталог: `CHECKIN_PHOTO_BASE/{object_id}/{date_str}/`. Санитации от `../`/управляющих символов нет — только длина. Потенциальный path-traversal на запись файлов (фото check-in) вне предполагаемого дерева каталогов.

---

## 3. P1 — важно закрыть до широкого использования, не блокируют технически первый день

1. **`mangel_lib.py` полностью вне Git** (`/home/promonta/agent/mangel_lib.py`, аналогично `objekte_lib.py`) — тот же класс риска, что был у `tools_lib.py` до фикса: чистый checkout репозитория не воспроизводит рабочий backend, изменения на сервере не версионируются. Известный дубль-риск: по `server-structure.md` уже существует вторая **неиспользуемая** копия `mangel_lib.py` на диске — реальный источник путаницы при будущих правках.
2. **`checkin_meta.json`** (главный стор смен/GPS/фото) — `_save_checkin_meta` пишет `open(...,'w')+json.dump` напрямую, **не atomic** (main.py:4656-4658). RMW-race закрыт `_checkin_lock`, но crash посреди записи (systemctl restart, OOM-kill) оставит обрезанный JSON → следующий старт приложения не сможет прочитать сессии смен.
3. **`chat_messages.json` / `chat_messages_archive.json`** — оба non-atomic (main.py:2621-2622, 2603-2606). Тот же риск для истории чата.
4. **`mangel_tickets.json`** — non-atomic запись (4 места в mangel_lib.py), хотя RMW-race уже закрыт `_mangel_lock` (в отличие от первоначальной оценки одного из фоновых агентов — лок в файле присутствует).
5. **`GET /api/objects/{object_id}/image/file`** (main.py:995) — только `get_current_user`, без `require_object_access`. Любой авторизованный worker видит фото любого объекта независимо от назначения — несогласованно с сестринскими upload/delete на том же ресурсе (owner-only).
6. **`GET /api/objects/{object_id}/stages/{row_num}/roadmap/notes`** (main.py:4193) — в отличие от sibling `POST` того же ресурса (`require_object_access`), у `GET` нет проверки доступа к объекту вообще.
7. **`AI_MODEL_FILE`, rate-limit файл, alert_dismissals.json, weather/news/birthday reactions, roles.json, notified_users.json, worker_profiles.json, tasks.json, critical_alerts.json, abwesenheit.json, object_info.json** — все используют `_atomic_write_json`, но через отдельные load+save вызовы (не `update_json_transaction`) → RMW-race теоретически возможен при двух одновременных запросах на один и тот же файл (обновление профиля в 2 полях подряд, два владельца одновременно меняют роль и т.п.). Ниже приоритет чем P0/P1 выше, т.к. эти сценарии редки (мало одновременных owner-действий), но стоит закрыть системно там, где это дёшево.
8. **Critical-alert-resolve** (main.py:5418) пишет фото по пути `{alert_id}/{uuid}.ext` без `os.path.basename(alert_id)` на **write**-стороне (на read-стороне, main.py:5463, санитация есть) — `alert_id` перед этим проверяется через `_load_critical_alerts()`+ownership, что ограничивает практическую эксплуатируемость, но несогласованность стоит устранить.

---

## 4. P2 — можно отложить после запуска

1. `GET /api/profile/{user_id}/avatar` (main.py:665) — нет явной authz-проверки (любой авторизованный видит любой аватар по числовому ID). Вероятно by-design (аватар полу-публичен, как user-card), но не задокументировано явно нигде — стоит либо явно прокомментировать намерение в коде, либо добавить формальное решение в ENDPOINT_ACCESS_MATRIX.
2. Стилевая несогласованность: `GET/POST /api/ai-model`, `POST /api/ai-chat/upload` используют inline `if role != 'owner': raise 403` вместо `Depends(require_owner)` — функционально эквивалентно, но не единый паттерн.
3. Куча `.bak-*`/`.bak-pre-*` файлов закоммичены прямо в `backend/`/`frontend/` git-репозитория (16 `main.py.bak-*`, множество `app.html.bak-*`, `roadmap_lib.py.bak-*`) — замусоривают репозиторий, не несут ценности (git history уже хранит все версии). Кандидат на отдельный cleanup commit вне рамок текущего release.
4. `test_roadmap.py`/`test_owner_kt_requirements.py` и остальные тесты используют `unittest`, не `pytest`-фикстуры — не проблема, но стоит унифицировать при появлении CI, чтобы `pytest tests/` оставался единой точкой входа (уже так и есть де-факто, `pytest` умеет запускать `unittest.TestCase`).

---

## 5. Deployed SHA

На момент аудита: **`f19f421a336c8cf0d2f50dc817684c5798cb5c28`** — подтверждено сверкой md5sum между `git log -1` в `/home/promonta/agent/miniapp-repo` и реальными файлами в serving-путях (`/home/promonta/agent/miniapp/main.py`, `/home/promonta/agent/miniapp/tools_lib.py`, `/var/www/miniapp/*`) 30.07.2026. `git status --short` на сервере — чист.

---

## 6. Внешние зависимости

- **Google Sheets API** — OAuth refresh_token (`/home/promonta/agent/.sheets.json`), используется `objekte_lib.py` (объекты/этапы) и `tools_lib.py` (инструменты). Не service account — реальный refresh_token, единая точка отказа при истечении/отзыве.
- **Telegram Bot API** — `BOT_TOKEN` env var, используется для initData HMAC-валидации и отправки уведомлений (`send_telegram_message`).
- **Файловая система сервера** — все JSON-сторы, все загруженные файлы (фото/документы/голосовые) хранятся локально на VPS, не в объектном хранилище — единая точка отказа при заполнении диска или потере сервера.
- **systemd** — `promonta-miniapp.service`, `WorkingDirectory=/home/promonta/agent`, запускается как `uvicorn miniapp.main:app`.
- **Shared runtime-модули** (вне текущего репозитория, читаются с диска сервера в момент запроса):
  - `objekte_lib.py` — объекты/этапы, **вне git**.
  - `mangel_lib.py` — дефекты, **вне git**.
  - `tools_lib.py` / `roadmap_lib.py` — **в git** (`backend/tools_lib.py`, `backend/roadmap_lib.py`), также существуют идентичные copies на сервере (`/home/promonta/agent/tools_lib.py`, `/home/promonta/agent/roadmap_lib.py`) для совместимости/резервного пути импорта.
- **faster-whisper** — локальная модель транскрипции голосовых (CPU, int8), без внешнего API.
- **GLM / Claude API** — используется в `/api/ai-chat` (owner) и `/api/tasks/extract` (AI-извлечение потребностей из голосового).

---

## 7. Файлы и данные, существующие ТОЛЬКО на сервере (вне Git)

Полный список untracked путей на проде (`/home/promonta/agent/` и подкаталоги), критичных для работы приложения:

- `objekte_lib.py`, `mangel_lib.py` — **код**, не данные (см. п.6, требует переноса в git по аналогии с tools_lib.py).
- `roles.json`, `worker_profiles.json`, `notified_users.json` — учётные/профильные данные.
- `object_assignments.json`, `object_images.json`, `object_info.json` — данные по объектам.
- `checkin_meta.json` — все сессии смен (GPS, фото, часы).
- `abwesenheit.json` — отсутствия.
- `tasks.json`, `mangel_tickets.json`, `critical_alerts.json` — потребности/дефекты/алерты.
- `chat_messages.json`, `chat_messages_archive.json`, `chat_reads.json`, `chat_thread_meta.json`, `chat_reactions.json` — вся история чата.
- `roadmap.json`, `roadmap_stage_requests.json` — чек-листы этапов.
- `feed_photos.json`, `.news_feed.json`, weather/news/birthday reactions/read-файлы.
- `ai_model.json` — выбранная AI-модель.
- Каталоги загрузок: `avatars/`, `object_photos/`, `object_documents/`, `feed_photos/` (также используется для mangel-фото с префиксом `mangel_`), `chat_attachments/`, `blocker_photos/`, `checkin_photos/`, `transcribe_audio/`, `critical_alerts_photos` (или аналог).
- `.sheets.json` — Google OAuth credentials.
- `audit.log` — построчный JSON audit-лог всех запросов.
- Множество `.bak-*` файлов рабочих backup'ов от предыдущих ручных деплоев (не мусор для отката, но не версионируется).

---

## 8. Ограничения этого аудита

- Полная проверка Этапа 5 (chat unread-счётчики) не проводилась в рамках Этапа 0 — запланирована отдельно.
- UX/визуальная часть не проверялась — Safari MCP Bridge технически не подключается на этой машине (safari-helper не отвечает несмотря на переустановку пакета и корректный codesign identifier; вероятная причина — не выданное вручную разрешение Accessibility в System Settings, требует действия пользователя). Визуальный аудит (Этап 11) будет проведён через чтение кода экранов, без живого рендеринга, если это ограничение не снимется.
- CI/deploy-скрипты (`scripts/deploy.sh`) уже существуют в репозитории — Этап 7/8 должны свериться с реальным содержимым, не создавать заново с нуля.
- `docs/` уже содержит существенный объём документации (API.md, ARCHITECTURE.md, SECURITY.md, ROLES_AND_PERMISSIONS.md, TESTING.md и др.) — Этап 12 должен актуализировать, не переписывать с нуля.
