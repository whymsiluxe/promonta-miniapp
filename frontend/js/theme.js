// Тема: light — дефолт приложения (22.07 редизайн). Источник — Telegram.WebApp.colorScheme,
// ручной override поверх сохраняется в localStorage.theme ('dark'|'light').

function _resolveInitialTheme() {
  // 22.07: полный редизайн на светлую тему — light всегда, независимо от системной
  // темы устройства/Telegram. Раньше тема следовала за Telegram.colorScheme, из-за
  // чего юзер с тёмным Telegram продолжал видеть старый тёмный стиль после редизайна.
  // Одноразовый сброс localStorage.theme (мог остаться 'dark' с прошлых сессий).
  if (!localStorage.getItem('theme_migrated_22jul2026')) {
    localStorage.removeItem('theme');
    localStorage.setItem('theme_migrated_22jul2026', '1');
  }
  const stored = localStorage.getItem('theme');
  if (stored === 'dark' || stored === 'light') return stored;
  return 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

function setTheme(theme, persist = true) {
  applyTheme(theme);
  if (persist) localStorage.setItem('theme', theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  setTheme(current === 'dark' ? 'light' : 'dark');
  hapticImpact('light');
}

function initTheme() {
  applyTheme(_resolveInitialTheme());
  // 22.07: больше не следим за themeChanged Telegram — светлая тема фиксирована,
  // меняется только вручную через toggleTheme().
}
