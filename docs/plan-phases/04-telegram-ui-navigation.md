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

---

