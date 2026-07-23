// Общее для всех табов: авторизация, роль, API-обёртка, haptic/sound фидбек.
const initData = window.Telegram?.WebApp?.initData;
const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8001' : '';

let currentRole = 'worker';
let currentUserId = null;

// Прогрев данных на splash-экране: initApp() кладёт сюда промисы GET-запросов заранее,
// пока грузится анимация — к моменту открытия таба Объекты/Инструмент/Лента данные уже готовы.
// Каждый путь используется из кэша один раз, дальше идёт обычный живой fetch.
const _prefetchCache = {};

function api(path, options = {}) {
  const isGet = !options.method || options.method === 'GET';
  if (isGet && _prefetchCache[path]) {
    const cached = _prefetchCache[path];
    delete _prefetchCache[path];
    return cached;
  }
  return fetch(API_BASE + path, {
    ...options,
    headers: { 'X-Telegram-Init-Data': initData, 'Content-Type': 'application/json', ...(options.headers || {}) }
  }).then(async res => {
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
  });
}

// Экранирование пользовательского текста перед вставкой в innerHTML (описания Mängel-тикетов,
// комментарии, сообщения чата, задачи, новости) — без этого чужой ввод с <script>/onerror=
// выполнялся бы в контексте приложения у всех, кто открыл тот же список/тред.
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// img src / CSS background-image не умеют слать X-Telegram-Init-Data — файловые эндпойнты
// (фото ленты, Mängel, чек-ин) отдают 422 без него. Тянем blob через fetch с тем же заголовком,
// что и api(), и возвращаем object URL — единая точка вместо копипасты по каждому месту рендера.
let _toastTimer = null;

