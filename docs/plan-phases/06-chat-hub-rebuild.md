# Promonta Mini App — Audit Master Plan (Phase file)

PHASE E — Chat Hub full rebuild. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE E — Chat Hub rebuild

Источник: ТЗ3 (полностью) + ТЗ2 §24-26.

Референс: тёмный Messages screen (адаптировать под Promonta: charcoal вместо чёрного, forest green активный, brass акцент, oxblood только ошибки, Manrope, без оранжевого/stories/fake online).

Палитра (dark, chat-specific): `--chat-bg:#11130F; --chat-surface:#191C17; --chat-surface-hover:#20241E; --chat-surface-active:#252A23; --chat-text:#F5F1E8; --chat-text-secondary:#AAA59A; --chat-text-tertiary:#77756D; --chat-forest:#2D6A51; --chat-forest-light:#79A38F; --chat-brass:#A98754; --chat-border:rgba(245,241,232,0.08); --chat-divider:rgba(245,241,232,0.07)`.

Структура Chat Hub: title (ниже contentSafeAreaInset.top) → горизонтальная лента (Search circle первым + все активные работники) → tabs (Общий/Личные/Объекты/Дефекты) → список диалогов → bottom nav.

Expandable search: circle 56-64px → scale 0.94 → расширяется вправо на всю ширину контента → icon перемещается влево → input появляется + focus → Close справа → аватары сдвигаются/исчезают. 240-320ms, cubic-bezier, prefers-reduced-motion = мгновенно. Состояния: COLLAPSED/EXPANDING/ACTIVE/SEARCHING/NO_RESULTS/ERROR/COLLAPSING.

Поиск по вкладке: Общий (чаты+сообщения), Личные (люди+диалоги), Объекты (название/адрес/чат), Дефекты (title/объект/ответственный). Debounce 200-300ms, AbortController против stale results, сохранять query при возврате из найденного чата.

Worker strip: avatar 56-64px + имя (1 строка, ellipsis), online indicator только если presence реально хранится backend, unread badge, forest/brass ring. Инициалы+градиент если нет фото, никаких emoji. Тап → direct thread (создать лениво если не существует, детерминированная уникальность пары — см. ниже), не открывать Profile.

Direct thread uniqueness: `participant_low_id + participant_high_id` — A→B и B→A = один и тот же thread. Запретить self-chat.

4 таба, каждый с собственным empty/loading/error/offline state (тексты — см. ТЗ3 §29). Не смешивать типы (object chats ≠ direct ≠ general ≠ defect).

Unread badges: forest/brass, не оранжевый, `99+` cap, не показывать 0, обновлять после server confirmation (не раньше). Total unread на bottom-nav Chat tab = сумма разрешённых threads.

Reactions: компактный набор (👍✅👀❗ или аналог), long-press → context menu, chip под сообщением с count, своя reaction выделена, toggle снимает, optimistic + rollback on error. Backend: `message_id, user_id, reaction, created_at`, одна reaction одного типа от юзера на сообщение.

Read receipts: SENDING/SENT/DELIVERED/READ/FAILED — **только реальные состояния, которые backend реально знает**, не имитировать delivery если backend знает только SENT/READ.

Pin/mute/archive — **только если backend может это полноценно поддержать**; если нет data model — не рисовать fake controls, сначала строить data layer, или явно оставить вне scope.

Data model (целевая, JSON пока остаётся — см. Architecture ADR): ChatThread{id,type[GENERAL|DIRECT|OBJECT|DEFECT],title,object_id,defect_id,created_at,updated_at,last_message_id,version,archived}, ThreadParticipant{thread_id,user_id,joined_at,last_read_message_id,muted,pinned,archived,role}, ChatMessage{id,thread_id,sender_id,text,message_type,reply_to_id,attachment_id,created_at,updated_at,deleted_at,client_id}, MessageReaction{message_id,user_id,reaction,created_at}.

API: `GET /api/chat/threads?type=direct&cursor=...` — нормализованный response (id/type/title/avatar_url/subtitle/last_message/unread_count/muted/pinned/version), не сырой JSON storage shape, не русские названия Sheets колонок.

Workers API: один batch endpoint (user_id/display_name/avatar_url/role/active/direct_thread_id/unread_count), не N+1 запросов на каждого работника.

Polling: один controller для всего Chat Hub (threads+unread+last message+typing если есть), monotonic cursor не max-timestamp, AbortController, visibility handling, backoff, cleanup.

Frontend файлы: `frontend/js/screens/chat-hub.js`, `components/{chat-worker-strip,expandable-chat-search,chat-tabs,chat-list,chat-list-item,chat-thread,message-reactions}.js`, `core/chat-controller.js`, `css/screens/chat-hub.css`, `css/components/{chat-list,chat-search,chat-thread}.css`.

Тесты: unit (unique thread pair, search filtering, tab filtering, unread count, time formatting, ordering, reaction toggle, read state, controller cleanup, single polling instance) + Playwright E2E (6 сценариев из ТЗ3 §34: search animation, worker avatar→thread, tabs, unread, reactions, Telegram safe area на iPhone13mini/15ProMax/Android360×800) + visual regression screenshots (список в ТЗ3 §35).

---

## Аудит текущего состояния (2026-07-28, ДО старта рёбилда — не начато, только разведка)

