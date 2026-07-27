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

Статус: **CONFIRMED — ни один helper не существует.** Проверено `grep -n 'def can_access_object\|def require_object_access\|def require_object_assignment\|def require_task_access\|def require_mangel_access\|def require_thread_access'` — пусто. Только `get_current_user` (main.py:204) и `get_role` (main.py:216) существуют.

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

Статус: **UNVERIFIED**, требует явной проверки. `_gps_suspect()` (main.py:340) существует для валидации подозрительных координат, но не подтверждено, что сами координаты required (не Optional) в сигнатурах `checkin_start` (main.py:3108) / `checkin_finish` (main.py:3221). Проверить перед фиксом.

### A3. Finish shift — минимум 2 фото обязательны
Статус: **CONFIRMED GAP.** `_save_checkin_photos` (main.py:49) проверяет только `len(raw) > CHECKIN_MAX_BYTES` per file — нет проверки `len(photos) >= 2`. Добавить explicit проверку в `checkin_finish`.

Frontend: нельзя перейти дальше шага фото в finish-wizard, если фото < 2. UX-текст: "Сделай минимум 2 фото с разных ракурсов. Лучше 3-5 фото." Превью, удаление/пересъёмка.

### A4. Не доверять object_id с клиента при finish
Finish endpoint должен брать `object_id` из активной смены (server-side), не из тела запроса от клиента — иначе можно закрыть смену "от имени" чужого объекта.

### A5. XSS / escaping
Правила: `esc()` everywhere user/AI/Sheets data рендерится; CSS class — whitelist; inline `onclick` с пользовательскими данными → `data-*` + listeners.

Уже проверено (TODO.md batch 2026-07-27, не повторять):
- `esc()` существует (`shared.js:55`), 131 использование.
- **Confirmed real gap**: `checkin.js:158` — `resultEl.innerHTML = html` (AI-анализ) НЕ эскейпится. Error path (:161) экранирован, success path — нет. Чинить первым в этом under-раздел.
- 20 файлов с `innerHTML`, нужен файл-за-файлом аудит (не сделан).
- CSS class whitelist — не существует нигде.
- Inline `onclick` с данными — ещё в: `app.html`(18), `home.js`(23), `feed.js`(8), `objects.js`(4), `abwesenheit.js`(4), `profile.js`(2), `chat.js`(2), `bubble-assign.js`/`tools.js`/`worker-checkin-fab.js`(1 each). Мигрировать по одному файлу.

Дополнительные конкретные места из владельческого списка: AI analysis в checkin (см. выше), stage names/status/object names, picker object/stage names, profile object history/skills, любые данные из Google Sheets, любые данные от user, любые данные от AI.

### A6. JSON storage
- `_atomic_write_json` (main.py:124) — **уже используется everywhere**, no direct `open(path,"w")` для JSON. FIXED, no action.
- JSONDecodeError handling — только 2 места в 4027-строчном файле. Нужен аудит каждого `json.load`/`json.loads` на runtime-файлах, добавить try/except с safe fallback (по образцу `roles.json`, main.py:145).
- Locks для конкурентных записей — **уже есть**: `AUDIT_LOCK`, generic `_json_locks` dict, `_photo_lock`, `_chat_lock`, `_checkin_lock`. FIXED (покрывает 15-site deadlock из ранее смёрженной `fix/security-reliability-p1`).
- Path traversal: проверить все `os.path.join`/`Path(...)`/`open(...)`/`FileResponse`/`os.remove`/`shutil.*`, особенно с `object_id`/`user_id`/`thread_key`/`filename`/`document_id`/`defect_id`/`attachment_id`/`date`. Тестовые значения: `../`, `../../`, `%2e%2e/`, `..%2f`, abs path, unicode separators, длинные ID, dot-only. Создать `validate_object_id()`, `validate_entity_id()`, `safe_storage_path()`, `ensure_path_within_base()`, `sanitize_original_filename()`.

### A7. Uploads
- Magic bytes: **CONFIRMED — не реализовано** (`grep magic\|imghdr\|filetype` пусто). Только `content_type` header (spoofable, 25 вхождений). Добавить content-sniffing.
- Size/count limits: chat=8MB confirmed, остальные unverified (TODO.md REC-10, не дублировать).
- Extension normalization, dangerous-type rejection — не проверено.
- Decompression bomb protection, allowlist formats, safe internal filename (original name only as metadata), запрет HTML/SVG если не нужны.

### A8. AI subprocess security
Проверить: запускается ли Claude CLI с `--dangerously-skip-permissions`, cwd, environment, доступ к secrets/коду, может ли user prompt влиять на tools, concurrency/timeout/orphan process, cost limit. Целевое состояние: обычный AI chat НЕ имеет shell/filesystem access, allowlist env vars, timeout, concurrency limit. Разделить: обычный AI chat ≠ агент с доступом к файлам.

### A9. Resource-level permissions (шире owner/worker)
Определить по каждому endpoint: unauthenticated / authenticated / owner / assigned worker / unassigned worker / creator / responsible worker / revoked user. Единый permission service (расширяет A1): `require_owner()`, `require_object_access()`, `require_object_assignment()`, `require_thread_access()`, `require_document_access()`, `require_defect_access()`, `require_shift_access()`. Проверить: нельзя удалить/понизить последнего owner, revoked user не остаётся active worker, role change логируется.

### A10. Check-in / shifts инварианты
Одна active shift на user; finish только для active shift; idempotency scope `user + operation + key`; photos принадлежат shift; object существует; worker имеет доступ; время в UTC, UI показывает Europe/Berlin. Concurrency test: много параллельных start requests → ровно одна active shift. State machine: DRAFT → STARTING → ACTIVE → FINISHING → COMPLETED (+ CORRECTION_REQUIRED, CANCELLED).

### A11. CSV/formula injection
Значения начинающиеся с `=`, `+`, `-`, `@` не должны исполняться как spreadsheet formula при экспорте. Использовать стандартный `csv` module, не ручную сборку строк.

### A12. Google Sheets sync failures
Найти `try: sync() except Exception: pass` паттерны — silent failure недопустим для owner-важных операций. Owner должен видеть sync error, даже если полноценный outbox пока не строится.

---