function showToast(message, type) {
  let el = document.getElementById('app-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'app-toast';
    document.body.appendChild(el);
  }
  el.className = 'app-toast' + (type ? ` app-toast-${type}` : '');
  el.textContent = message;
  el.classList.add('app-toast-show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('app-toast-show'), 3000);
}

async function authImageUrl(path) {
  const res = await fetch(API_BASE + path, { headers: { 'X-Telegram-Init-Data': initData } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return URL.createObjectURL(await res.blob());
}

async function authImg(imgEl, path) {
  if (!imgEl) return;
  try {
    imgEl.src = await authImageUrl(path);
  } catch (e) {}
}

async function authBgImage(el, path) {
  if (!el) return;
  try {
    el.style.backgroundImage = `url(${await authImageUrl(path)})`;
  } catch (e) {}
}

// Открытие внешней ссылки — единая точка (переиспользуется новостями и адресами объектов).
// Telegram.WebApp.openLink() открывает системным браузером поверх WebView вместо навигации внутри него.
function openExternalLink(url) {
  const wa = window.Telegram?.WebApp;
  if (wa && typeof wa.openLink === 'function') wa.openLink(url);
  else window.open(url, '_blank');
}

function prefetch(path) {
  // Не глотаем ошибку — просто позволяем ей всплыть при потреблении из кэша,
  // как если бы api() вызвали напрямую (иначе caller-код получит null вместо catch-ветки).
  _prefetchCache[path] = api(path);
}

function prefetchTracked(path) {
  // Как prefetch(), но splash-экран может дождаться того же промиса, что позже
  // заберёт настоящий код таба — сам промис в кэше не подменяется/не глотается,
  // ошибка (если будет) всё равно дойдёт до реального потребителя как обычно.
  const p = api(path);
  _prefetchCache[path] = p;
  return p.catch(() => null); // splash ждёт через Promise.allSettled — сетевой сбой не должен его подвесить
}

function hapticImpact(style) {
  try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(style); } catch (e) {}
  if (window.navigator.vibrate) window.navigator.vibrate(style === 'medium' ? 15 : 8);
}

let _dragAudioCtx = null;

function playTone(freqFrom, freqTo, duration, volume) {
  try {
    _dragAudioCtx = _dragAudioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const osc = _dragAudioCtx.createOscillator();
    const gain = _dragAudioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freqFrom, _dragAudioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(freqTo, _dragAudioCtx.currentTime + duration * 0.8);
    gain.gain.setValueAtTime(volume, _dragAudioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, _dragAudioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(_dragAudioCtx.destination);
    osc.start();
    osc.stop(_dragAudioCtx.currentTime + duration);
  } catch (e) {}
}

function playDragTickSound() { playTone(880, 440, 0.1, 0.08); }
function playDropSound() { playTone(440, 880, 0.12, 0.09); }

// Свайп-переход (между вкладками и внутри Ленты Инфо/Фото): короткий свип-тон.
function playSwipeSound(direction) {
  playTone(direction === 'left' ? 880 : 440, direction === 'left' ? 440 : 880, 0.08, 0.05);
}

// Инициализация роли — вызывается один раз при старте приложения (app.js).
async function fetchRole() {
  const me = await api('/api/me');
  currentRole = me.role;
  currentUserId = String(me.user_id);
  return currentRole;
}

// Как в обычном Telegram-чате: пока открыта клавиатура — нижнее меню скрыто,
// панель ввода поднимается вплотную к клавиатуре (visualViewport API отслеживает
// реальную видимую высоту, т.к. Telegram WebView не всегда сжимает 100vh сам).
function keepInputAboveKeyboard(inputBarEl) {
  if (!inputBarEl || !window.visualViewport) return;
  const vv = window.visualViewport;
  const nav = document.querySelector('.bottom-nav');

  function adjust() {
    const keyboardHeight = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    const isOpen = keyboardHeight > 50;
    inputBarEl.style.transform = isOpen ? `translateY(-${keyboardHeight}px)` : '';
    if (nav) nav.style.display = isOpen ? 'none' : 'flex';
  }

  vv.addEventListener('resize', adjust);
  vv.addEventListener('scroll', adjust);
  adjust();
}

// Публичная карточка пользователя (10.10) — доступна всем (не только owner как /api/profile/stats),
// вызывается с people-dots на карточке объекта и из имени в chat-треде.
async function openUserCard(userId) {
  const modal = document.getElementById('user-card-modal');
  const body = document.getElementById('user-card-body');
  if (!modal || !body) return;
  modal.style.display = 'flex';
  body.innerHTML = 'Загрузка...';
  try {
    const card = await api(`/api/users/${encodeURIComponent(userId)}/card`);
    const initials = (card.name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
    const avatarHtml = card.has_avatar
      ? `<img class="user-card-avatar" id="user-card-avatar-img">`
      : `<div class="user-card-avatar-fallback">${esc(initials)}</div>`;
    const skillsHtml = (card.skills || []).length
      ? `<div class="user-card-skills">${card.skills.map(s => `<span class="user-card-skill-chip">${esc(s)}</span>`).join('')}</div>`
      : '<div style="color:var(--text-light);font-size:0.85rem">Навыки не указаны</div>';
    body.innerHTML = `
      ${avatarHtml}
      <div class="user-card-name">${esc(card.name)}</div>
      <div class="user-card-role">${card.role === 'owner' ? 'Владелец' : 'Работник'}</div>
      ${skillsHtml}
    `;
    if (card.has_avatar) authImg(document.getElementById('user-card-avatar-img'), `/api/profile/${userId}/avatar`);
  } catch (e) {
    body.innerHTML = `<div style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

function closeUserCard() {
  document.getElementById('user-card-modal').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('user-card-close-btn')?.addEventListener('click', closeUserCard);
});

// 22.07: переиспользуемая голосовая надиктовка для форм создания (Потребности/Дефекты) —
// переиспользует тот же MediaRecorder-паттерн что chat.js, но проще (нет thread-контекста,
// нет отправки в чат) — тап на кнопку начинает запись, повторный тап останавливает и
// транскрибирует через /api/transcribe (faster-whisper на бэке), результат идёт в колбэк.
let _voiceInputRecorder = null;
let _voiceInputChunks = [];

function attachVoiceInputButton(buttonEl, onTranscript) {
  if (!buttonEl || buttonEl.dataset.voiceWired) return;
  buttonEl.dataset.voiceWired = '1';
  buttonEl.addEventListener('click', async () => {
    if (_voiceInputRecorder) {
      _voiceInputRecorder.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _voiceInputChunks = [];
      const mimeType = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(t =>
        window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
      _voiceInputRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const usedMime = _voiceInputRecorder.mimeType || mimeType || 'audio/webm';
      _voiceInputRecorder.ondataavailable = e => { if (e.data.size > 0) _voiceInputChunks.push(e.data); };
      _voiceInputRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        _voiceInputRecorder = null;
        buttonEl.classList.remove('voice-input-recording');
        buttonEl.textContent = '🎤';
        const blob = new Blob(_voiceInputChunks, { type: usedMime });
        if (blob.size < 500) return;
        buttonEl.textContent = '⏳';
        try {
          const fd = new FormData();
          fd.append('file', blob, 'voice.webm');
          const res = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST',
            headers: { 'X-Telegram-Init-Data': initData },
            body: fd,
          });
          if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
          const data = await res.json();
          onTranscript(data.transcript || '');
        } catch (e) {
          showToast('Не удалось распознать речь: ' + e.message, 'error');
        } finally {
          buttonEl.textContent = '🎤';
        }
      };
      _voiceInputRecorder.start();
      buttonEl.classList.add('voice-input-recording');
      buttonEl.textContent = '⏹';
      hapticImpact('light');
    } catch (e) {
      showToast('Нет доступа к микрофону: ' + e.message, 'error');
    }
  });
}
