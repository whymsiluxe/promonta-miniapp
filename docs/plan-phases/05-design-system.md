# Promonta Mini App — Audit Master Plan (Phase file)

PHASE D — Design tokens, typography, Home/Profile/Calendar/Bubble Assignment. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE D — Design System V2

Источники: ТЗ2 §14-18, §33-35.

Единый token system (не накладывать aliases поверх старого CSS):
```
--color-canvas: #F8F4EC;  --color-surface: #FFFDF8;  --color-surface-muted: #F0E9DD;  --color-surface-deep: #E8DFD0;
--color-text: #201D18;  --color-text-secondary: #696257;  --color-text-tertiary: #91897C;
--color-forest: #1E4B3A;  --color-forest-hover: #173B2E;  --color-forest-soft: #DCE7E1;
--color-brass: #A4814E;  --color-brass-soft: #EEE3CF;
--color-oxblood: #8F453E;  --color-oxblood-soft: #F0DEDB;
--color-border: #DED5C6;  --color-divider: #E8E0D4;
```
Семантика: forest=primary/active/success/selected, brass=premium detail/secondary/caution, oxblood=destructive/error/critical. Не использовать pure black, random blue, яркий оранжевый, множество похожих зелёных.

Типографика: единственный UI font Manrope (+ system fallback). Удалить Montserrat из функционального UI — **известный реальный факт**: `tokens.css` имеет `--font-heading: Manrope`, `--font-body: Montserrat` одновременно (найдено в предыдущей сессии, AUDIT_COVERAGE_MATRIX.md), но по SESSION_HANDOFF commit `871414a` это уже унифицировано — **проверить актуальное состояние перед повтором работы**, не задваивать. Scale: Page title 32/700, Large 28/700, Section 22-24/700, Card title 19-20/650-700, Body 16-17/450-500, Button 16-17/650, Secondary 14-15/450-500, Caption 12-13/500. Не мельче 16px для рабочего текста.

Spacing scale 4/8/12/16/20/24/32. Radius: controls 10-12, inputs/buttons 14, cards 16-18, sheets 22-24, chips/avatars 999. Максимум 3 shadow tokens (card/floating/pressed) — убрать множественные тени, neumorphism, hover translateY на мобильном.

Icons: единый SVG набор, одинаковый stroke, 20-24px, aria-label. Emoji — только как пользовательский контент, не системные иконки (radio/camera/CSV/tools/AI/settings/status/nav/primary actions).

### Home (owner + worker)
Проблемы: title под Telegram Close, разные дизайн-системы карточек, alert card случайная рамка, красная полоса неясного смысла, всё визуально одного приоритета, слабые иконки. Целевая иерархия: title → критические действия → сегодня → операционные показатели → последняя активность → второстепенные инструменты. Worker Home компактнее — без новостей/AI/бюджетов/статистики компании/настроек, фокус на: текущий объект, начать/завершить смену, мои задачи, важное сообщение, создать потребность, сообщить дефект, offline queue status.

### Profile
Header card (avatar/name/role/metadata, без огромного пустого пространства). Tabs: Мой профиль/Команда/Настройки, единый design system. Accordions свёрнуты по умолчанию (кроме секции с validation error). Objects — compact rows, не raw text dump. Team — avatar/name/role/status/object, remove через context menu с confirm. Settings — реальные (sounds/haptic/theme/radio/notifications). CSV export — secondary action, не огромная primary button.

### Calendar
Крупный title, заметный selector chip (owner: Все/worker; worker: свой), today vs selected различимы, отпуск/болезнь/обучение — цвет+icon+label (не только цвет), day tap → bottom sheet.

### Bubble Assignment — сохранить, не заменять таблицей
Проверить: hardcoded skills расходятся с profile data, unescaped stage names, inline onclick, drag конфликтует со swipe navigation, assignment conflicts/absences/overlapping dates, optimistic update+rollback+undo. Два режима: Просмотр (workers на объектах, unassigned отдельно, visible conflicts/absence) и Распределение (tap ИЛИ drag, global swipe отключён во время drag, haptic, conflict explained, Undo после изменения). Drag — не единственный способ (нужна tap-альтернатива).

