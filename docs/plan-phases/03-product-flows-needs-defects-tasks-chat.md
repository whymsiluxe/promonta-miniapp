# Promonta Mini App — Audit Master Plan (Phase file)

PHASE B part 2 — Needs/Defects/Tasks workflows + chat data logic. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE B (continued) — Needs, Defects, Tasks, Chat data logic

### B7. Потребности (Needs) — отдельный workflow, не текст в чате
Статус: **FALSE — план ошибался, +расширено (commits 3c67448 backend, e54ff4d frontend, 2026-07-27).** Проверка кода: полный CRUD уже существовал (`GET/POST/PATCH /api/tasks` + complete endpoint), не заглушка. Priority, per-object/global visibility split, Telegram-уведомления owner — всё уже работало.

Реальный gap: category (материал/инструмент/СИЗ/доступ/другое) — добавлен (`TASK_CATEGORIES`, Latin keys). Статусы — было 3 (открыто/в работе/закрыто), расширено до 7 (добавлены принято/заказано/выдано/отклонено поверх старых, backward-compatible). Frontend: category picker в форме создания (переиспользует `.fw-cat-btn` из finish-wizard). Voice input для title — уже был реализован (`attachVoiceInputButton`), не трогал.

**Не сделано**: AI-extraction preview (voice → AI parse → editable fields → confirm) — сейчас voice просто дописывает raw transcript в title textarea, нет отдельного AI-структурирования полей. Owner actions (принять/заказать/выдано/отклонить как UI-кнопки, не только PATCH status) — backend статусы готовы, frontend UI для этих действий не построен в этом проходе.

### B8. Дефекты (Mängel) — отдельный workflow
Статус: **Частично FIXED (mangel_lib.py статусы, 2026-07-27, ПРЯМАЯ PROD-ПРАВКА).** Assignment (`assigned_worker_id`) уже существовал. Статусы были 3 (`gemeldet`/`in Bearbeitung`/`behoben`), расширены до 5 (`needs_review`/`rejected` добавлены, старые не переименованы).

**Важно про способ доставки**: `mangel_lib.py` живёт в `/home/promonta/agent/` — **вне git-репозитория** (`miniapp-repo`), общий shared-модуль между staging и prod, нет промежуточного git-коммита для него в принципе. Залито напрямую в prod-путь с бэкапом (`mangel_lib.py.bak-pre-status-expand-20260727-230559`), owner дал явное разрешение на прямую заливку + restart `promonta-miniapp.service` (Python кеширует импорты, без restart новые статусы не подхватились бы). Отличается от всей остальной работы этой сессии, которая шла только в git-репо staging без деплоя.

**Не сделано**: owner UI actions (назначить ответственного через UI — assignment API уже есть, но нет kanban/status-change buttons на фронте для новых статусов), "запросить фото после исправления" workflow — не реализовано.

Голосовое создание Need: voice → AI extraction → preview editable fields (title/type/object/quantity/unit/urgency/description) → explicit confirm → create. Никогда не автосоздавать без подтверждения.

### B8. Дефекты (Mängel) — отдельный workflow
Worker: фото, локация, текст/голос, срочность, отправить. Owner: назначить ответственного, статус, запросить фото после исправления, закрыть после проверки. Статусы: NEW/ASSIGNED/IN_PROGRESS/NEEDS_REVIEW/DONE/REJECTED. Привязан к объекту, доступ ограничен object permissions (A1), история комментариев+фото.

### B9. Задачи объекта (Tasks) — воспроизвести и починить баг
Статус: **FIXED, root cause найден и подтверждён чтением кода (commit a32c229, 2026-07-27).** Не "не воспроизвёл в браузере" — нашёл точную причину статическим анализом, достаточно убедительно чтобы не тратить время на live-repro.

**Root cause**: два глобальных `function loadTasks(...)` с разными сигнатурами в разных файлах (`objects.js:166` — 3 аргумента, для object-scoped WorkItems; `tasks.js:25` — 0 аргументов, для глобального экрана Needs), загружены обычными `<script>` тегами (не modules). `tasks.js` подключён ПОСЛЕ `objects.js` в app.html — его версия молча перезаписывает первую в глобальном scope. Когда `object-info.js` вызывает `loadTasks(objectId, listEl, null)` после создания задачи, реально выполняется tasks.js-версия — игнорирует все 3 аргумента, рендерит в свой хардкодный `#tasks-list` (не существует в object-detail контексте), тянет глобальный неотфильтрованный список. Backend создаёт задачу успешно (`POST /api/objects/{id}/tasks` работает) — просто список никогда не перерисовывается в нужном месте. Ровно симптом "не даёт видимого результата".

Фикс: переименовал objects.js версию в `loadObjectWorkTasks` (4 места: определение + 2 call sites в objects.js + 2 в object-info.js). Проверил `renderTaskRow`/`attachTaskHandlers` (тоже только в objects.js) — коллизий с tasks.js нет.

**Не сделано** (вне скоупа root-cause фикса): assignee/due_date поля в task card (backend их не поддерживает, см. B5 due_date gap), bottom sheet UI для создания (сейчас inline input), idempotency key на create (нет double-tap защиты на этом конкретном create).

### B10. Чаты по контекстам (data logic часть — UI часть в PHASE E)
Статус: **Большая часть уже была в порядке (проверено в Фазе 01), точечный фикс на реальный gap (commit ef32c69, 2026-07-27).**

Уже FIXED до этой сессии (перепроверено, не gap): attachments/thread_key, `_check_thread_access` consistently применён (my_threads/messages/unread_by_thread/attachment/messages POST-DELETE), mark_read/download attachment проверяют доступ, `get_my_chat_threads` возвращает корректные previews. Polling: единый `_chatUnreadTimer` с `clearInterval` перед новым `setInterval` — не дублируется.

**Реальный gap, точечно исправлено**: `_renderChatMessages` использовал ТОЛЬКО `Math.max(...ts)` как индикатор "надо ли перерендерить" — если сообщение удалено с другого устройства/сессии и это не было последним сообщением, `maxTs` не менялся, polling-клиент молча продолжал показывать удалённое сообщение. Добавлен `_chatLastCount` рядом с `_chatLastTs`, re-render триггерится если изменилось любое из двух. Все 7 существующих `_chatLastTs = 0` resets (thread switches) спарены с `_chatLastCount = 0`.

**Owner explicit decision**: полный monotonic cursor (`message_id`/`thread_version`, backend response shape меняется во всех 11 chat endpoints) — сознательно НЕ делать сейчас отдельным патчем, риск сломать рабочий чат без промежуточного тестирования. Отложено до PHASE 07 (Chat Hub rebuild) — там всё равно redesign всего chat data flow, cursor логично встроить туда, не патчить дважды. Известный оставшийся edge case (не покрыт точечным фиксом): два одновременных edit с неизменными count и max-ts — не притворяюсь что это решено.

**Не сделано**: геолокация-в-чат — уже отложено owner'ом в B2 (Фаза 02), тот же статус здесь.

---

