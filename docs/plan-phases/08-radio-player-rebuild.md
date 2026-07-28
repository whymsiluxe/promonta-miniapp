# Promonta Mini App — Audit Master Plan (Phase file)

PHASE G — Radio Player full rebuild. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE G — Radio Player rebuild

Источник: ТЗ5 (полностью).

Референс: фиолетовый плеер (album art + Previous/Play-Pause/Next + progress 2:28/5:33 + bottom glow) — адаптировать под Old Money (forest/brass glow, не фиолетовый/RGB).

### G1. Удалить старую radio orb полностью
Найдено в: `frontend/js/home.js`, `frontend/js/swipe-nav.js`, `frontend/app.html`. Убрать: chrome floating bubble 82×82, fixed top-right, emoji, тяжёлую тень, floating-меню, старые конфликтующие CSS-правила (52px vs 82px разные размеры — известный факт из прошлой сессии). Не оставлять скрытый старый UI параллельно новому — проверить явно после рефакторинга.

### G2. HomeRadioPlayer (карточка на Home, обычный flow, не fixed)
Высота ~230-290px, radius 28-32, atmospheric background image (архитектура/интерьер/камень/дерево — не случайные stock-фото людей, не copyrighted artwork), gradient overlay (верх легче, низ плотнее forest/charcoal + мягкое forest/brass glow — НЕ фиолетовый/синий/кислотный). Название станции (16-18px/700) + описание/трек (14-15px/500, max 2 строки). Controls: Previous/Play-Pause(56-64px, самая заметная)/Next(48×48min), SVG only, aria-label, haptic, loading/disabled states. Progress bar ИЛИ `LIVE` indicator — автовыбор TRACK vs LIVE mode, **не показывать fake duration/progress если backend не даёт реальных данных**.

Состояния: IDLE/LOADING/BUFFERING/PLAYING/PAUSED/ERROR/OFFLINE — конкретные тексты см. ТЗ5 §8.

### G3. RadioController — единый источник состояния
Управляет HTMLAudioElement, station, station list, track metadata, play/pause/stop/next/previous, loading/buffering/error/reconnect, LIVE/TRACK mode. **Не создавать новый Audio element при каждом render, не дублировать listeners при повторном открытии Home.**

Проверить факт перед стартом: сколько сейчас реально станций поддерживает backend (owner просил switcher станций в одном из предыдущих ТЗ — не строить multi-station UI, если источник single-stream).

### G4. RadioMiniPlayer
48-56px высота, над bottom nav, только пока играет/на паузе после запуска и не закрыт explicitly. Скрыт: на Home (там уже большой player), при открытой клавиатуре, в photo viewer, в fullscreen media, поверх modal/bottom sheet, если остановлено/закрыто. Учитывает `contentSafeAreaInset.{left,right,bottom}` + реальную высоту bottom-nav (не magic offset типа `top:90px`).

### G5. Не делать (жёсткий список из ТЗ5 §14)
Чёрная orb, emoji, фиолетовый/RGB neon, giant album card fullscreen, autoplay со звуком, автозапуск при открытии приложения, fake progress/duration/metadata, несколько Audio elements, inline onclick/style, fixed top-right, меню поверх Telegram UI, tiny controls, hover-зависимость. Радио стартует только по явному действию юзера.

Файлы: `frontend/js/components/radio-player.js`, `frontend/js/core/radio-controller.js`, `frontend/css/components/radio-player.css`.

Тесты: unit (initial state, play/pause/next/previous, buffering, error, retry, stop, listener cleanup, single Audio element) + Playwright E2E (18 шагов ТЗ5 §16) + screenshots (idle/playing/buffering/error/mini-player/narrow iPhone/Android/increased text size).

---

## Статус (2026-07-28, live owner requests — вне формальной последовательности фаз)

`HomeRadioPlayer`/`RadioMiniPlayer`/`RadioController` уже существовали до старта фазы 05-10 (прошлая сессия) и заработали после CSP-фикса (`media-src` в Caddyfile, см. Phase 04 handoff). В текущей сессии owner протестировал живьём на телефоне и прислал два прямых запроса, обработанных сразу (не дожидаясь формального старта этой фазы по очереди):

