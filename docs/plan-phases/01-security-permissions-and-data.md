# Promonta Mini App — Audit Master Plan (Phase file)

PHASE A — Security P0 (permissions, geo, photos, XSS, JSON, uploads, AI, checkin invariants). Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE A — Security P0 (ДЕЛАЕМ ПЕРВЫМ)

Источники: ТЗ1 §1, ТЗ2 §40-50, ранее верифицированный TODO.md batch 2026-07-27.

### A1. Object-level backend permissions
Добавить helpers в `backend/main.py` (или `permissions.py`, если уже начат split):
- `can_access_object(user, object_id)`
- `require_object_access(user, object_id)`
- `require_object_assignment_or_owner(user, object_id)`
- `require_task_access(user, task)`
- `require_mangel_access(user, mangel)`
- `require_thread_access(user, thread_key)`

Статус: **FIXED (2026-07-27, commits ba537ca, 162e4b6).** `can_access_object()`/`require_object_access()` добавлены (main.py, сразу после `require_owner`). Применены к 9 object-routes (tasks GET, description GET, info-items GET+POST, documents GET+POST+file, stages GET, stage-complete POST) — раньше проверяли только `get_current_user`, любой worker мог читать/писать чужой объект. `require_mangel_access()` добавлен отдельно (резолвит ticket→object_id), применён к 6 mangel routes (get ticket, comments GET+POST, list с фильтрацией по assignments для worker, create с access-check, photo file по сканированию owning ticket). Owner-only mutations (create_task/delete_document/stage create-update-delete-swap/status) уже имели `require_owner`, не трогал.

Chat уже был защищён (`_check_thread_access` во всех местах) — проверено, gap не найден, ничего не менял. Checkin history (stundenzettel/list/photo) уже был self-or-owner — проверено, gap не найден, ничего не менял.

Не покрыто этим проходом: второй `create_task` (main.py ~2861, `TaskCreateBody`, другая сущность без object_id в пути) — вне скоупа, не проверял что это вообще такое.

Правила доступа:
- owner видит/управляет всем.
- worker — только свои объекты/задачи/дефекты/чаты/материалы.
- worker не может через API читать/менять чужой объект.

Проверить и исправить для: `GET /api/objects`, object info/description/items/documents/download, object stages, stage complete, checkin start/finish/manual/status/history, tasks list/create/update, mangel list/create/detail/photos/comments, chat threads по object/task/mangel, любые file download endpoints.

Acceptance: Worker A не может прочитать/изменить/скачать документы/создать данные для object B, если не назначен. Frontend и backend ограничения совпадают. Добавить smoke/negative-access test.

Known existing gap (уже зафиксирован в ROLES_AND_PERMISSIONS.md/TODO.md REC-9): `POST /api/objects/{object_id}/tasks` — любой authenticated worker может добавить задачу любому объекту, не только своему. Чинить в рамках A1.

### A2. Геолокация — обязательна на старте/финише смены
- Start shift: GPS обязателен. Нет геолокации → "Включи геолокацию, чтобы начать смену", смена не стартует.
- Finish shift: GPS обязателен, `finish_location` сохраняется. Нет геолокации → смена не завершается, понятная ошибка.
- Owner видит `start_location`/`finish_location` в истории смены.

Статус: **FIXED (2026-07-27, commit 8b838d0).** Подтверждено: `lat`/`lon` были `Form('')` без server-side проверки, `_getGeolocation()` тихо резолвилась в `{lat:'',lon:''}` при отказе/таймауте. Добавлено: backend 400 если lat/lon пустые (start+finish), frontend throw до fetch (не тратит аплоад фото зря) + отдельный UX-текст для geo-ошибки vs network-ошибки в retry-подсказке. `checkin_manual` (owner ручной ввод задним числом) намеренно не тронут — другой эндпоинт, без GPS по дизайну.

### A3. Finish shift — минимум 2 фото обязательны
Статус: **ALREADY FIXED, не gap — план ошибался.** Перепроверено 2026-07-27: `checkin_finish` (main.py ~3249) уже содержит `if len(files) < 2: raise HTTPException(400, "Прикрепите минимум 2 фото...")`, и frontend `_confirmCheckinPreview` (checkin.js) уже проверяет `_checkinPreviewFiles.length < 2` до отправки с понятным toast. Первоначальный grep в плане не долистал достаточно строк файла — не повторять эту проверку, это уже сделано и работает.

