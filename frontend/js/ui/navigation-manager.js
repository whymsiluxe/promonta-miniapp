// NavigationManager (24.07, Phase 0.5) — единый стек навигации + единая точка "назад"
// для всех триггеров (custom header, Telegram BackButton, Android hardware back).
//
// Дизайн-решение: единый стек с tab-тегом на каждой записи, не 5 отдельных стеков
// по числу нав-вкладок — план допускал оба варианта, полные per-tab стеки были бы
// непропорциональной сложностью для этой кодовой базы (12 мест switchView, ~15 экранов
// всего, один воркер/owner использует приложение последовательно, не параллельно
// в нескольких табах одновременно как в браузере).
//
// Модалки/bottom-sheet НЕ пушатся в стек как полноценный route — у них свой отдельный
// overlay-стек, т.к. они могут открываться поверх любого экрана и должны закрываться
// первым приоритетом при "назад", не заменяя текущий route.

const NavigationManager = (() => {
  const stack = [];
  const overlayStack = []; // { close: fn } — модалки/bottom-sheets, LIFO
  let backLocked = false;

  function push(screen, params = {}) {
    const prev = stack[stack.length - 1];
    if (prev) prev.scrollY = window.scrollY;
    stack.push({
      screen, params,
      parent: prev ? prev.screen : null,
      scrollY: 0,
      timestamp: Date.now(),
    });
    _syncTelegramBackButton();
  }

  function replaceRoot(screen, params = {}) {
    // Смена таба через bottom-nav — не растим стек бесконечно, сбрасываем на новый корень.
    stack.length = 0;
    push(screen, params);
  }

  function current() {
    return stack[stack.length - 1] || null;
  }

  function depth() {
    return stack.length;
  }

  // Overlay-стек: модалки регистрируют свой close-колбэк при открытии, снимают при закрытии
  // вручную (крестик/клик-вне). registerOverlay возвращает функцию для снятия с этого стека.
  function registerOverlay(closeFn) {
    const entry = { close: closeFn };
    overlayStack.push(entry);
    _syncTelegramBackButton();
    return () => {
      const idx = overlayStack.indexOf(entry);
      if (idx !== -1) overlayStack.splice(idx, 1);
      _syncTelegramBackButton();
    };
  }

  // Единая точка "назад" — приоритет: закрыть верхнюю модалку → вернуть предыдущий route.
  // Клавиатура/полноэкранное медиа/selection-mode пока не имеют отдельного состояния в этой
  // кодовой базе (нет режима множественного выбора нигде) — приоритет упрощён до того что
  // реально существует, не строим шаги под гипотетические будущие фичи.
  function back() {
    if (backLocked) return;
    backLocked = true;
    setTimeout(() => { backLocked = false; }, 250); // дебаунс двойного срабатывания

    if (overlayStack.length) {
      const top = overlayStack.pop();
      try { top.close(); } catch (e) {}
      _syncTelegramBackButton();
      return;
    }

    if (stack.length > 1) {
      stack.pop();
      const target = current();
      if (typeof switchView === 'function') {
        switchView(target.screen, { fromBack: true, scrollY: target.scrollY });
      }
      _syncTelegramBackButton();
      return;
    }

    // 24.07: на корне (глубина 1, ни одной модалки) план изначально требовал no-op,
    // но это оставляло стрелку "назад" в шапках корневых табов (напр. список тредов
    // чата, открытого через bottom-nav) визуально ведущей в никуда -- юзер тапает,
    // ничего не происходит. Раз кнопка física нарисована, она должна куда-то вести:
    // на корне уводим на Home, если мы не уже на Home.
    if (current()?.screen && current().screen !== 'home' && typeof switchView === 'function') {
      switchView('home', { isTabSwitch: true });
    }
  }

  function _syncTelegramBackButton() {
    try {
      const tgBack = window.Telegram?.WebApp?.BackButton;
      if (!tgBack) return; // версия клиента может не поддерживать — не считаем ошибкой
      if (overlayStack.length || stack.length > 1) {
        tgBack.show();
      } else {
        tgBack.hide();
      }
    } catch (e) {}
  }

  function init() {
    try {
      window.Telegram?.WebApp?.BackButton?.onClick(() => back());
    } catch (e) {}

    // Android hardware back / браузерный back — тот же .back(), не системный переход.
    window.addEventListener('popstate', (e) => {
      e.preventDefault?.();
      back();
    });
  }

  return { push, replaceRoot, back, current, depth, registerOverlay, init };
})();
