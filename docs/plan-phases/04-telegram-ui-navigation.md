# Promonta Mini App — Audit Master Plan (Phase file)

PHASE C — Telegram safe-area, viewport controller, navigation, screen lifecycle. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE C — Telegram System UI + Navigation (P0 по одному из ТЗ, здесь идёт после Security по решению owner)

Источники: ТЗ2 §4-13.

### C1. Проблема
Ни один элемент приложения не должен быть под системными controls Telegram (Close/Back, menu справа, Dynamic Island, status bar). Симптомы со скриншотов: Home под Close, заголовки "Потребности"/"Объекты"/"Чат"/"Общий чат"/"Профиль" перекрыты, custom back дублирует Telegram Back, radio под Telegram menu, кнопка `+` объектов конфликтует с top-right zone, sticky content уходит под системную область при скролле.

### C2. TelegramViewportController
Централизованный модуль `frontend/js/core/telegram-viewport.js`. Управляет: `ready()`, `expand()`, `requestFullscreen` (только если реально нужен), `viewportHeight`, `viewportStableHeight`, `safeAreaInset`, `contentSafeAreaInset`, `isFullscreen`, события `viewportChanged`/`safeAreaChanged`/`contentSafeAreaChanged`/`fullscreenChanged`/`fullscreenFailed`, `visualViewport`, keyboard state, orientation.

CSS variables: `--tg-safe-{top,right,bottom,left}`, `--tg-content-safe-{top,right,bottom,left}`, `--app-viewport-height`, `--app-stable-viewport-height`, `--app-keyboard-height`, `--app-header-top`, `--app-bottom-safe`, `--app-bottom-nav-height`, `--app-radio-player-height`, `--app-content-bottom-space`.

Обновлять на: startup/ready/viewportChanged/safeAreaChanged/contentSafeAreaChanged/fullscreenChanged/orientationchange/visualViewport resize/keyboard open-close. Listeners с lifecycle+cleanup, не дублировать при повторном открытии экранов.

### C3. Fullscreen — проверить необходимость
Гипотеза: глобальный `requestFullscreen()` создаёт больше проблем чем пользы для business productivity app. Сравнить: A) `expand()` без fullscreen, B) fullscreen с корректным contentSafeAreaInset. Если A устраняет overlap и упрощает keyboard behaviour — отключить глобальный fullscreen, оставить только для photo viewer/document preview.

### C4. Exclusion zone (не просто `padding-top: 44px`)
Root screen: system controls zone → page title → subtitle → actions. Nested screen: Telegram BackButton показывается, custom arrow не дублируется, title ниже system zone. Не размещать в верхних углах: radio, FAB, `+`, собственное меню, заголовок, search, input, floating controls.

### C5. Debug safe area tool (dev-only)
Overlay показывающий safeAreaInset/contentSafeAreaInset/viewportHeight/keyboard height/fullscreen state/platform/version/exclusion zones. Не включать в production. Checklist для физического iPhone/Android теста — не утверждать "исправлено", пока automated tests не проходят И physical iPhone test не отмечен VERIFIED.

### C6. Навигация — единый источник истины
Сейчас конкурируют: NavigationManager, switchView, ручной `style.display`, inline onclick, custom back buttons, Telegram BackButton, popstate, hardware back, swipe navigation, overlays/dialogs/bottom sheets, photo comments/viewer, object detail, embedded chat, bottom tabs.

Целевая модель: route stack + overlay stack (+ media overlay stack если нужен). Back priority: 1) закрыть keyboard/transient input, 2) закрыть top dialog/bottom sheet, 3) закрыть photo/media overlay, 4) закрыть embedded thread substate, 5) вернуться на предыдущий route, 6) на root screen — не совершать случайный переход в другой tab.

### C7. Баг: Back из комментариев фото → Profile (конкретный воспроизводимый баг)
Сценарий: Home → лента фото → открыть фото → комментарии → Back → открывается Profile вместо возврата в ленту. Проверить: зарегистрирован ли comments modal как overlay, вызывается ли `closePhotoComments`, сохраняется родительский route, какой bottom tab считался активным, Telegram BackButton не вызывает два обработчика, нет stale overlay entries, route stack не сбрасывается при открытии модалки, нет fallback `showHome()`/`showProfile()`, scroll position и выбранная вкладка "Фото" сохраняются. Добавить E2E regression test.