### A4. Не доверять object_id с клиента при finish
Finish endpoint должен брать `object_id` из активной смены (server-side), не из тела запроса от клиента — иначе можно закрыть смену "от имени" чужого объекта.

### A5. XSS / escaping
Правила: `esc()` everywhere user/AI/Sheets data рендерится; CSS class — whitelist; inline `onclick` с пользовательскими данными → `data-*` + listeners.

Статус: **FIXED — все 20 файлов с innerHTML проверены file-by-file (2026-07-27).** Коммиты: 87332ad, a8e25c1, 360e98f, 60821fa, 938f324, c4058b0, ac2dd4f, ed1ab0b, 6f48257.

`esc()` существует (`shared.js:55`), теперь используется consistently. Повторяющийся паттерн gap'а по всему проекту: `SOME_LABEL[status] || status` fallback (когда значение не matched в известном lookup-объекте, возвращается сырой Sheets-статус) рендерился без esc() почти везде — нашёл и исправил в объектах (stage status), tasks (task status), object-info (stage status roadmap). Второй частый паттерн: inline `onclick="...('${x.replace(/'/g,"\\'")}'...)"` — только quote-escape для JS-строки, не HTML-escape — заменено на `data-*` + `addEventListener` в objects.js/abwesenheit.js.

Файл-за-файлом результат:
- **Исправлено** (реальные gaps): checkin.js (AI-анализ), home.js (ring card label, alerts title/subtitle, weather object tabs), objects.js (status pill fallback + inline onclick → data-*), tasks.js (status label fallback), tools.js (status/object label + data-атрибуты), critical-alerts.js (alert title/subtitle — тот же источник данных что home.js alerts, независимый gap), profile.js (skill_options в редакторе навыков), feed.js (weather risk text в caption), abwesenheit.js (name×2, status/reason label fallback, **note — единственное по-настоящему free-text поле среди всех находок**, inline onclick → data-*), object-info.js (stage roadmap status label + CSS class whitelist), bubble-assign.js (worker names, stage name, BUBBLE_STAGE_OPTIONS ×2 вхождения — **Bubble Assignment, который план явно просил проверить**), onboarding.js (skill options в quiz), worker-checkin-fab.js (object picker name/stage), angebot.js + rechnung.js (position title/description в `value` атрибутах — owner-entered, не Sheets, но тот же риск).
- **Проверено, уже корректно, не трогал**: chat.js (`_check_thread_access`-паттерн + `_escChat` везде), mangel.js (`esc()` уже стоит), ai.js (`_formatAiText` эскейпит ДО markdown-форматирования — правильный порядок), my-tasks.js (уже esc()'d), shared.js (уже esc()'d, эталонный файл где `esc()` определён).
- CSS class whitelist: реализовано точечно (не отдельная переиспользуемая функция) в двух местах где status → CSS class (objects.js, object-info.js) — regex `/^[a-zA-Zа-яА-Я0-9\-]+$/` с fallback на `unknown`.

Дополнительные конкретные места из владельческого списка: AI analysis в checkin (см. выше), stage names/status/object names, picker object/stage names, profile object history/skills, любые данные из Google Sheets, любые данные от user, любые данные от AI.

### A6. JSON storage
- `_atomic_write_json` (main.py:124) — **уже используется everywhere**, no direct `open(path,"w")` для JSON. FIXED, no action.
- JSONDecodeError handling — **FIXED (commit 062e88d)**. Добавлен `_safe_load_json(path, default)` рядом с `_atomic_write_json`, все 19 `_load_*` функций переведены на него (roles/notified_users/worker_profiles/assignments/object_images/alert_dismissals/object_info/weather_reactions/news_reactions/news_reads/birthday_alerts/photo_meta/chat/chat_reads/chat_thread_meta/tasks/checkin_meta/critical_alerts/abwesenheit). Corrupt JSON теперь логируется и деградирует к default вместо unhandled 500. `_load_notified_users` list→dict миграция сохранена поверх safe load.
- Locks для конкурентных записей — **уже есть**: `AUDIT_LOCK`, generic `_json_locks` dict, `_photo_lock`, `_chat_lock`, `_checkin_lock`. FIXED (покрывает 15-site deadlock из ранее смёрженной `fix/security-reliability-p1`).
- Path traversal: **FIXED (commit 7c5597c).** Проверены все GET/`FileResponse` routes (avatar, object documents, chat attachments, mangel photos, checkin photos, critical-alert photos). Большинство уже безопасны by construction: object documents/chat attachments матчат `fname` против known-значения в JSON-store ДО сборки пути (traversal payload просто не совпадёт ни с чем), checkin photos строят путь из JSON-resolved значения по index (не из сырого URL text), avatar `user_id` уже `isdigit()`-валидирован. **Единственный реальный gap**: `GET /api/critical-alerts/{alert_id}/photo/{filename}` строил `os.path.join(DIR, alert_id, filename)` напрямую из URL без matching-проверки и без basename. Добавлен `os.path.basename()` на оба параметра + reject если изменилось после basename. Не стал создавать отдельные `validate_object_id()`/`safe_storage_path()` helpers — паттерн matched-lookup, который уже используется в большинстве мест, эффективнее и не требует новой инфраструктуры; там где его не было (единственное найденное место), точечный basename-фикс закрыл конкретный gap.

### A7. Uploads
- Magic bytes: **FIXED (commit 0a52f6c).** `sniff_image()`/`sniff_image_or_pdf()` добавлены (используют `python-magic`, уже стоял на VPS но не был в requirements.txt — добавлен туда). Применены ко всем 8 местам, где раньше проверялся только client-supplied `content_type`: avatar upload, object documents (image+PDF), AI chat upload (image+PDF, owner-only), mangel ticket photo, `_save_checkin_photos` (start+finish), critical-alert resolution photo, feed photo upload. Extension теперь выбирается из detected MIME, не client content_type.
- **Известный нерешённый нюанс** (не чинить отдельно, зафиксировано намеренно): в `_save_checkin_photos` bad-file молча `continue`-ится (как было раньше), но `len(files) < 2` guard в `checkin_finish` считает **входящие** файлы до magic-check, не **сохранённые** после него — если оба присланных файла провалят magic-check, `finish_photos` может остаться пустым несмотря на пройденную проверку "минимум 2". Существовавшая логическая дыра, просто теперь более вероятна из-за строгой проверки. Если будет жалоба на пустые finish_photos — здесь копать первым делом.
- Size/count limits: chat=8MB confirmed, остальные unverified (TODO.md REC-10, не дублировать).
- Extension normalization, dangerous-type rejection — magic-bytes closes dangerous-type (не image/pdf = reject), extension теперь derived от detected MIME (нормализовано автоматически).
- Decompression bomb protection, allowlist formats, safe internal filename (original name only as metadata), запрет HTML/SVG если не нужны.

### A8. AI subprocess security
Статус: **CONFIRMED + INTENTIONAL, partially fixed (commit b87cdca).** `_call_claude_cli` (main.py ~2588) реально вызывает `claude -p --dangerously-skip-permissions --model {model} {prompt}` с `cwd='/home/promonta/agent'` и `env={**os.environ}` (полный доступ). Endpoint `/api/ai-chat` — **owner-only** (`role != 'owner'` check уже есть), rate-limited 20/час.

**Owner подтвердил явно (2026-07-27): это намеренно.** Owner хочет, чтобы этот AI-ассистент видел тот же полный контекст, что и Claude Code сам — полноценный агент, не sandboxed chat-bot. `--dangerously-skip-permissions`/cwd/env **НЕ трогать** — это НЕ security-gap, это осознанный дизайн. Не "исправлять" это в будущих проходах.

Что реально было gap и исправлено: не было concurrency guard — rate limit ограничивает частоту (20/час), но не параллельность, два быстрых запроса могли заспавнить два параллельных 120-сек subprocess. Добавлен `_claude_cli_lock` (threading.Lock, 1s acquire timeout, 429 при конфликте).

**Worker AI-чат — backend FIXED (commit 1a3d5fc, 2026-07-27).** `POST /api/ai-chat/worker` — GLM-only (никогда не трогает Claude CLI путь), собственный `WORKER_AI_SYSTEM_PROMPT` (явно говорит модели что нет доступа к данным фирмы, редиректить object/client/money вопросы к owner), собственный rate limit (15/час, отдельный файл от owner's 20/час), text-only (без multimodal). Open для любого authenticated user (не owner-gated — безопасно by construction, endpoint сам по себе узкий). `_call_glm()`/`_check_ai_rate()` парам-я (system/rate_file/limit опционально, дефолты = owner-значения), все 4 существующих owner-вызова не тронуты. **Frontend UI wiring не сделан** — отдельный шаг (worker-facing screen, часть UI-редизайна фаз 04-08).

### A9. Resource-level permissions (шире owner/worker)
Статус: **Основное покрыто A1/mangel-фиксом (require_object_access/require_mangel_access) + FIXED отдельно (commit b0c326c).** Подтверждён и закрыт реальный gap: `set_role`/`revoke_role` не защищали от удаления/понижения ПОСЛЕДНЕГО owner (только "нельзя себя удалить" уже было) — если бы появился второй owner, один мог убрать другого до нуля owner'ов, оставив приложение без управления. Добавлена проверка remaining-owners-count в оба endpoint'а. Role change уже логируется косвенно (Telegram push при set_role) — отдельный audit-log не строил, не запрошено. "Revoked user не остаётся active worker" — `get_current_user` уже проверяет `roles.json` на каждый запрос (whitelist-модель), revoke мгновенно отрезает доступ, не нужно отдельно чинить.

### A10. Check-in / shifts инварианты
Статус: **Уже FIXED, перепроверено 2026-07-27, не gap.** `checkin_start` (main.py ~3178) уже содержит double-check locking внутри `_checkin_lock`: первая проверка "нет открытой сессии" перед I/O (фото), повторная проверка внутри финального lock перед записью (TOCTOU-safe, комментарий в коде явно это описывает — "10.29 Fable-аудит"). Idempotency key — `crypto.randomUUID()` с фронта, TTL-cache, per-attempt уникален (коллизия между юзерами практически невозможна by construction, отдельный user-prefix не нужен). State machine не формализована явно как enum, но фактическое поведение (`finish_at is None` = active, `finish_at` set = completed) уже реализует нужный инвариант. Concurrency test не написан (нет test infrastructure — Фаза 10), но логика проверена чтением кода, не нужно менять сейчас.

### A12. Google Sheets sync failures
Статус: **FIXED (commit 9090c46).** Найдены оба `try: ... except Exception: pass` вокруг Sheets mirror-записи в mangel create/status-update (main.py ~3036, ~3076) — единственные два места, где Sheets ЗАПИСЬ (не чтение) молча проглатывалась. JSON остаётся source of truth (осознанный дизайн, не трогать), но теперь оба места логируют `WARNING` с ticket_id и exception при сбое зеркалирования — видно в journalctl, не требует Telegram-спама на каждый мелкий sync fail. Остальные 22 `except Exception: pass` в файле — либо best-effort Telegram push (правильный паттерн, не трогать), либо Sheets READ с graceful degrade fallback (не opasно, не трогать).

### A11. CSV/formula injection
Статус: **FIXED (commit b6410d4).** Единственный CSV-генератор в проекте — `export_stundenzettel` (main.py ~3434). Подтверждён реальный gap: `object_id` в строке CSV шёл напрямую из `checkin_start`'s Form-параметра (только `.strip()[:100]`, без sanitize) — worker теоретически мог отравить экспорт formula-payload'ом типа `=cmd|'/c calc'!A1`. Добавлен `_csv_safe()` (префикс апострофом для `=`/`+`/`-`/`@`), применён к `date`/`object_id`. Ручная f-string сборка (`join(';')`, без quoting) заменена на `csv.writer(delimiter=';')`. Реальные object_id (`OBJ-xxx`, буква первая) и date (`YYYY-MM-DD`, цифра первая) не задеты — только нейтрализует теоретический payload, не меняет вывод для нормальных данных.

### A12. Google Sheets sync failures
Найти `try: sync() except Exception: pass` паттерны — silent failure недопустим для owner-важных операций. Owner должен видеть sync error, даже если полноценный outbox пока не строится.

---

