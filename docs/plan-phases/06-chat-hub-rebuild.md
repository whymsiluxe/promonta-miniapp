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