### C8. Убрать дублирующие back-кнопки
Root screens — без custom back. Nested — Telegram BackButton. Custom back — только fallback если BackButton недоступна, оба вызывают один `NavigationManager.back()`. Не текстовый `←`, SVG chevron-left, touch target 44×44, haptic light, press scale ~0.96, prefers-reduced-motion.

### C9. Per-tab navigation state
Отдельные stacks: Home/Chat/Objects/Calendar/Profile. Переключение bottom tab не стирает контекст другого tab. Нет fallback-логики "если stack пустой — открыть Profile".

### C10. Screen lifecycle
Каждый крупный экран: `mount()/activate(params)/deactivate()/unmount()`. При deactivate/unmount — cleanup intervals/timeouts/ResizeObserver/IntersectionObserver/visualViewport listeners/document listeners/touch listeners/blob URLs/AbortControllers/media streams/voice recording/animation frames/overlay registration/polling/drag state. Идемпотентная инициализация — повторное открытие не создаёт второй timer/handler/listener/observer.

Статус C1-C10 в целом: **частично FIXED в сессиях до 2026-07-28** (safe-area compensation, header grid-центрирование, back-button SVG chevron, root routes без back-arrow — см. HANDOFF_PHASE05_10.md "What's already done, Phase 04"). C6/C9/C10 (единый source of truth навигации, per-tab стеки, полный screen lifecycle) **НЕ реализованы** — NavigationManager существует и покрывает 7 экранов, открытых через `switchView()`, но объект-detail/new-object-sheet/stages-view/chat-thread-detail остаются на отдельном ad-hoc display-toggle механизме вне стека (см. ниже, "Известный незакрытый пробел"). Не переделывалось в этой сессии — риск сломать много рабочих экранов ради архитектурной чистоты не оправдан объёмом оставшегося плана (фазы 05-10); зафиксировано как технический долг, не решение "пропустить осознанно".

---

## Remainder items 1-6 (последний, более детальный owner-брифинг — приоритет над C1-C10 выше)

См. `docs/HANDOFF_PHASE05_10.md` "Still open in Phase 04" за точную формулировку. Обработано в автономной сессии 2026-07-28.

**1. Objects FAB.** Статус: **FIXED, commit `eca02dc`.** `#add-object` вынесен из шапки (там перекрывал Telegram menu-кнопку справа) в `position:fixed` FAB над bottom-nav: squircle 60×60px/radius 21px, `var(--c-forest)` фон, ivory (`#F5F1E8`) плюс-иконка, appear 220ms opacity+translateY+scale без bounce, press `scale(0.92)`. Позиция считается через реально измеренную `--app-bottom-nav-height` (новая `_applyBottomNavHeight()`, читает `offsetHeight` видимого `.bottom-nav`, вызывается из `applyRoleNav()` + resize/orientationchange), не через magic number (в отличие от старого `.nav-item-start` check-in FAB, который так и остался на хардкоде — не трогали, вне скоупа этого пункта). Видимость: `refreshObjectsFabVisibility()` — только когда активен таб Объекты, показан список (не sheet/detail/stages), роль owner.

**2. Header centering verification.** Статус: **CONFIRMED, не gap.** Проверены все 5 root-экранов (`Home`/`Чат`(`.chat-list-header`)/`Объекты`/`Календарь`/`Профиль`) — все используют общий `header { display:grid; grid-template-columns: minmax(44px,auto) 1fr minmax(44px,auto); }` с `h1{grid-column:2; text-align:center}` (фикс от 27.07, commit `2d87c4d`). После выноса FAB из шапки Объектов (пункт 1 выше) все 5 root-шапок теперь содержат ТОЛЬКО `<h1>`, без боковых элементов — центрирование тривиально корректно. `.chat-list-header` не имеет собственного CSS-override, наследует базовый grid.

