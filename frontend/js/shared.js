// Общее для всех табов: авторизация, роль, API-обёртка, haptic/sound фидбек.
const initData = window.Telegram?.WebApp?.initData;
const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8001' : '';

let currentRole = 'worker';
let currentUserId = null;

// 03.08 (ТЗ Задача 1): 12-часовой backend session token поверх initData -- initData
// сам протухает через 1 час (Telegram его не переподписывает без реального переоткрытия
// мини-аппы), так что воркер посреди смены получал 401. sessionStorage (не localStorage) --
// токен привязан к конкретному открытию WebView, не должен переживать полное закрытие
// Telegram и попасть в постоянное хранилище на устройстве.
const SESSION_TOKEN_KEY = 'promonta_session_token';
let _sessionToken = null;
try { _sessionToken = window.sessionStorage.getItem(SESSION_TOKEN_KEY); } catch (e) { /* приватный режим / недоступно */ }

function _saveSessionToken(token) {
  _sessionToken = token;
  try { window.sessionStorage.setItem(SESSION_TOKEN_KEY, token); } catch (e) {}
}

function _clearSessionToken() {
  _sessionToken = null;
  try { window.sessionStorage.removeItem(SESSION_TOKEN_KEY); } catch (e) {}
}

// Получить token: если уже есть в sessionStorage -- используем как есть (backend всё
// равно проверяет whitelist/роль заново на каждый запрос, не доверяет токену слепо).
// Если нет -- обмениваем initData на token один раз при старте приложения (см. app.html).
async function ensureSessionToken() {
  if (_sessionToken) return _sessionToken;
  if (!initData) return null;
  const res = await fetch(API_BASE + '/api/session', {
    method: 'POST',
    headers: { 'X-Telegram-Init-Data': initData },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  const data = await res.json();
  _saveSessionToken(data.token);
  return data.token;
}

// Единая точка: юзер увидел "Сессия устарела" -- не молчаливый редирект/белый экран
// (ТЗ Задача 1). Токен стёрт, следующий ensureSessionToken() при новом открытии
// мини-аппы получит свежий initData от Telegram и перевыпустит токен сам.
function _handleSessionExpired() {
  _clearSessionToken();
  document.body.innerHTML = '<div style="padding:2rem 1rem;text-align:center;color:var(--text-light)">Сессия устарела. Переоткройте приложение.</div>';
}

// Прогрев данных на splash-экране: initApp() кладёт сюда промисы GET-запросов заранее,
// пока грузится анимация — к моменту открытия таба Объекты/Инструмент/Лента данные уже готовы.
// Большинство путей используется из кэша один раз, дальше идёт обычный живой fetch —
// см. исключение _isMultiConsumerPath() ниже для путей с несколькими независимыми consumers.
const _prefetchCache = {};

// 24.07: некоторые пути (/api/objects, /api/objects/{id}/stages) читаются НЕСКОЛЬКИМИ
// независимыми функциями сразу после splash (Home KPI, worker-checkin FAB, дашборд-кольца
// прогресса и т.д.) — если каждый путь потребляется одноразово, первый же consumer съедает
// кэш и все остальные (включая реальный экран, который юзер открывает секундой позже —
// "Объекты"/"Этапы объекта") идут в живой fetch, что и выглядело как "опять грузится".
// Для этих путей держим кэш живым короткое TTL-окно вместо немедленного delete — достаточно
// покрыть все параллельные consumers на старте, но не мешает live-обновлению данных позже
// (TTL истёк → обычный fetch, как и было). Сам общий механизм api()/prefetchTracked() для
// остальных путей (/api/tools, /api/feed/weather и т.п.) не трогаем — остаётся одноразовым.
const _MULTI_CONSUMER_TTL_MS = 8000;
function _isMultiConsumerPath(path) {
  return path === '/api/objects' || /^\/api\/objects\/[^/]+\/stages$/.test(path);
}

function api(path, options = {}) {
  const isGet = !options.method || options.method === 'GET';
  if (isGet && _prefetchCache[path]) {
    const cached = _prefetchCache[path];
    if (_isMultiConsumerPath(path)) {
      // Не удаляем сразу — оставляем на TTL, чтобы следующий independent consumer (Home KPI,
      // checkin FAB, rings, а потом и сам экран Объекты/Этапы) тоже попал в тёплый кэш.
      if (!cached._prefetchExpiry) cached._prefetchExpiry = Date.now() + _MULTI_CONSUMER_TTL_MS;
      if (Date.now() < cached._prefetchExpiry) {
        return cached.then(v => v); // тот же результат, без повторного delete-гонки
      }
    }
    delete _prefetchCache[path];
    return cached;
  }
  // 28.07 (ТЗ п.26): api() ставил Content-Type: application/json безусловно -- если бы
  // кто-то передал FormData как body (никто пока так не делает, все uploads используют
  // отдельный fetch() -- проверено, но лучше не оставлять ловушку для будущего кода),
  // это сломало бы multipart boundary, который браузер должен проставить сам. FormData
  // detection пропускает наш Content-Type override целиком.
  const isFormData = options.body instanceof FormData;
  // 03.08 (ТЗ Задача 1): Authorization: Bearer <session token> -- приоритетный путь,
  // не требует свежего initData на каждый запрос (12ч vs 1ч TTL). X-Telegram-Init-Data
  // остаётся как fallback, только если токена ещё нет (напр. сетевой сбой при первом
  // /api/session обмене на splash) -- backend всё ещё принимает его тоже (обратная
  // совместимость), так что запрос не проваливается впустую.
  const headers = { ...(options.headers || {}) };
  if (_sessionToken) headers['Authorization'] = `Bearer ${_sessionToken}`;
  else if (initData) headers['X-Telegram-Init-Data'] = initData;
  if (!isFormData) headers['Content-Type'] = 'application/json';
  return fetch(API_BASE + path, {
    ...options,
    headers
  }).then(async res => {
    if (!res.ok) {
      if (res.status === 401 && _sessionToken) {
        // Токен истёк/отозван (не первичная initData-проверка, у неё нет _sessionToken
        // ещё) -- явное сообщение юзеру, не silent redirect/белый экран без объяснения.
        _handleSessionExpired();
      }
      throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    }
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

// Раунд 5 §3: единый резолвер отображаемого имени. Некоторые Telegram-аккаунты не
// передают имя → раньше показывался сырой user_id (2091898960). Приоритет:
// profile.name → имя из roles/workers → Telegram first+last → "Сотрудник".
// Сырой user_id НИКОГДА не становится основным именем (только Owner видит его
// мелким вторичным текстом в админ-инфо). Любое новое место, показывающее имя
// пользователя, должно резолвить через это, а не брать поле напрямую.
function _looksLikeRawId(s) {
  return /^\d{3,}$/.test(String(s || '').trim());
}
function resolveDisplayName({ profileName, roleName, telegramFirstName, telegramLastName, userId } = {}) {
  const pick = v => {
    const t = (v == null ? '' : String(v)).trim();
    return t && !_looksLikeRawId(t) ? t : '';
  };
  const profile = pick(profileName);
  if (profile) return profile;
  const role = pick(roleName);
  if (role) return role;
  const tg = [telegramFirstName, telegramLastName]
    .map(x => (x == null ? '' : String(x)).trim())
    .filter(Boolean)
    .join(' ')
    .trim();
  if (tg && !_looksLikeRawId(tg)) return tg;
  return 'Сотрудник';
}

// 01.08 (доп.раунд П5): GET /api/objects отдаёт СЫРЫЕ Google Sheets-строки с русскими
// ключами (obj['ID объекта']/obj['Объект']/obj['Адрес']/obj['Статус']) -- не
// id/name/address как предполагал assignment-sheet.js (реальный найденный баг:
// отправлялся undefined в качестве object_id). Единая точка нормализации -- любой
// новый код должен читать объект через это, не изобретать свои obj.id/obj.name.
// 01.08 (доп.раунд П7): единый Europe/Berlin date helper -- new Date().toISOString()
// возвращает UTC-дату, которая расходится с локальной Berlin-датой вечером/ночью
// (найденный реальный баг в object-info.js: "сегодня" для смен считалось по UTC).
// Единая точка, используется вместо любого прямого toISOString().slice(0,10).
function todayBerlin() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin' }).format(new Date());
}

function tomorrowBerlin() {
  const todayStr = todayBerlin();
  const d = new Date(todayStr + 'T12:00:00Z'); // полдень UTC -- без риска перескочить дату при переходе через полночь Berlin
  d.setUTCDate(d.getUTCDate() + 1);
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin' }).format(d);
}

function normalizeObjectDto(obj) {
  return {
    id: obj['ID объекта'] ?? obj.id ?? '',
    name: obj['Объект'] || obj['Название'] || obj.name || '',
    address: obj['Адрес'] || obj.address || '',
    status: obj['Статус'] || obj.status || '',
  };
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
  _toastTimer = setTimeout(() => el.classList.remove('app-toast-show'), Math.max(3000, message.length * 60));
}

function _authHeaders() {
  // 03.08 (ТЗ Задача 1): та же приоритизация Bearer-токена, что и в api() -- отдельные
  // raw fetch() (файловые эндпоинты, img/blob) не проходят через api(), но должны
  // одинаково пережить протухший initData, если session token уже выпущен.
  if (_sessionToken) return { 'Authorization': `Bearer ${_sessionToken}` };
  return { 'X-Telegram-Init-Data': initData };
}

async function authImageUrl(path) {
  const res = await fetch(API_BASE + path, { headers: _authHeaders() });
  if (!res.ok) {
    if (res.status === 401 && _sessionToken) _handleSessionExpired();
    throw new Error(`HTTP ${res.status}`);
  }
  return URL.createObjectURL(await res.blob());
}

// 31.07: revoke предыдущий blob URL перед заменой src -- иначе повторный рендер того
// же элемента (напр. каждый poll-тик чата) копит blob'ы в памяти WebView без освобождения.
function _revokeIfBlobUrl(url) {
  if (url && url.startsWith('blob:')) {
    try { URL.revokeObjectURL(url); } catch (e) {}
  }
}

async function authImg(imgEl, path) {
  if (!imgEl) return;
  try {
    const newUrl = await authImageUrl(path);
    _revokeIfBlobUrl(imgEl.src);
    imgEl.src = newUrl;
  } catch (e) {}
}

async function authBgImage(el, path) {
  if (!el) return;
  try {
    const newUrl = await authImageUrl(path);
    _revokeIfBlobUrl(el.dataset.blobUrl);
    el.style.backgroundImage = `url(${newUrl})`;
    el.dataset.blobUrl = newUrl;
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
    // 30.07 (спек: expanded user-card) -- shift_status/object_name только для owner
    // (backend отдаёт их только owner'у, worker-to-worker card этих полей не видит).
    let statusHtml = '';
    if (card.shift_status === 'working') {
      const mins = card.start_at ? Math.round((Date.now() / 1000 - card.start_at) / 60) : 0;
      const durationLabel = mins >= 60 ? `${Math.floor(mins / 60)} ч ${mins % 60} мин` : `${mins} мин`;
      statusHtml = `<div class="user-card-status user-card-status-active">Смена идёт · ${esc(card.object_name)}${card.stage_name ? ' · ' + esc(card.stage_name) : ''} · ${durationLabel}</div>`;
    } else if (card.shift_status === 'idle') {
      statusHtml = `<div class="user-card-status">Смена сейчас не идёт</div>`;
    }
    // 30.07 (спек: полный Worker profile) -- кнопка перехода из карточки в полный
    // профиль (часы/навыки/размеры/объекты, существующий Profile→"Мой профиль" вид
    // для чужого работника). owner-only, свою же карточку открыть некуда вести.
    const fullProfileBtn = (currentRole === 'owner' && card.role !== 'owner' && typeof openWorkerFullProfile === 'function')
      ? `<button class="submit-btn profile-inline-btn" id="user-card-full-profile-btn" type="button" style="margin-top:0.5rem">Открыть профиль →</button>`
      : '';
    body.innerHTML = `
      ${avatarHtml}
      <div class="user-card-name">${esc(card.name)}</div>
      <div class="user-card-role">${card.role === 'owner' ? 'Владелец' : 'Работник'}</div>
      ${statusHtml}
      ${skillsHtml}
      ${fullProfileBtn}
    `;
    if (card.has_avatar) authImg(document.getElementById('user-card-avatar-img'), `/api/profile/${userId}/avatar`);
    document.getElementById('user-card-full-profile-btn')?.addEventListener('click', () => {
      closeUserCard();
      openWorkerFullProfile(userId);
    });
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
            headers: _authHeaders(),
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


// 24.07: человекочитаемый диапазон дат (Calendar polish) — юзер жаловался на сырой
// ISO-формат "2026-07-16 — 2026-07-16" в карточках Abwesenheit. Общий helper, не
// специфичен для одного экрана — lift в shared.js для переиспользования где ещё
// понадобится (план явно это требовал).
const FMT_MONTH_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

function fmtDateHuman(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  if (!y || !m || !d) return isoDate;
  return `${d} ${FMT_MONTH_GENITIVE[m - 1]}`;
}

function fmtDateRangeHuman(isoFrom, isoTo) {
  if (!isoFrom || !isoTo) return '';
  if (isoFrom === isoTo) return fmtDateHuman(isoFrom);
  const [yFrom, mFrom] = isoFrom.split('-').map(Number);
  const [yTo, mTo] = isoTo.split('-').map(Number);
  // Тот же месяц и год — "16 — 20 июля", не повторяем месяц дважды.
  if (yFrom === yTo && mFrom === mTo) {
    const dFrom = parseInt(isoFrom.split('-')[2], 10);
    return `${dFrom} — ${fmtDateHuman(isoTo)}`;
  }
  return `${fmtDateHuman(isoFrom)} — ${fmtDateHuman(isoTo)}`;
}
