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

Уже проверено (TODO.md batch 2026-07-27, не повторять):
- `esc()` существует (`shared.js:55`), 131 использование.
- **FIXED (commit 87332ad)**: `checkin.js` AI-анализ (`resultEl.innerHTML = html`, было progress/materials/defects `.analysis` без esc) — добавлен `escMultiline()` helper (esc + newline→br), применён ко всем трём. Error path уже был экранирован, теперь и success path тоже.
- 20 файлов с `innerHTML`, нужен файл-за-файлом аудит (не сделан, checkin.js — единственный проверенный).
- CSS class whitelist — не существует нигде.
- Inline `onclick` с данными — ещё в: `app.html`(18), `home.js`(23), `feed.js`(8), `objects.js`(4), `abwesenheit.js`(4), `profile.js`(2), `chat.js`(2), `bubble-assign.js`/`tools.js`/`worker-checkin-fab.js`(1 each). Мигрировать по одному файлу.

Дополнительные конкретные места из владельческого списка: AI analysis в checkin (см. выше), stage names/status/object names, picker object/stage names, profile object history/skills, любые данные из Google Sheets, любые данные от user, любые данные от AI.

### A6. JSON storage
- `_atomic_write_json` (main.py:124) — **уже используется everywhere**, no direct `open(path,"w")` для JSON. FIXED, no action.
- JSONDecodeError handling — **FIXED (commit 062e88d)**. Добавлен `_safe_load_json(path, default)` рядом с `_atomic_write_json`, все 19 `_load_*` функций переведены на него (roles/notified_users/worker_profiles/assignments/object_images/alert_dismissals/object_info/weather_reactions/news_reactions/news_reads/birthday_alerts/photo_meta/chat/chat_reads/chat_thread_meta/tasks/checkin_meta/critical_alerts/abwesenheit). Corrupt JSON теперь логируется и деградирует к default вместо unhandled 500. `_load_notified_users` list→dict миграция сохранена поверх safe load.
- Locks для конкурентных записей — **уже есть**: `AUDIT_LOCK`, generic `_json_locks` dict, `_photo_lock`, `_chat_lock`, `_checkin_lock`. FIXED (покрывает 15-site deadlock из ранее смёрженной `fix/security-reliability-p1`).
- Path traversal: проверить все `os.path.join`/`Path(...)`/`open(...)`/`FileResponse`/`os.remove`/`shutil.*`, особенно с `object_id`/`user_id`/`thread_key`/`filename`/`document_id`/`defect_id`/`attachment_id`/`date`. Тестовые значения: `../`, `../../`, `%2e%2e/`, `..%2f`, abs path, unicode separators, длинные ID, dot-only. Создать `validate_object_id()`, `validate_entity_id()`, `safe_storage_path()`, `ensure_path_within_base()`, `sanitize_original_filename()`.

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

**Worker AI-чат не существует вообще** (тот же `role != 'owner'` полностью блокирует worker на `/api/ai-chat`). Owner отдельно попросил: worker'ам нужен **отдельный** узкий чат ("рабочие вопросы типа как сделать то или это"), без доступа к чувствительным данным фирмы, скорее всего GLM-only (не Claude CLI agent). Это НЕ security-fix, это новая product-фича — **не строить в рамках Фазы 01 (Security)**, вернуться к этому в PHASE B (Product flows) или отдельным заданием, когда владелец явно попросит.

### A9. Resource-level permissions (шире owner/worker)
Определить по каждому endpoint: unauthenticated / authenticated / owner / assigned worker / unassigned worker / creator / responsible worker / revoked user. Единый permission service (расширяет A1): `require_owner()`, `require_object_access()`, `require_object_assignment()`, `require_thread_access()`, `require_document_access()`, `require_defect_access()`, `require_shift_access()`. Проверить: нельзя удалить/понизить последнего owner, revoked user не остаётся active worker, role change логируется.

### A10. Check-in / shifts инварианты
Одна active shift на user; finish только для active shift; idempotency scope `user + operation + key`; photos принадлежат shift; object существует; worker имеет доступ; время в UTC, UI показывает Europe/Berlin. Concurrency test: много параллельных start requests → ровно одна active shift. State machine: DRAFT → STARTING → ACTIVE → FINISHING → COMPLETED (+ CORRECTION_REQUIRED, CANCELLED).

### A11. CSV/formula injection
Значения начинающиеся с `=`, `+`, `-`, `@` не должны исполняться как spreadsheet formula при экспорте. Использовать стандартный `csv` module, не ручную сборку строк.

### A12. Google Sheets sync failures
Найти `try: sync() except Exception: pass` паттерны — silent failure недопустим для owner-важных операций. Owner должен видеть sync error, даже если полноценный outbox пока не строится.

---