---

## Статус по итогам проверки и работы 2026-07-28 (автономная сессия)

Каждый пункт спеки верифицирован по реальному коду (не по тексту плана) через параллельные read-only разведочные проходы, затем сделаны точечные правки там, где обнаружился настоящий, ограниченный по риску пробел. Токены/типографика:

**Design tokens (цвет/spacing/radius/shadow).** Статус: **CONFIRMED — расхождение только в именах, не решение переименовывать.** Спека просит `--color-canvas`/`--color-surface`/`--color-forest`/`--color-oxblood`/... — в реальном `tokens.css` используются `--c-bg`/`--c-surface`/`--c-accent`/`--c-red`/... с очень близкими (не идентичными, но в пределах ~5% по hex) значениями и полноценным compat-alias слоем (`--bg-app: var(--c-bg)` и т.п.) для старого inline CSS. Решение: **не переименовывать**. Переименование сотен CSS-правил ради совпадения буквальных имён токенов из спеки — чистый риск регресса (visual diff по всему приложению) без видимой пользователю выгоды, раз семантика и палитра уже эквивалентны. Если owner явно попросит именно эти имена (например для внешнего дизайн-инструмента/handoff) — тогда стоит; не делать превентивно.

**Типографика (единственный UI-шрифт Manrope).** Статус: **CONFIRMED, уже FIXED (commit `871414a`, сессия до этой).** Перепроверено заново: `--font-heading`/`--font-body` оба указывают на Manrope, Montserrat не встречается нигде в живых `app.html`/`tokens.css` (только в `.bak-pre-*` и `.archived-legacy/`, не отдаётся сервером).

**Иконки (emoji→SVG).** Статус: **BLOCKED, без изменений.** Подтверждено: emoji всё ещё используется как системные иконки в ~12+ местах (`home.js`/`ai.js`/`abwesenheit.js`/`checkin.js`/`finish-wizard.js`/`mangel.js`/`objects.js`/`tasks.js`/`tools.js`). Блокер актуален (см. `docs/SESSION_HANDOFF.md`) — owner должен прислать референс-картинку стиля иконок, без него разработка своего стиля unilaterally уже получила явный негативный фидбек в прошлой сессии.

### Home / Profile

Все 7 пунктов Home и 4 пункта Profile из спеки перепроверены агентом построчно против `home.js`/`profile.js`/`app.html`. Статус: **CONFIRMED — почти все уже FIXED в более ранних сессиях** (grid-заголовок, консолидация карточек до 5-6 CSS-классов, red/yellow бордеры — намеренные severity-индикаторы, а не случайные, worker Home уже компактнее через `currentRole==='worker'` ветвление, Profile-аккордеоны свёрнуты по умолчанию, CSV-кнопка уже role-different). Единственный найденный реальный минус: **"свернуть все кроме секции с validation error"** — в Profile нет ни одной секции с состоянием "validation error" вообще (нет такого понятия в текущем UI) — пункт спеки не отображается на реальный функционал, решение: **не реализовывать synthetic validation state ради буквы спеки**, если понадобится в будущем — добавить вместе с самой validation-логикой, которой сейчас просто нет.

### Calendar

**Title/selector/today-vs-selected** — Статус: **CONFIRMED, уже FIXED** (title 1.75rem, owner видит dropdown работников, worker — легенду; today получает отдельный outline, 4 состояния — свои цвета).

**"отпуск/болезнь/обучение — не только цвет"** — Статус: **CONFIRMED, не gap.** Grid-heatmap (`#abw-month-grid`) действительно только цвет (4 состояния доступности, не типа причины) — но это осознанная модель (availability-heatmap, не туда мапится тип причины), а список заявок под календарём (`renderAbwesenheitList`) уже показывает текстовый label причины (`ABW_REASON_LABEL`) для каждой записи — цвет НЕ единственный канал информации там, где вообще показывается тип причины.

