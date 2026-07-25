// NavigationHeader (25.07, Phase 0.5 completion) — единый визуальный компонент back-кнопки.
// NavigationManager.js уже владеет ПОВЕДЕНИЕМ (стек, приоритеты back(), Telegram BackButton) --
// этот файл владеет только РАЗМЕТКОЙ: находит все существующие .chat-back-btn (9 экранов,
// все уже вызывают onclick="NavigationManager.back()") и один раз при старте заменяет их
// содержимое на chevron-SVG + новый CSS-класс .nav-back-btn (3D ivory-кнопка по спеку плана:
// press-state scale+inset-shadow, forest chevron). Не трогаем сами onclick-обработчики --
// они уже корректны, дублировать/переписывать их тут нет причины.

function _renderNavBackButtons() {
  document.querySelectorAll('.chat-back-btn, .back-btn').forEach(btn => {
    if (btn.dataset.navHeaderUpgraded) return;
    btn.dataset.navHeaderUpgraded = '1';
    btn.classList.add('nav-back-btn');
    btn.innerHTML = '<svg class="nav-back-chevron" viewBox="0 0 24 24" width="20" height="20"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M15 18l-6-6 6-6"/></svg>';
  });
}

document.addEventListener('DOMContentLoaded', _renderNavBackButtons);
