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
Симптом: input "Новая задача" + кнопка `+` не даёт видимого результата, список отсутствует, нет loading/error/success. **Нужно воспроизвести прежде чем чинить** — проверить: renderObjectTasksTab вызывается, listener подключён и не теряется после re-render, endpoint существует, HTTP method/field правильные, permission, object ID, backend response, error handling, list не обновляется после создания, DOM не пересоздаётся после bind, overlay не блокирует tap, iOS tap работает, Enter работает, зависимость от Google Sheets, правильный store.

Минимальная task card: title/status/assignee(если backend поддерживает)/priority/due date/creator/created time/actions/change status. Empty state с CTA. Create в bottom sheet. Create button: disabled во время запроса, spinner, Enter, очистка input только после success, error сохраняет текст, idempotency key против double-tap.

### B10. Чаты по контекстам (data logic часть — UI часть в PHASE E)
Контексты: общий/личный worker-owner/объект/задача/дефект/critical alert. UI всегда показывает где пишешь ("Чат объекта: ..."). Починить: attachments сохраняют thread_key, unread по object/task/mangel не считается как group, mark_read проверяет доступ, download attachment проверяет доступ к thread, `get_my_chat_threads` возвращает корректные previews. Добавить отправку геолокации в чат (только участникам чата).

Не использовать только max timestamp как индикатор изменения thread — monotonic cursor: `message_id`/`thread_version`/`updated cursor`/`next_cursor`. Polling: один timer, cleanup при уходе с экрана, backoff, AbortController, не дублируется при повторном открытии.

---