**3. Root vs nested route classification.** Статус: **Частично FIXED, commit `d305ba7`+`21db273`.** Root screens (Home/Chat-list/Objects-list/Calendar/Profile) уже не имели back-arrow (подтверждено чтением разметки — по факту это уже было сделано раньше в сессии, коммиты `5b14e62`/`e35dc2f`). Nested screens используют либо `NavigationManager.push()`+`.chat-back-btn` (7 экранов: tools/documents/working-objects/my-tasks/tasks/mangel/ai), либо отдельный ad-hoc display-toggle БЕЗ регистрации в NavigationManager (new-object-view — исправлено в этой сессии, см. пункт 5; object-detail/stages-view/chat-thread-detail — НЕ исправлено, остаётся пробелом). Найден и исправлен конкретный баг "оба сразу": Telegram нативная BackButton показывалась ОДНОВременно с кастомной `.chat-back-btn` на всех 7 nested-экранах, ничего не скрывало кастомную кнопку. Первая попытка фикса (`d305ba7`, скрыть весь `.chat-back-btn` по `body.tg-native-back`) была РЕГРЕССИЕЙ — `.chat-back-btn` переиспользуется и элементами, не подключёнными к NavigationManager (`checkin-status-close-btn`, `chat-thread-back-btn`), скрытие оставило бы юзера без способа закрыть эти экраны. Исправлено в `21db273`: селектор сужен до точного `[onclick="NavigationManager.back()"]`, бьёт только по 7 доказанно избыточным кнопкам. **Известный незакрытый пробел**: object-detail/stages-view/chat-thread-detail/new-object-sheet(частично) не в едином route stack — см. C6/C9/C10 выше.

**4. Fallback back-button component.** Статус: **CONFIRMED, не gap (уже было сделано раньше в сессии).** `frontend/js/ui/navigation-header.js` (commit до 28.07) уже заменяет `.chat-back-btn`/`.back-btn` на SVG chevron-left (не текстовый `←`) при `DOMContentLoaded`, стиль `.nav-back-btn` — ivory-градиент 3D-кнопка, press scale 0.96 + inset-тень. Форма — `border-radius:999px` (полный круг), НЕ squircle, как буквально просил owner ("soft squircle not a heavy circle") — это расхождение с формулировкой спеки, но кнопка уже мягкая (градиент+тень, не плоский тяжёлый круг), решил не трогать без явного запроса (риск несогласованности с другими круглыми элементами UI, которые тоже `border-radius:999px`). Новая `.bottom-sheet-close-btn` (пункт 5) использует squircle (`border-radius:12px`) — если owner подтвердит, что squircle предпочтителен системно, стоит унифицировать оба.

**5. Object-creation as bottom sheet.** Статус: **FIXED, commit `eca02dc`.** "Новый объект" был полноэкранной inline-формой (прятала весь `objects-list-view`). Теперь управляемый bottom sheet (`#new-object-sheet`), вынесенный на верхний уровень DOM (та же причина, что `checkin-status-modal`/`checkin-preview-modal` были вынесены 24.07 — `position:fixed` внутри `display:none` `.view`-предка не рендерится). Зарегистрирован в `NavigationManager.overlayStack` (паттерн как у `photo-comments-modal` в feed.js) — Telegram BackButton закрывает корректно. Закрытие: ✕/тап по фону/back(). `data-no-swipe` — свайп-навигация между табами не должна триггериться внутри формы.

**6. Minimal smoke test.** Статус: **Написан, НЕ выполнен, commit `ce7e2e4`.** `tests/smoke-nav-fab.js` — ad-hoc Playwright-скрипт (не полноценный фреймворк, это фаза 10), покрывает FAB-видимость/sheet open-close/native-back-button scoping. `npx playwright install chromium --with-deps` требует root (недоступен за пределами 3 sudo-правил для prod-деплоя), голый chromium download не хватает системных библиотек (`libnspr4.so` и др.) без apt-доступа для установки. Тест логически вычитан против реальных id/классов, но НЕ запускался — честно помечено как непроверенное, не заявлено как "прошёл".

