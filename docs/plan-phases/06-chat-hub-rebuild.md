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

- **5 типов/табов чата**, не 4: Общий(group)/Личные(DM)/Объекты(`obj:ID`)/Дефекты(`mangel:ID`)/**Потребности(`task:ID`)** — последнего нет в спеке (спека явно требует "4 таба"). **РЕШЕНО 2026-07-28**: оставляем 5 табов — см. `docs/DECISIONS.md` запись от 2026-07-28. Причина: Потребности уже живая, ежедневно используемая фича с явным прошлым owner-требованием (комментарий в `app.html` про Object Info), удалять без прямого согласия owner — хуже, чем задокументированное отклонение от плана.
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

## Статус (2026-07-28, сессия 2 — реализация начата, не закончена)

Следующая сессия после аудита выше — план рекомендации выполнен по пунктам 1-3 и частично 4-6. Всё закоммичено и задеплоено на прод небольшими шагами (`python3 -m py_compile` / `node --check` перед каждым деплоем), живой чат не ломался ни разу за сессию.

### FIXED / реализовано и задеплоено
- **"4 vs 5 табов"** — РЕШЕНО, оставляем 5. См. `docs/DECISIONS.md` запись 2026-07-28.
- **Self-chat** — теперь явно запрещён (400) в `POST /api/chat/messages`, `/messages/attachment`, `/messages/voice`. Commit `583a3ff`.
- **Reactions (👍✅👀❗)** — backend (`chat_reactions.json`, toggle endpoint `POST /api/chat/messages/{id}/reactions`, embedded в `GET /api/chat/messages`) + frontend (long-press context menu на бабле, объединён с существующим delete — отдельная схема жестов для двух функций создала бы конфликт; чип реакции кликабелен напрямую; optimistic + rollback). Commits `7204908`, `feb9bf2`.
- **Pin/mute/archive data layer** — `chat_thread_meta.json.user_prefs` (per-user), endpoint `POST /api/chat/threads/prefs`. Backend только, **frontend controls НЕ нарисованы** (сознательно — спека прямо запрещает fake controls без data layer; теперь data layer есть, controls — следующий шаг). Попутно найден и исправлен реальный баг: `close_chat_thread` перезаписывал весь `meta[thread_id]`, что стёрло бы `user_prefs`. Commit `509e20e`.
- **Нормализованный `GET /api/chat/threads`** — полный целевой shape (`id/type/title/avatar_url/subtitle/last_message/unread_count/muted/pinned/archived/version`, `online` на DIRECT), покрывает все 5 типов. Existing `/api/chat/my_threads` НЕ тронут (используется живым UI). Заодно исправлен найденный попутно баг: старый `my_threads` никогда не возвращал GENERAL/DIRECT треды вообще — только obj:/mangel:/task:, из-за чего превью "Общий чат"/DM в списке чатов всегда показывали статичный fallback-текст, не реальное последнее сообщение (`_threadByKey()` в chat.js искал по ключу, которого не было в ответе). **Frontend ещё не читает этот endpoint** — только backend-groundwork. Commit `0ec6acb`.
- **Тёмная chat-specific палитра** — все 11 переменных из спеки, scoped на `#view-chat` (чат всегда тёмный, независимо от app-wide темы), не задевает `.ai-*` (чат с ИИ у owner). Commit `7476da6`.
- **Worker strip** — горизонтальная лента над табами, тап открывает/лениво создаёт DM, реальный online-presence + unread per-worker. Частично: search circle из спеки НЕ слит в один компонент с лентой (отдельный `<input>` выше, как был) — см. "Не сделано" ниже. Commit `b5becd7`.
- **Тесты** — `tests/test_chat_backend.py`, 16 stdlib-unittest кейсов на добавленную backend-логику, реально запущены (16/16 pass), не просто написаны. Commit `9159715`.

### Не сделано (осознанно, не блокер — следующая сессия)
- **Expandable search state machine** (COLLAPSED/EXPANDING/ACTIVE/SEARCHING/NO_RESULTS/ERROR/COLLAPSING, слияние с worker-strip в одну ленту) — самый крупный оставшийся фронтенд-кусок этой фазы, требует отдельного прохода с анимацией/debounce/AbortController/per-tab-scope поиска. Текущий plain `<input>` работает (клиентский filter в `renderChatThreadList`), просто не по референсу.
- **Polling consolidation** (2 таймера → 1 controller, monotonic cursor, AbortController, backoff) — сознательно не трогали в этой сессии: самый рискованный пункт (затрагивает работающий live-polling), решили не рисковать в той же сессии, где уже сделано много других изменений в тот же файл. Следующий шаг, отдельно, с полным вниманием.
- **Granular read receipts** (SENDING/SENT/DELIVERED/READ/FAILED) — backend реально знает только бинарное read/unread per-thread, не per-message DELIVERED/FAILED. Строить fake-состояния запрещено спекой напрямую ("не имитировать delivery если backend знает только SENT/READ") — этот пункт требует сначала решить, нужен ли per-message read-tracking вообще (сейчас его нет, только per-thread last_read ts), это архитектурное решение, не мелкая правка.
- **Pin/mute/archive UI** — data layer готов (см. выше), кнопки/свайпы в списке тредов ещё не нарисованы.
- **Нормализованный endpoint не подключен к фронту** — существует, не используется. Переключение живого UI на него — отдельный, более рискованный шаг (нужно параллельно тестировать оба пути перед вырезанием старого).
- **Файловая структура из спеки** (`screens/chat-hub.js`, отдельные `components/*.js`, `core/chat-controller.js`) — всё ещё в одном `chat.js` (теперь ~900+ строк). Не разбито намеренно: разбиение на модули без сборки (vanilla JS, `<script>`-теги) — это Architecture phase 09 забота (порядок загрузки, глобальные функции), смешивать с Chat Hub функциональными изменениями в одну сессию было бы рискованно.

### Рекомендация для следующей сессии (обновлено)
Порядок: 1) polling consolidation (самое рискованное, но и самое ценное — текущие 2 таймера дают устаревшие badges/previews в нескольких местах), 2) expandable search, 3) wiring нормализованного endpoint к фронту (с явным fallback/сравнением против старого перед вырезанием), 4) pin/mute/archive UI поверх готового data layer, 5) read-receipts — только после архитектурного решения про per-message tracking.

---

