# Promonta Mini App — Endpoint Access Matrix

Полная инвентаризация всех 140 routes в `backend/main.py`. Собрано прямым чтением кода (не по памяти/старым отчётам) 30.07.2026.

**核心 auth-примитивы:**
- `get_current_user` — валидирует Telegram initData, требует whitelist в `roles.json`, иначе 403.
- `get_role` — `'owner'`/`'worker'` из roles.json.
- `require_owner` — 403 если role != owner.
- `can_access_object(user, role, object_id)` — owner всегда true; worker только если есть `accepted` назначение.
- `require_object_access` — Depends-обёртка над `can_access_object` по path-параметру `object_id`.
- `require_mangel_access` — только проверяет существование тикета, НЕ проверяет доступ к объекту (осознанное решение: "любой worker видит любой дефект").
- `_check_thread_access` — для чат-тредов `obj:`/`mangel:`/`task:`.

Легенда столбца "Resource check": ✅ строгая проверка конкретного ресурса, `by-design` — намеренно открыто (задокументировано в коде), ⚠️ — asymmetric/несогласованно (см. примечания внизу).

---

## Роли / Admin

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/roles | ✅ | ❌ | require_owner |
| POST /api/roles | ✅ | ❌ | require_owner + защита от удаления последнего owner |
| DELETE /api/roles/{id} | ✅ | ❌ | require_owner + self-delete/last-owner блок |
| GET /api/me | ✅ | ✅ | self only |
| GET /api/health | ✅ | ✅ | unauthenticated (liveness probe, без чувствительных данных) |
| GET /api/workers | ✅ | ✅ | by-design: весь ростер виден всем |

## Профиль

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/profile/me | ✅ | ✅ | self only. 01.08: отдаёт skills_v2 + legacy skills (строки, для старого frontend) |
| GET /api/users/{id}/card | ✅ | ✅ | ✅ доп. shift/location поля только owner. 01.08: содержит skills_v2 |
| PATCH /api/profile/me | ✅ | ✅ | self only. 01.08: skills_v2 всегда сбрасывает verified в false; onboarding_completed требует имя+навык+уровень каждого |
| POST /api/profile/me/avatar | ✅ | ✅ | self only |
| GET /api/profile/{user_id}/avatar | ✅ | ✅ | by-design (полу-публичный, как user-card) |
| GET /api/profile/stats | ✅ | ✅ | ✅ non-owner принудительно self |

## Объекты

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /api/objects/{id}/image | ✅ | ❌ | require_owner |
| DELETE /api/objects/{id}/image/{fname} | ✅ | ❌ | require_owner |
| GET /api/objects/{id}/image/file | ✅ | ✅ | by-design (см. примечание 1) |
| GET /api/objects | ✅ | ✅ | by-design: весь список виден всем |
| GET /api/my-assignments | ✅ | ✅ | self only |
| POST /api/objects/{id}/assign | ✅ | ❌ | require_owner |
| DELETE /api/objects/{id}/assign/{uid} | ✅ | ❌ | require_owner. 01.08: 409 если у работника несколько активных назначений (раньше молча удаляло все) |
| POST /api/objects/{id}/assign/{uid}/respond | ✅ | ✅ | ✅ self only |
| GET /api/work-types | ✅ | ✅ | 01.08: любой авторизованный, единый каталог видов работ |
| GET /api/assignment-candidates | ✅ | ❌ | require_owner. 01.08: без утечки приватных absence note/reason |
| POST /api/objects/{id}/assignments/batch | ✅ | ❌ | require_owner. 01.08: несколько работников одним запросом |
| PATCH /api/objects/{id}/assignments/{assignment_id} | ✅ | ❌ | require_owner. 01.08: точечное изменение, значимая правка сбрасывает accepted → pending |
| DELETE /api/objects/{id}/assignments/{assignment_id} | ✅ | ❌ | require_owner. 01.08: удаляет ровно одно назначение по id |
| PATCH /api/workers/{uid}/skills/{skill_id}/verification | ✅ | ❌ | require_owner. 01.08: Worker не может сам подтвердить свой навык |
| GET /api/objects/{id}/tasks | ✅ | ✅ | ✅ require_object_access |
| POST /api/objects/{id}/tasks | ✅ | ❌ | require_owner |
| PATCH /api/tasks/{id}/complete | ✅ | ❌ | require_owner |
| GET/PATCH /api/objects/{id}/description | ✅ | GET only | ✅ require_object_access / require_owner |
| GET/POST /api/objects/{id}/info-items | ✅ | ✅ | ✅ require_object_access |
| DELETE /api/objects/{id}/info-items/{iid} | ✅ | ❌ | require_owner |
| GET/POST /api/objects/{id}/documents | ✅ | ✅ | ✅ require_object_access |
| DELETE /api/objects/{id}/documents/{did} | ✅ | ❌ | require_owner |
| GET /api/objects/{id}/documents/{fname}/file | ✅ | ✅ | ✅ require_object_access + matched against stored doc list |
| POST /api/objects | ✅ | ❌ | require_owner |
| PATCH /api/objects/{id}/status | ✅ | ❌ | require_owner |