- **G3 (список станций)** — **FIXED, commit `25ca0be`.** Было 4 плейсхолдер-станции (`techno`/`gop`/`rap`/`deep`), теперь 19 реальных потоков `radiorecord.hostingradio.ru`. Плюс бесшовная infinite-loop карусель чипов (список x3, scroll-snap CSS, JS-recenter у краёв без видимого скачка) — не было в исходной спеке G-фазы буквально, но естественное продолжение "switcher станций" из owner-запроса, upgrade UX поверх уже готового списка.
- **G2 (layout)** — **FIXED, commit `41b3ef7`.** Убран дублирующий верхний блок `PROMONTA RADIO` + подзаголовок (имя станции теперь только в status-row, напр. "В эфире · Rock"), status-row поднят выше карусели станций, карусель исключена из глобального tab-swipe жеста (`swipe-nav.js`) — свайп по станциям больше не триггерит смену таба.
- **G5 (не делать)** — актуально проверено заново: без autoplay, без fake progress/duration (по-прежнему только LIVE-режим, нет track duration от бэкенда), один `Audio` element (не создаётся новый при каждом render — `RadioController` не тронут в архитектурном смысле, только список станций расширен).

**Ещё не сделано из G-спеки** (не в этой сессии): единый набор unit/Playwright/screenshot тестов (§ Тесты выше) — не написаны для radio вообще, как и для большинства фичей проекта (см. `docs/TESTING.md`). Debug/verification на реальном iPhone/Android помимо owner'а — не проводился, статус "работает" — по прямому подтверждению owner в процессе (два последовательных конкретных запроса на доработку подряд, оба обработаны в тот же проход, не по жалобе на поломку).

**Продолжение (тот же день, отдельный процесс — см. ниже про конкурентную сессию):**
- **Mini-player перекрывал Objects FAB** — **FIXED, commit `018f648`.** Оба элемента (radio mini-player поверх bottom-nav и Objects "+" FAB) занимали правый нижний угол одновременно на табе Объекты. `objects.js` теперь ставит `body.view-objects-active` только когда FAB реально видим (`refreshObjectsFabVisibility()`), CSS сужает `.radio-mini-player` (`left`/`width` calc) только при этом классе — другие табы не затронуты, там FAB вообще не показывается. Заодно смягчён `scroll-snap-type` карусели станций с `mandatory` на `proximity` (пользователь жаловался, что свайп "залипал" точно на chip).
- **Видимый auto-scroll jump карусели станций при заходе на Home** — **FIXED, commit `9609941`.** `_buildRadioStationLoop()`'s стартовый прыжок на средний блок (`wrap.scrollLeft = blockWidth`) наследовал `scroll-behavior:smooth` от CSS, из-за чего юзер видел, будто список сам едет при каждом открытии Home. Отключается `scroll-behavior` на время программного прыжка (`'auto'` → forced reflow → вернуть `''`), реальный свайп юзера по-прежнему плавный.
- **Список станций**: добавлены "Гоп FM" (была в оригинальном 4-станционном плейсхолдер-списке, owner попросил вернуть) и "Russian Hits" — итого 21 станция.

**Важно про коммит `9609941`**: его заголовок называет только радио-правки, но он **также содержит несвязанное Phase 06 изменение** (chat polling consolidation, `frontend/js/chat.js`/`critical-alerts.js`/часть `app.html`) — результат гонки между этой автономной сессией (`autonomous-miniapp.timer`) и параллельно работавшим процессом Telegram-бота, каждый со своими незакоммиченными правками в одном рабочем дереве без блокировки. Контент проверен побайтово, ничего не потеряно — только commit message вводит в заблуждение относительно объёма изменений. Полная запись — `docs/CHANGELOG.md` за 2026-07-28 "chat polling consolidation + a concurrent-session note".

---