Эта фаза НЕ начата в сессии 2026-07-28 — сама спека честно называет её "своим многосессионным проектом", а текущий чат — живая, ежедневно используемая production-система (реальная переписка команды). Начинать реальную реализацию в конце уже длинной сессии означало бы рисковать оставить критичную для бизнеса фичу в непроверенном промежуточном состоянии. Вместо этого код (не план) прочитан полностью и сверен построчно со спекой — чтобы следующая сессия стартовала с фактов, а не переоткрывала их заново.

### Что уже есть сегодня (frontend/js/chat.js 725 строк + backend/main.py ~2060-2625)

- **5 типов/табов чата**, не 4: Общий(group)/Личные(DM)/Объекты(`obj:ID`)/Дефекты(`mangel:ID`)/**Потребности(`task:ID`)** — последнего нет в спеке (спека явно требует "4 таба"). **Решение нужно ДО рёбилда**: убрать таб Потребности из Chat Hub (спека явно "4 таба"), или явно расширить спеку до 5 — не решать это молча внутри рёбилда, спросить/зафиксировать явно.
- **Детерминированная пара для DM УЖЕ РЕАЛИЗОВАНА** — `backend/main.py:2104-2107`, `_chat_thread_id()`: `'-'.join(sorted([user_a, user_b]))`. Это ровно то, что спека просит ("participant_low_id + participant_high_id"), просто другой техникой (sorted-join, не two-field id) — семантически эквивалентно, переделывать не за чем. Self-chat НЕ запрещён явно нигде — единственный реальный пробел в этом пункте.
- Unread per-thread, 99+ cap, attachments+voice-транскрипция (Whisper), message delete (owner/author), thread close/reopen (owner, шлёт Telegram-уведомление), access control per-thread (`_check_thread_access`) — всё это уже есть и работает.
- Polling: **2 независимых таймера**, не один controller — `_chatPollTimer` (8s, сообщения активного треда) и `_chatUnreadTimer` (15s, total unread, всегда активен независимо от видимости). Использует maxTs+length эвристику, не monotonic cursor. Нет AbortController, нет backoff.
- Backend API — `/api/chat/my_threads`, `/messages` (GET/POST/DELETE), `/messages/attachment`, `/messages/voice`, `/unread_count`, `/unread_by_thread`, `/read`, `/attachments/{fname}`, `/threads/status`, `/threads/close`, `/threads/reopen`, плюс общий `/api/workers`. Все возвращают "сырую" форму хранения (`thread_key`/`title`/`last_ts`/`last_preview`), НЕ нормализованный shape из спеки (`id`/`type`/`title`/`avatar_url`/`subtitle`/`last_message`/`unread_count`/`muted`/`pinned`/`version`).
- Хранение: `chat_messages.json` (плоский массив, max 200, retention 7 дней), `chat_reads.json` (`{user_id: {thread_key: ts}}`), `chat_thread_meta.json` (только `closed`/`closed_at`/`closed_by` — НЕТ mute/pin/archive полей). Участники треда нигде не хранятся персистентно — пересчитываются на каждый запрос из assignments/tickets/tasks.

### Чего нет вообще (нужно строить с нуля)

- Тёмная chat-specific палитра (11 CSS-переменных из спеки) — сейчас чат использует общие `--c-*` токены, не свою палитру.
- Expandable search circle с состояниями (COLLAPSED/EXPANDING/ACTIVE/SEARCHING/NO_RESULTS/ERROR/COLLAPSING) — сейчас просто текстовый `<input>`, без анимации/состояний/debounce/AbortController/query persistence.
- Горизонтальная лента аватаров работников — сейчас работники видны только строками списка в табе "Личные", не как отдельная лента над табами.
- Reactions на сообщениях (👍✅👀❗) — нигде не существуют (есть только у постов новостей/погоды, другой backend-механизм, не переиспользуется чатом).
- Гранулярные read receipts (SENDING/SENT/DELIVERED/READ/FAILED) — сейчас только бинарное read/unread per-thread, per-message состояний нет.
- Pin/mute/archive — только `closed`/`reopen` в метаданных, mute/pin/archive полей нет вообще ни в данных, ни в UI.
- Предложенная файловая структура (`screens/chat-hub.js`, `components/{chat-worker-strip,expandable-chat-search,chat-tabs,chat-list,chat-list-item,chat-thread,message-reactions}.js`, `core/chat-controller.js`, соответствующие CSS) — сейчас всё в одном `chat.js` (725 строк), `frontend/js/components/`/`core/` уже существуют как папки (из radio-player рёбилда), но не содержат ничего chat-специфичного.
- Тесты (unit+E2E+visual) — нет вообще, как и для всего остального проекта на этот момент (см. `docs/TESTING.md`).

### Рекомендация для следующей сессии

Это реализационная задача на полноценный отдельный проход (данные-модель → backend endpoints → frontend компоненты → тесты), не то, что стоит начинать с малым остатком контекста в конце другой сессии. Порядок при старте: 1) решить вопрос "4 vs 5 табов" с owner (или зафиксировать 5 как осознанное решение отклониться от спеки — Потребности явно используется), 2) спроектировать нормализованный API-shape и данные-модель (можно инкрементально поверх текущих плоских JSON-файлов, ADR см. Architecture phase 09 — не обязательно полная миграция сразу), 3) backend endpoints с новым shape параллельно со старыми (не ломать текущий живой чат посреди рёбилда), 4) frontend компоненты по одному, каждый комментируемый коммит, 5) reactions/read-receipts как отдельные под-этапы поверх готовой основы, 6) тесты по ходу, не в конце.

---