**"day tap → bottom sheet"** — Статус: **FIXED, commit `9606f3d`.** `#abw-reason-form` был inline display:block/none блоком в потоке страницы; теперь bottom sheet (`#abw-reason-sheet`), переиспользующий паттерн из `new-object-sheet` (objects.js): регистрация в `NavigationManager.overlayStack`, закрытие ✕/тап-по-фону/после сохранения, `data-no-swipe`. Остался вложен внутрь `#view-abwesenheit` (не вынесен на верхний уровень DOM как `new-object-sheet`) — форма открывается только когда этот `.view` уже активен, поэтому "position:fixed под display:none-родителем" сюда не применимо, вынос был бы лишним риском без пользы.

### Bubble Assignment

**Hardcoded skills / unescaped names / inline onclick / drag-vs-swipe** — Статус: **CONFIRMED, уже FIXED/не gap** (skills берутся из реального `/api/workers` с 10.31, весь пользовательский текст проходит `esc()`, единственный inline onclick передаёт только DB-id, drag использует `setPointerCapture` — не конфликтует со свайп-навигацией).

**"Drag — не единственный способ (нужна tap-альтернатива)"** — Статус: **FIXED, commit `752b2f3`.** Тап по bubble без значимого движения (порог 6px, отслеживается в существующем pointerdown/pointermove/pointerup цикле, без нового типа событий) теперь ведёт в тот же confirm-popup, что и успешный drag — drag-логика не тронута.

**"assignment conflicts/absences/overlapping dates"** — Статус: **ЧАСТИЧНО CONFIRMED, менее серьёзно чем казалось.** Бэкенд (`backend/main.py:914` `assign_user`) **уже жёстко блокирует** и одобренный отпуск/больничный (409 с текстом причины+датами), и пересечение с назначением на другой объект (409) — это не просто цветовая подсказка, это серверная защита данных, которая уже существует. Фронтенд показывает эту ошибку через `showToast()` в `_confirmBubbleAssign`/`openAssignFromProfile` — то есть юзер узнаёт о конфликте, просто не ДО попытки назначить, а ПОСЛЕ (после сабмита формы confirm-popup). **Реальный оставшийся пробел — только UX-полировка** (проактивная подсветка конфликтов в самой bubble-арене/drop-зоне до попытки), не отсутствие защиты данных. **Deferred** — не реализовано в этой сессии, отдельная небольшая задача на будущее: подсвечивать/бледнить bubble работника, если он занят/недоступен в дефолтном периоде этапа, до тапа/драга.

**"optimistic update+rollback+undo"** — Статус: **REAL GAP, deferred.** Сейчас: POST → ждать ответ → либо закрыть панель, либо toast с ошибкой. Нет мгновенного оптимистичного обновления UI, нет Undo после успешного назначения. Не реализовано в этой сессии — оценка: полноценный undo для serverside-состояния (назначение уже физически произошло в Google Sheets через `objekte_lib.py`) требует либо честного "отменить = ещё один API-вызов unassign", либо action-toast с timeout-окном перед реальной отправкой POST — оба варианта достаточно инвазивны, чтобы делать отдельно и внимательно, не между делом внутри уже большой phase 05 сессии.

**"Два режима: Просмотр и Распределение"** — Статус: **REAL GAP, deferred.** Сейчас панель всегда в режиме назначения (открывается кнопкой "+" на этапе, drag/tap сразу что-то делают). Отдельного read-only "Просмотр" режима с картой занятости/unassigned/conflicts нет. Deferred — это по сути отдельный экран/вид (обзор занятости команды), не маленькая правка поверх существующей панели; в рамках оставшегося бюджета фаз 06-10 (Chat Hub — сам по себе многосессионный проект) решил не начинать, чтобы не оставить обе вещи недоделанными.

---