## Angebot / Rechnung

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /api/angebot, /api/rechnung | ✅ | ❌ | require_angebot_access (owner/manager) |

## Инструменты

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/tools, /api/tools/{serial}/history | ✅ | ✅ | by-design: глобальный список |
| PATCH /api/tools/{serial}/checkout | ✅ | ✅ | ✅ holder_id принудительно = self |
| PATCH /api/tools/{serial}/return | ✅ | ✅ | ✅ только текущий держатель или owner |
| PATCH /api/tools/{serial}, POST /api/tools | ✅ | ❌ | require_owner |

## Feed

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| Все GET/POST /api/feed/* | ✅ | ✅ | by-design: общая лента компании |
| DELETE .../comments/{id} | ✅ | ✅ | ✅ автор или owner |

## Чат

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/chat/my_threads, /threads | ✅ | ✅ | ✅ per-thread _check_thread_access |
| GET /api/chat/messages | ✅ | ✅ | ✅ thread_key проверяется, DM только свои пары |
| GET /api/chat/unread_count, /unread_by_thread | ✅ | ✅ | ✅ self-scoped / per-thread |
| POST /api/chat/read | ✅ | ✅ | self only |
| POST /api/chat/messages/attachment, /voice | ✅ | ✅ | ✅ thread access + closed-thread check |
| POST /api/transcribe | ✅ | ✅ | per-user dir |
| GET /api/transcribe/{id}/audio | ✅ | ✅ | ✅ non-owner ограничен своей папкой |
| GET /api/chat/attachments/{fname} | ✅ | ✅ | ✅ non-owner: участник треда (IDOR-фикс 10.29) |
| POST /api/chat/messages | ✅ | ✅ | ✅ thread access |
| DELETE /api/chat/messages/{id} | ✅ | ✅ | ✅ автор или owner |
| DELETE/POST /api/chat/threads (close/reopen) | ✅ | ❌ | require_owner |
| POST .../reactions | ✅ | ✅ | ✅ через _check_message_access |
| POST /api/chat/threads/prefs | ✅ | ✅ | ✅ per-thread |

## AI Chat

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /api/ai-chat, GET/POST /api/ai-model, POST /api/ai-chat/upload | ✅ | ❌ | inline `role != 'owner'` check (не Depends, стилистически несогласованно с require_owner, функционально эквивалентно) |
| POST /api/ai-chat/worker | ✅ | ✅ | by-design: узкий worker-facing режим открыт всем |

## Roadmap / Этапы

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET/POST/PATCH /api/objects/{id}/stages | ✅ | ✅ | **by-design (28.07 owner-решение): без require_object_access** — любой worker видит/создаёт/правит этапы любого объекта |
| PATCH/DELETE/swap /stages/{row} | ✅ | ❌ | require_owner |
| POST .../complete, /blocker, DELETE /blocker | ✅ | ✅ | ✅ require_object_access |
| GET .../roadmap (snapshot) | ✅ | ✅ | by-design, тот же owner-принцип что и /stages |
| POST/DELETE .../roadmap/categories, /items | ✅ | ❌ | require_owner |
| POST .../roadmap/items/{id}/status | ✅ | ✅ | ✅ require_object_access |
| POST .../roadmap/notes | ✅ | ✅ | ✅ require_object_access |
| **GET .../roadmap/notes** | ✅ | ✅ | by-design, согласовано с /stages GET (см. примечание 2) |
| POST .../stages/{row}/request | ✅ (400) | ✅ | ✅ require_object_access, owner не может запросить сам себя |
| GET/POST .../stages/requests | ✅ | ❌ | require_owner |

## Tasks (Потребности)

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/tasks | ✅ | ✅ | ✅ non-owner без object_id видит только свои; **с object_id — видит все для объекта (by-design)** |
| POST /api/tasks | ❌ | ✅ | workers only |
| PATCH /api/tasks/{id} | ✅ | ❌ | require_owner |

## Mängel (Дефекты)

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/mangel, /counts | ✅ | ✅ | by-design: все дефекты видны всем |
| GET/POST .../comments, GET /{id} | ✅ | ✅ | require_mangel_access (только существование тикета, НЕ object-scoped — by-design) |
| POST /api/mangel | ✅ | ✅ | by-design |
| GET /api/mangel/photos/{fname}/file | ✅ | ✅ | ✅ non-owner: can_access_object по object_id тикета (строже, чем ticket/comments endpoints) |
| PATCH /api/mangel/{id}/status | ✅ | ❌ | require_owner |

## Check-in / Смены

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /api/checkin/start | ✅ | ✅ | ✅ owner: can_access_object; worker: _get_active_assignment_for_checkin |
| POST /api/checkin/{id}/pause, /finish | ✅ | ✅ | ✅ session.user_id == self или owner |
| GET /api/workers/{id}/calendar | ✅ | ✅ | ✅ non-owner принудительно self |
| GET /api/checkin/stundenzettel | ✅ | ✅ | ✅ non-owner принудительно self |
| GET /api/checkin | ✅ | ✅ | ✅ non-owner фильтр по self |
| GET /api/checkin/{id}/photo/{which}/{idx} | ✅ | ✅ | ✅ session owner или owner-роль |
| POST /api/checkin/manual | ✅ | ✅ | ✅ non-owner не может писать за другого |
| POST .../analyze-progress/-materials/-defects | ✅ | ✅ | ✅ через _get_checkin_session helper |

## Critical Alerts

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /{id}/ack, /resolve | ✅ | ✅ | ✅ target_user_id == self |
| GET /{id}/photo/{fname} | ✅ | ✅ | ✅ target_user_id == self или owner |
| GET /pending | ✅ | ✅ | self-scoped |
| POST /api/critical-alerts | ✅ | ❌ | require_owner |

## Absences (Abwesenheit)

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| POST /api/abwesenheit | ✅ | ✅ | self only |
| PATCH .../close, DELETE | ✅ | ✅ | ✅ entry.user_id == self или owner |
| PATCH .../status | ✅ | ❌ | require_owner |
| GET /api/abwesenheit | ✅ | ✅ | self-scoped |
| GET /api/abwesenheit/all | ✅ | ✅ | by-design: view-only team-wide |

## Dashboard / Alerts (owner-агрегаты)

| Method + Path | Owner | Worker | Resource check |
|---|---|---|---|
| GET /api/dashboard/* | ✅ | ❌ | require_owner |
| GET /api/alerts | ✅ | ✅ | role_filter tag в payload, worker получает подмножество |
| POST /api/alerts/dismiss | ✅ | ✅ | self only |

---

## Примечания к asymmetric/by-design пунктам

1. **`GET /api/objects/{object_id}/image/file`** — без `require_object_access`, в отличие от upload/delete (owner-only) на том же ресурсе. Согласовано с `GET /api/objects` (весь список объектов открыт всем) — не отдельная дыра, комментарий добавлен в код 30.07.
2. **`GET .../roadmap/notes`** — без `require_object_access`, в отличие от sibling `POST` того же ресурса. Согласовано с `GET /api/objects/{id}/stages` и `GET .../roadmap` (оба тоже открыты по документированному 28.07 owner-решению) — паттерн "читать может любой, писать — только назначенный", применяется последовательно по всей roadmap-группе. Комментарий добавлен в код 30.07.
3. **Mängel ticket-level GET/comments** (`require_mangel_access`) проверяют только существование тикета, не object access — но `GET /api/mangel/photos/{fname}/file` для того же ресурса СТРОЖЕ (реальный `can_access_object`). Осознанная асимметрия по 28.07 owner-решению ("любой worker видит любой дефект"), фото — чувствительнее текста, поэтому строже.
4. **AI-model/AI-chat-upload endpoints** используют inline `if role != 'owner': raise 403` вместо `Depends(require_owner)` — функционально эквивалентно, стилистически несогласованно (P2, не блокирует релиз).

## Тестовое покрытие

Из 140 routes до этого коммита negative-authorization тестами явно покрыты: checkin ownership (test_owner_kt_requirements.py), tools return/checkout (test_tools.py), object access scope (test_owner_kt_requirements.py). Этим коммитом добавлены недостающие: Worker A против Worker B на chat/mangel/absence, поддельный/просроченный initData, прямой доступ к чужому файлу (см. `tests/test_access_control.py`).
