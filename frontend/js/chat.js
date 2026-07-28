// Таб "Чат" — командный чат команды Promonta.
// Хранение: JSON-файл на VPS (последние 200 сообщений), polling каждые 8 сек.
// Решение: WebSocket избыточен для 2-5 чел., простой polling без зависимостей.
//
// 28.07 (Phase 06): единый polling controller (см. startChatPolling() внизу файла) —
// раньше было 2 независимых setInterval (сообщения активного треда 8s + total unread
// 15s, последний всегда активен независимо от видимости вкладки/приложения). Backend
// не отдаёт реальный пагинационный cursor (полный массив ≤200 сообщений на каждый
// запрос) — "monotonic cursor" из спеки реализован практически: сравнение сигнатуры
// (id+реакции) последнего снятого снимка вместо старой maxTs+length эвристики, которая
// не ловила reaction-only изменение (ts/length не менялись, но чужая реакция добавилась).

const CHAT_POLL_MS = 8000;
let _chatPollTimer = null;
let _chatPollAbort = null;
let _chatPollBackoffMs = 0;
let _chatLastRenderSig = null;
let _chatMyId = null;
let _chatIsOwner = false;
let _chatActiveThread = null; // null = группа, иначе user_id собеседника (DM)
let _chatActiveThreadKey = null; // 10.36: чат объекта/дефекта (obj:OBJ-001 / mangel:ticket_id) — приоритет над _chatActiveThread
let _chatWorkers = [];
let _chatReturnToView = null; // 21.07: откуда открыт чат (Потребности/Дефекты) — назад должен вернуть туда, не в общий список тредов

// 28.07 (Phase 06): message reactions — компактный фиксированный набор, зеркалит
// backend CHAT_REACTION_OPTIONS (main.py). Держать в синхроне при изменении набора.
const CHAT_REACTION_OPTIONS = ['👍', '✅', '👀', '❗'];
let _chatMessagesById = {}; // msg_id -> msg (последний рендер), для optimistic reaction toggle

function _escChat(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _fmtChatTime(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const timeStr = pad(d.getHours()) + ':' + pad(d.getMinutes());
  if (d.toDateString() === now.toDateString()) return timeStr;
  return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + ' ' + timeStr;
}

function _fmtChatDayLabel(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return 'Сегодня';
  if (d.toDateString() === yesterday.toDateString()) return 'Вчера';
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

function _renderChatMessages(messages) {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  if (!messages || messages.length === 0) {
    container.innerHTML = '<div class="chat-empty">Сообщений пока нет. Напишите первым!</div>';
    _chatLastRenderSig = null;
    return;
  }

  // Сигнатура снимка: id (порядок+delete/insert) + сводка реакций каждого сообщения --
  // ловит и удаление не-последнего сообщения, и reaction-only изменение без нового
  // сообщения/смены ts, оба пропускались старой maxTs+length эвристикой.
  const sig = messages.map(m => `${m.id}:${(m.reactions || []).map(r => `${r.reaction}${r.count}${r.mine ? '1' : '0'}`).join('')}`).join('|');
  if (sig === _chatLastRenderSig) return;

  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 30;
  _chatLastRenderSig = sig;

  // 24.07: группировка последовательных сообщений одного отправителя (Connecteam-стиль) —
  // второе+ сообщение подряд от того же юзера в пределах 120 сек не повторяет имя, садится
  // вплотную к предыдущему пузырю (chat-bubble-grouped, см. CSS).
  const GROUP_WINDOW_SECONDS = 120;
  let lastDayKey = null;
  let lastUid = null;
  let lastTs = null;
  _chatMessagesById = {};
  container.innerHTML = messages.map(msg => {
    _chatMessagesById[msg.id] = msg;
    const isOwn = msg.user_id === _chatMyId;
    const dayKey = new Date(msg.ts * 1000).toDateString();
    let divider = '';
    if (dayKey !== lastDayKey) {
      divider = `<div class="chat-day-divider">${_fmtChatDayLabel(msg.ts)}</div>`;
      lastDayKey = dayKey;
      lastUid = null; // новый день — не группировать через границу дня
    }
    const isGrouped = !divider && msg.user_id === lastUid && lastTs !== null && (msg.ts - lastTs) < GROUP_WINDOW_SECONDS;
    lastUid = msg.user_id;
    lastTs = msg.ts;
    // 25.07: имя+время в одну строку над сообщением (референс Connecteam), для ОБОИХ
    // own/other -- раньше имя показывалось только у чужих сообщений, время отдельной
    // строкой снизу у всех. Header скрыт целиком через CSS на сгруппированных сообщениях
    // (.chat-bubble-grouped .chat-msg-header{display:none}), не дублируем условие тут.
    const avatarHue = _chatAvatarHue(msg.user_id);
    const avatarInitial = (msg.name || '?')[0].toUpperCase();
    const avatarHtml = `<span class="chat-msg-avatar" style="background:hsl(${avatarHue} 45% 42%)" ${!isOwn ? `onclick="openUserCard('${msg.user_id}')"` : ''}>${avatarInitial}</span>`;
    const nameHtml = isOwn
      ? `<span class="chat-name">Вы</span>`
      : `<span class="chat-name" onclick="openUserCard('${msg.user_id}')">${_escChat(msg.name)}</span>`;
    return `${divider}
    <div class="chat-bubble ${isOwn ? 'chat-bubble-own' : 'chat-bubble-other'}${isGrouped ? ' chat-bubble-grouped' : ''}" data-msg-id="${msg.id}" data-uid="${msg.user_id}">
      <div class="chat-msg-header">${avatarHtml}${nameHtml}<span class="chat-time">${_fmtChatTime(msg.ts)}</span></div>
      ${msg.attachment ? _renderChatAttachment(msg) : ''}
      ${msg.text ? `<div class="chat-text">${_escChat(msg.text)}</div>` : ''}
      <div class="chat-reactions-slot">${_renderChatReactions(msg)}</div>
    </div>`;
  }).join('');

  if (wasAtBottom || messages.length === 1) {
    container.scrollTop = container.scrollHeight;
  }

  _attachChatBubbleHandlers(container);
  container.querySelectorAll('[data-auth-src] img.chat-attach-img').forEach(img => {
    const wrap = img.closest('[data-auth-src]');
    if (wrap) authImg(img, wrap.dataset.authSrc);
  });
  container.querySelectorAll('audio[data-auth-audio]').forEach(async audio => {
    try {
      audio.src = await authImageUrl(audio.dataset.authAudio);
    } catch (e) {}
  });
  container.querySelectorAll('[data-extract-transcript]').forEach(btn => {
    btn.addEventListener('click', () => _extractTaskFromTranscript(btn.dataset.extractTranscript, btn));
  });
}

async function _extractTaskFromTranscript(transcript, btnEl) {
  btnEl.disabled = true;
  btnEl.textContent = 'Разбираю…';
  try {
    const result = await api('/api/tasks/extract', {
      method: 'POST',
      body: JSON.stringify({ text: transcript, object_id: _chatActiveThreadKey?.startsWith('obj:') ? _chatActiveThreadKey.slice(4) : '' }),
    });
    if (!result.title) {
      showToast('AI не нашёл конкретный запрос в этом голосовом');
      btnEl.disabled = false;
      btnEl.textContent = '✨ Извлечь заявку';
      return;
    }
    const objectId = _chatActiveThreadKey?.startsWith('obj:') ? _chatActiveThreadKey.slice(4) : '';
    await api('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({ title: result.title, description: result.description, object_id: objectId }),
    });
    hapticImpact('light');
    btnEl.textContent = '✓ Заявка создана';
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    btnEl.disabled = false;
    btnEl.textContent = '✨ Извлечь заявку';
  }
}

let _chatLongPressTimer = null;

// 28.07 (Phase 06): один long-press-меню на реакции + удаление (раньше long-press
// сразу открывал confirm() на удаление, только для своих/owner сообщений; реакции
// нужны на ЛЮБОМ сообщении, поэтому меню теперь общее, delete-пункт в нём — опционален).
function _attachChatBubbleHandlers(container) {
  container.querySelectorAll('.chat-bubble').forEach(bubble => {
    const msgId = bubble.dataset.msgId;
    const canDelete = _chatIsOwner || Number(bubble.dataset.uid) === _chatMyId;

    bubble.addEventListener('touchstart', () => {
      _chatLongPressTimer = setTimeout(() => {
        hapticImpact('medium');
        _openChatBubbleMenu(bubble, msgId, canDelete);
      }, 500);
    }, { passive: true });

    bubble.addEventListener('touchend', () => clearTimeout(_chatLongPressTimer));
    bubble.addEventListener('touchmove', () => clearTimeout(_chatLongPressTimer));
  });

  container.querySelectorAll('.chat-reaction-chip').forEach(chip => {
    chip.addEventListener('click', e => {
      e.stopPropagation();
      _toggleChatReaction(chip.dataset.msgId, chip.dataset.reaction);
    });
  });
}

function _renderChatReactions(msg) {
  const reactions = msg.reactions || [];
  if (!reactions.length) return '';
  return `<div class="chat-reactions">${reactions.map(r => `
    <span class="chat-reaction-chip${r.mine ? ' mine' : ''}" data-reaction="${r.reaction}" data-msg-id="${msg.id}">${r.reaction}<span class="chat-reaction-chip-count">${r.count}</span></span>
  `.trim()).join('')}</div>`;
}

function _rerenderBubbleReactions(msgId) {
  const msg = _chatMessagesById[msgId];
  const bubble = document.querySelector(`.chat-bubble[data-msg-id="${msgId}"]`);
  const slot = bubble && bubble.querySelector('.chat-reactions-slot');
  if (!msg || !slot) return;
  slot.innerHTML = _renderChatReactions(msg);
  slot.querySelectorAll('.chat-reaction-chip').forEach(chip => {
    chip.addEventListener('click', e => {
      e.stopPropagation();
      _toggleChatReaction(chip.dataset.msgId, chip.dataset.reaction);
    });
  });
}

// Optimistic toggle: применяем локально сразу, откатываем при ошибке сервера —
// требование спеки ("optimistic + rollback on error").
async function _toggleChatReaction(msgId, reaction) {
  const msg = _chatMessagesById[msgId];
  if (!msg) return;
  const prevReactions = (msg.reactions || []).map(r => ({ ...r }));
  hapticImpact('light');

  const next = prevReactions.map(r => ({ ...r }));
  const existing = next.find(r => r.reaction === reaction);
  if (existing && existing.mine) {
    existing.count -= 1;
    existing.mine = false;
    if (existing.count <= 0) next.splice(next.indexOf(existing), 1);
  } else if (existing) {
    existing.count += 1;
    existing.mine = true;
  } else {
    next.push({ reaction, count: 1, mine: true });
  }
  next.sort((a, b) => CHAT_REACTION_OPTIONS.indexOf(a.reaction) - CHAT_REACTION_OPTIONS.indexOf(b.reaction));
  msg.reactions = next;
  _rerenderBubbleReactions(msgId);

  try {
    const res = await api(`/api/chat/messages/${msgId}/reactions`, {
      method: 'POST',
      body: JSON.stringify({ reaction }),
    });
    msg.reactions = res.reactions || [];
  } catch (e) {
    msg.reactions = prevReactions;
    showToast('Ошибка: ' + e.message, 'error');
  }
  _rerenderBubbleReactions(msgId);
}

function _openChatBubbleMenu(bubble, msgId, canDelete) {
  document.querySelectorAll('.chat-bubble-menu, .chat-bubble-menu-backdrop').forEach(el => el.remove());

  const backdrop = document.createElement('div');
  backdrop.className = 'chat-bubble-menu-backdrop';
  const menu = document.createElement('div');
  menu.className = 'chat-bubble-menu';
  menu.innerHTML = `
    <div class="chat-bubble-menu-reactions">
      ${CHAT_REACTION_OPTIONS.map(r => `<button type="button" data-reaction="${r}">${r}</button>`).join('')}
    </div>
    ${canDelete ? `<button type="button" class="chat-bubble-menu-delete">Удалить сообщение</button>` : ''}
  `;
  document.body.appendChild(backdrop);
  document.body.appendChild(menu);

  const rect = bubble.getBoundingClientRect();
  const menuWidth = menu.offsetWidth || 210;
  const menuHeight = menu.offsetHeight || 100;
  let left = Math.min(Math.max(16, rect.left), window.innerWidth - menuWidth - 16);
  let top = rect.bottom + 6;
  if (top + menuHeight > window.innerHeight - 16) top = rect.top - menuHeight - 6;
  menu.style.left = left + 'px';
  menu.style.top = Math.max(16, top) + 'px';

  const close = () => { backdrop.remove(); menu.remove(); };
  backdrop.addEventListener('click', close);
  menu.querySelectorAll('[data-reaction]').forEach(btn => {
    btn.addEventListener('click', () => {
      close();
      _toggleChatReaction(msgId, btn.dataset.reaction);
    });
  });
  const delBtn = menu.querySelector('.chat-bubble-menu-delete');
  if (delBtn) {
    delBtn.addEventListener('click', () => {
      close();
      _confirmDeleteChatMessage(msgId, bubble);
    });
  }
}

async function _confirmDeleteChatMessage(msgId, bubbleEl) {
  if (!confirm('Удалить сообщение?')) return;
  try {
    await api(`/api/chat/messages/${msgId}`, { method: 'DELETE' });
    bubbleEl.remove();
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function _loadChatMessages(forceScroll, signal) {
  try {
    const path = _chatActiveThreadKey ? `/api/chat/messages?thread_key=${encodeURIComponent(_chatActiveThreadKey)}`
      : _chatActiveThread ? `/api/chat/messages?with_=${_chatActiveThread}` : '/api/chat/messages';
    const data = await api(path, signal ? { signal } : {});
    _renderChatMessages(data.messages || []);
    if (forceScroll) {
      const c = document.getElementById('chat-messages');
      if (c) c.scrollTop = c.scrollHeight;
    }
  } catch (e) {
    if (e.name === 'AbortError') return;
    console.error('Chat poll error:', e.message);
  }
}

function _renderChatAttachment(msg) {
  const att = msg.attachment;
  const isImage = (att.content_type || '').startsWith('image/');
  const isAudio = (att.content_type || '').startsWith('audio/');
  if (isImage) {
    return `<div class="chat-attach-img-wrap" data-auth-src="/api/chat/attachments/${att.file}"><img class="chat-attach-img" alt="${_escChat(att.name)}"></div>`;
  }
  if (isAudio) {
    const transcript = msg.voice_transcript || '';
    const canExtract = currentRole !== 'owner' && transcript;
    return `<div class="chat-voice-player">
      <audio controls data-auth-audio="/api/chat/attachments/${att.file}"></audio>
    </div>
    ${transcript ? `<div class="chat-voice-transcript">"${_escChat(transcript)}"</div>` : ''}
    ${canExtract ? `<button class="chat-extract-task-btn" data-extract-transcript="${_escChat(transcript)}" type="button">✨ Извлечь заявку</button>` : ''}`;
  }
  return `<a class="chat-attach-file" href="${API_BASE}/api/chat/attachments/${att.file}" target="_blank" rel="noopener">📎 ${_escChat(att.name)}</a>`;
}

async function _sendChatAttachment(file) {
  const btn = document.getElementById('chat-attach-btn');
  if (btn) btn.disabled = true;
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('to_user_id', _chatActiveThread || '');
    const res = await fetch(`${API_BASE}/api/chat/messages/attachment`, {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    _chatLastRenderSig = null;
    await _loadChatMessages(true);
    hapticImpact('light');
  } catch (e) {
    const errEl = document.getElementById('chat-error');
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
      setTimeout(() => { errEl.style.display = 'none'; }, 4000);
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function _sendChatMessage() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('chat-send');
  const text = input.value.trim();
  if (!text) return;

  btn.disabled = true;
  input.disabled = true;
  try {
    await api('/api/chat/messages', {
      method: 'POST',
      body: JSON.stringify({ text, to_user_id: _chatActiveThread, thread_key: _chatActiveThreadKey }),
    });
    input.value = '';
    input.style.height = 'auto';
    _chatLastRenderSig = null;
    await _loadChatMessages(true);
    _loadMyChatThreads(); // 24.07: обновляет last_ts/last_preview в списке тредов, иначе
                           // дата/превью там оставались устаревшими до следующего захода
                           // в чат — my_threads грузился только один раз при initChatView.
    hapticImpact('light');
  } catch (e) {
    const errEl = document.getElementById('chat-error');
    if (errEl) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
      setTimeout(() => { errEl.style.display = 'none'; }, 4000);
    }
  } finally {
    btn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

function _renderUnreadBadge(count) {
  const badge = document.getElementById('chat-nav-badge');
  if (badge) {
    if (count > 0) {
      badge.textContent = count > 9 ? '9+' : String(count);
      badge.classList.add('show');
    } else {
      badge.classList.remove('show');
    }
  }
  const homeBadge = document.getElementById('home-chat-badge');
  if (homeBadge) {
    homeBadge.textContent = count > 99 ? '99+' : String(count);
    homeBadge.style.display = count > 0 ? 'flex' : 'none';
  }
}

async function _pollUnreadChat(signal) {
  try {
    const data = await api('/api/chat/unread_count', signal ? { signal } : {});
    _renderUnreadBadge(data.unread || 0);
  } catch (e) {
    if (e.name !== 'AbortError') throw e;
  }
}

// 28.07 (Phase 06): единый polling tick для всего Chat Hub — заменяет старые
// независимые _chatUnreadTimer(15s)/_chatPollTimer(8s). Каждый тик всегда обновляет
// total unread (нужен глобально для nav-badge вне зависимости от открытого экрана),
// и дополнительно сообщения активного треда — если он сейчас открыт. AbortController
// отменяет предыдущий незавершённый тик, если новый уже стартовал (защита от гонки
// устаревшего ответа, актуально при быстром открытии/закрытии тредов). Backoff растёт
// экспоненциально при сетевых ошибках, сбрасывается на первом успешном тике.
function _chatIsThreadDetailOpen() {
  const el = document.getElementById('chat-thread-detail-view');
  return !!el && el.style.display !== 'none';
}

async function _chatPollTick() {
  if (document.hidden) { _scheduleNextChatPoll(); return; }
  if (_chatPollAbort) _chatPollAbort.abort();
  _chatPollAbort = new AbortController();
  const signal = _chatPollAbort.signal;
  try {
    const jobs = [_pollUnreadChat(signal)];
    if (_chatIsThreadDetailOpen()) jobs.push(_loadChatMessages(false, signal));
    await Promise.all(jobs);
    _chatPollBackoffMs = 0;
  } catch (e) {
    if (e.name !== 'AbortError') _chatPollBackoffMs = Math.min((_chatPollBackoffMs || 4000) * 2, 60000);
  } finally {
    _scheduleNextChatPoll();
  }
}

function _scheduleNextChatPoll() {
  if (_chatPollTimer) clearTimeout(_chatPollTimer);
  _chatPollTimer = setTimeout(_chatPollTick, CHAT_POLL_MS + _chatPollBackoffMs);
}

function _onChatVisibilityChange() {
  // Немедленный тик при возврате в приложение вместо ожидания истечения текущего
  // интервала -- badge/сообщения не должны выглядеть устаревшими сразу после разблокировки.
  if (!document.hidden) _chatPollTick();
}

let _chatPollingStarted = false;
function startChatPolling() {
  _chatPollTick();
  if (_chatPollingStarted) return;
  _chatPollingStarted = true;
  document.addEventListener('visibilitychange', _onChatVisibilityChange);
}

async function markChatRead(threadUserId, threadKey) {
  if (!threadUserId && !threadKey) _renderUnreadBadge(0);
  try {
    const qs = threadKey ? `?thread_key=${encodeURIComponent(threadKey)}` : (threadUserId ? `?with_=${threadUserId}` : '');
    await api(`/api/chat/read${qs}`, { method: 'POST' });
  } catch (e) {}
}

// ── Thread-selector (Фаза 6): список контактов, "Общий чат" закреплён первым ──
async function _loadChatWorkers() {
  try {
    const res = await api('/api/workers');
    _chatWorkers = (res.workers || []).filter(w => String(w.user_id) !== String(_chatMyId));
  } catch (e) {
    _chatWorkers = [];
  }
  _renderChatWorkerStrip();
}

// 28.07 (Phase 06): горизонтальная лента работников над табами -- тап открывает/
// лениво создаёт DM. Рендерит только в #chat-worker-strip-avatars -- search circle
// (первый элемент ленты, см. app.html) остаётся статичной разметкой, не перезаписывается
// на каждый re-render, иначе терялись бы фокус/введённый текст/expanded-состояние.
function _renderChatWorkerStrip() {
  const strip = document.getElementById('chat-worker-strip-avatars');
  if (!strip) return;
  strip.innerHTML = _chatWorkers.map(w => {
    const hue = _chatAvatarHue(w.user_id);
    const unread = _chatUnreadByThread[String(w.user_id)] || 0;
    return `
    <div class="chat-worker-avatar-item" data-worker-id="${w.user_id}" data-worker-name="${_escChat(w.name || w.user_id)}">
      <div class="chat-worker-avatar-circle" style="background:hsl(${hue} 45% 42%)">
        ${(w.name || '?')[0].toUpperCase()}
        ${w.online ? '<span class="chat-worker-online-dot"></span>' : ''}
        ${unread > 0 ? `<span class="chat-worker-unread-dot">${unread > 99 ? '99+' : unread}</span>` : ''}
      </div>
      <span class="chat-worker-avatar-name">${_escChat((w.name || w.user_id).split(' ')[0])}</span>
    </div>`;
  }).join('');

  strip.querySelectorAll('.chat-worker-avatar-item').forEach(item => {
    item.addEventListener('click', () => openChatThread(item.dataset.workerId, item.dataset.workerName));
  });
}

// 28.07 (Phase 06): expandable search circle, слит в одну ленту с worker-strip (спека).
// Остаётся client-side (фильтр по уже загруженным заголовкам/именам/preview) -- полнотекстовый
// поиск по истории сообщений потребовал бы нового backend search endpoint, вне рамок этого
// прохода (см. docs/plan-phases/06-chat-hub-rebuild.md). Поэтому нет отдельных
// SEARCHING/ERROR-состояний из спеки -- нет сетевого запроса, которому нужен был бы
// AbortController/таймаут; debounce остаётся ради плавности рендера на каждый keystroke.
let _chatSearchDebounceTimer = null;

function _setChatSearchExpanded(expanded) {
  const circle = document.getElementById('chat-search-circle');
  const strip = document.getElementById('chat-worker-strip');
  if (!circle) return;
  circle.classList.toggle('expanded', expanded);
  if (strip) strip.classList.toggle('search-active', expanded);
}

function _initChatSearchCircle() {
  const circle = document.getElementById('chat-search-circle');
  const iconBtn = document.getElementById('chat-search-icon-btn');
  const closeBtn = document.getElementById('chat-search-close-btn');
  const input = document.getElementById('chat-thread-search');
  if (!circle || circle.dataset.wired) return; // идемпотентно -- initChatView может перевызываться
  circle.dataset.wired = '1';

  iconBtn.addEventListener('click', () => {
    _setChatSearchExpanded(true);
    input.focus();
    hapticImpact('light');
  });
  closeBtn.addEventListener('click', () => {
    input.value = '';
    _chatSearchQuery = '';
    _setChatSearchExpanded(false);
    renderChatThreadList();
  });
  input.addEventListener('blur', () => {
    if (!input.value.trim()) _setChatSearchExpanded(false);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') input.blur();
  });
  input.addEventListener('input', () => {
    if (_chatSearchDebounceTimer) clearTimeout(_chatSearchDebounceTimer);
    _chatSearchDebounceTimer = setTimeout(() => {
      _chatSearchQuery = input.value;
      renderChatThreadList();
    }, 250);
  });

  // "сохранять query при возврате из найденного чата" (спека) -- _chatSearchQuery не
  // сбрасывается при открытии/закрытии треда, initChatView может перевызываться при
  // повторном открытии таба Чат, восстанавливаем визуальное expanded-состояние.
  if (_chatSearchQuery) {
    input.value = _chatSearchQuery;
    _setChatSearchExpanded(true);
  }
}

let _chatUnreadByThread = {};
let _chatSearchQuery = '';

// 28.07 (Phase 06): pin/mute/archive UI поверх уже существующего backend data layer
// (POST /api/chat/threads/prefs, chat_thread_meta.json.user_prefs). Читаем сюда через
// нормализованный GET /api/chat/threads (Phase 06 groundwork, раньше ничем не
// использовался) в read-only режиме -- основной рендер списка по-прежнему берёт
// заголовки/превью из старых /api/chat/my_threads+/api/workers (полная замена
// источника данных — риск отдельный, не в этом проходе, см. docs/plan-phases/06-*).
// Ключи здесь совпадают с уже используемыми в _chatUnreadByThread/_threadByKey
// ('group', worker_id для DM, thread_key для obj:/mangel:/task:) -- нормализованный
// endpoint возвращает `id` именно в этой схеме.
const CHAT_DEFAULT_PREFS = { muted: false, pinned: false, archived: false };
let _chatThreadPrefs = {};
let _chatShowArchived = false;

async function _loadChatThreadPrefs() {
  try {
    const data = await api('/api/chat/threads');
    const byId = {};
    (data.threads || []).forEach(t => {
      byId[t.id] = { muted: !!t.muted, pinned: !!t.pinned, archived: !!t.archived };
    });
    _chatThreadPrefs = byId;
  } catch (e) {
    _chatThreadPrefs = {};
  }
}

function _threadPrefsFor(key) {
  return _chatThreadPrefs[key] || CHAT_DEFAULT_PREFS;
}

function _threadPrefsIcons(prefs) {
  if (!prefs.pinned && !prefs.muted) return '';
  let html = '<span class="chat-thread-prefs-icons">';
  if (prefs.pinned) html += '<span class="chat-thread-pin-icon" title="Закреплено"><svg viewBox="0 0 24 24" width="13" height="13"><path fill="currentColor" d="M14 2l8 8-4 1-5 5-1 4-2-2-5 5-1-1 5-5-2-2 4-1 5-5 1-4z"/></svg></span>';
  if (prefs.muted) html += '<span class="chat-thread-mute-icon" title="Заглушено"><svg viewBox="0 0 24 24" width="13" height="13"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M11 5L6 9H2v6h4l5 4V5zM23 9l-6 6M17 9l6 6"/></svg></span>';
  html += '</span>';
  return html;
}

// Сортирует закреплённые вверх (стабильная сортировка сохраняет порядок внутри групп),
// фильтрует архивные из обычного вида / показывает только архивные в режиме "Архив".
function _applyThreadPrefsView(items, getKey) {
  const withPrefs = items.map(it => ({ it, prefs: _threadPrefsFor(getKey(it)) }));
  const visible = withPrefs.filter(x => _chatShowArchived ? x.prefs.archived : !x.prefs.archived);
  visible.sort((a, b) => (b.prefs.pinned === a.prefs.pinned) ? 0 : (b.prefs.pinned ? 1 : -1));
  return visible;
}

async function _toggleChatThreadPref(prefsKey, payloadBase, prefName, newVal) {
  try {
    const res = await api('/api/chat/threads/prefs', {
      method: 'POST',
      body: JSON.stringify({ ...payloadBase, [prefName]: newVal }),
    });
    _chatThreadPrefs[prefsKey] = { ...CHAT_DEFAULT_PREFS, ..._threadPrefsFor(prefsKey), ...res.prefs };
    renderChatThreadList();
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function _openChatThreadPrefsMenu(itemEl, prefsKey, payloadBase) {
  document.querySelectorAll('.chat-bubble-menu, .chat-bubble-menu-backdrop').forEach(el => el.remove());
  const prefs = _threadPrefsFor(prefsKey);

  const backdrop = document.createElement('div');
  backdrop.className = 'chat-bubble-menu-backdrop';
  const menu = document.createElement('div');
  menu.className = 'chat-bubble-menu';
  menu.innerHTML = `
    <button type="button" class="chat-thread-menu-item" data-pref="pinned">${prefs.pinned ? '✓ ' : ''}${prefs.pinned ? 'Открепить' : 'Закрепить'}</button>
    <button type="button" class="chat-thread-menu-item" data-pref="muted">${prefs.muted ? '✓ ' : ''}${prefs.muted ? 'Включить уведомления' : 'Заглушить'}</button>
  `;
  document.body.appendChild(backdrop);
  document.body.appendChild(menu);

  const rect = itemEl.getBoundingClientRect();
  const menuWidth = menu.offsetWidth || 210;
  const menuHeight = menu.offsetHeight || 130;
  let left = Math.min(Math.max(16, rect.left), window.innerWidth - menuWidth - 16);
  let top = rect.bottom + 4;
  if (top + menuHeight > window.innerHeight - 16) top = rect.top - menuHeight - 4;
  menu.style.left = left + 'px';
  menu.style.top = Math.max(16, top) + 'px';

  const close = () => { backdrop.remove(); menu.remove(); };
  backdrop.addEventListener('click', close);
  menu.querySelectorAll('[data-pref]').forEach(btn => {
    btn.addEventListener('click', () => {
      close();
      const prefName = btn.dataset.pref;
      _toggleChatThreadPref(prefsKey, payloadBase, prefName, !prefs[prefName]);
    });
  });
}

let _chatThreadLongPressTimer = null;
function _attachChatThreadLongPress(itemEl, prefsKey, payloadBase) {
  itemEl.addEventListener('touchstart', () => {
    _chatThreadLongPressTimer = setTimeout(() => {
      hapticImpact('medium');
      _openChatThreadPrefsMenu(itemEl, prefsKey, payloadBase);
    }, 500);
  }, { passive: true });
  itemEl.addEventListener('touchend', () => clearTimeout(_chatThreadLongPressTimer));
  itemEl.addEventListener('touchmove', () => clearTimeout(_chatThreadLongPressTimer));
}


function _hideBottomNavInline() {
  const ownerNav = document.getElementById('bottom-nav-owner');
  const workerNav = document.getElementById('bottom-nav-worker');
  if (ownerNav) ownerNav.style.display = 'none';
  if (workerNav) workerNav.style.display = 'none';
}

function _chatAvatarHue(id) {
  const s = String(id || '');
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
}

function _threadBadge(count) {
  return count > 0 ? `<span class="chat-thread-badge">${count > 99 ? '99+' : count}</span>` : '';
}

let _chatMyThreads = [];
let _chatCategory = 'general';

async function _loadMyChatThreads() {
  try {
    const data = await api('/api/chat/my_threads');
    _chatMyThreads = data.threads || [];
    renderChatThreadList();
  } catch (e) {}
}

function _threadTimeLabel(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function _threadByKey(key) {
  return _chatMyThreads.find(t => t.thread_key === key);
}

function renderChatThreadList() {
  const listEl = document.getElementById('chat-thread-list');
  const q = _chatSearchQuery.trim().toLowerCase();

  listEl.classList.toggle('chat-thread-list-archived-mode', _chatShowArchived);

  if (_chatCategory === 'general') {
    const t = _threadByKey('group');
    const preview = t?.last_preview ? _escChat(t.last_preview) : 'Команда Promonta';
    const time = _threadTimeLabel(t?.last_ts);
    // 28.07 (Phase 06): "Общий" раньше вообще не фильтровался поиском -- матчим по
    // названию+превью последнего сообщения (полная история сообщений не загружена
    // на фронт, реальный full-text поиск по чату потребовал бы backend endpoint).
    const generalMatches = !q || 'общий чат'.includes(q) || (t?.last_preview || '').toLowerCase().includes(q);
    const generalPrefs = _threadPrefsFor('group');
    const generalVisible = generalMatches && (_chatShowArchived ? generalPrefs.archived : !generalPrefs.archived);
    if (!generalVisible) {
      listEl.innerHTML = `<div class="chat-empty">${!generalMatches ? 'Ничего не найдено' : 'Общий чат в архиве'}</div>`;
    } else {
      listEl.innerHTML = `
      <div class="chat-thread-item" data-thread="">
        <div class="chat-thread-avatar group"><svg viewBox="0 0 24 24" width="20" height="20"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">Общий чат</div>
          <div class="chat-thread-preview">${preview}</div>
        </div>
        <div class="chat-thread-meta">
          ${_threadPrefsIcons(generalPrefs)}
          ${time ? `<span class="chat-thread-time">${time}</span>` : ''}
          ${_threadBadge(_chatUnreadByThread.group || 0)}
        </div>
      </div>`;
      _attachChatThreadLongPress(listEl.querySelector('.chat-thread-item'), 'group', {});
    }
  } else if (_chatCategory === 'dm') {
    let filteredWorkers = q ? _chatWorkers.filter(w => (w.name || '').toLowerCase().includes(q)) : _chatWorkers;
    const viewWorkers = _applyThreadPrefsView(filteredWorkers, w => String(w.user_id));
    listEl.innerHTML = viewWorkers.map(({ it: w, prefs }) => {
      const t = _threadByKey(String(w.user_id));
      const preview = t?.last_preview ? _escChat(t.last_preview) : (w.role === 'owner' ? 'Владелец' : 'Работник');
      const time = _threadTimeLabel(t?.last_ts);
      const hue = _chatAvatarHue(w.user_id);
      return `
      <div class="chat-thread-item" data-thread="${w.user_id}">
        <div class="chat-thread-avatar-wrap">
          <div class="chat-thread-avatar" style="background:hsl(${hue} 45% 42%);border-color:hsl(${hue} 45% 42% / 0.35)">${(w.name || '?')[0].toUpperCase()}</div>
          ${w.online ? '<span class="chat-online-dot"></span>' : ''}
        </div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">${_escChat(w.name || w.user_id)}</div>
          <div class="chat-thread-preview">${preview}</div>
        </div>
        <div class="chat-thread-meta">
          ${_threadPrefsIcons(prefs)}
          ${time ? `<span class="chat-thread-time">${time}</span>` : ''}
          ${_threadBadge(_chatUnreadByThread[String(w.user_id)] || 0)}
        </div>
      </div>`;
    }).join('') || `<div class="chat-empty">${q ? 'Ничего не найдено' : (_chatShowArchived ? 'Архив пуст' : 'Нет личных чатов')}</div>`;
    listEl.querySelectorAll('.chat-thread-item[data-thread]').forEach(item => {
      _attachChatThreadLongPress(item, item.dataset.thread, { to_user_id: item.dataset.thread });
    });
  } else {
    const prefix = _chatCategory === 'obj' ? 'obj:' : _chatCategory === 'mangel' ? 'mangel:' : 'task:';
    let filtered = _chatMyThreads.filter(t => t.thread_key.startsWith(prefix));
    if (q) filtered = filtered.filter(t => t.title.toLowerCase().includes(q) || (t.last_preview || '').toLowerCase().includes(q));
    const viewThreads = _applyThreadPrefsView(filtered, t => t.thread_key);
    listEl.innerHTML = viewThreads.map(({ it: t, prefs }) => `
      <div class="chat-thread-item" data-thread-key="${t.thread_key}">
        <div class="chat-thread-avatar group" style="background:${_chatCategory === 'obj' ? 'color-mix(in srgb, var(--c-brass, var(--accent)) 16%, var(--bg-card-raised))' : 'color-mix(in srgb, #9A4B42 16%, var(--bg-card-raised))'};color:${_chatCategory === 'obj' ? 'var(--c-brass, var(--accent))' : '#9A4B42'};border-color:${_chatCategory === 'obj' ? 'color-mix(in srgb, var(--c-brass, var(--accent)) 35%, transparent)' : 'color-mix(in srgb, #9A4B42 35%, transparent)'}"><svg viewBox="0 0 24 24" width="20" height="20"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">${_escChat(t.title)}</div>
          <div class="chat-thread-preview">${_escChat(t.last_preview || '')}</div>
        </div>
        <div class="chat-thread-meta">
          ${_threadPrefsIcons(prefs)}
          ${_threadTimeLabel(t.last_ts) ? `<span class="chat-thread-time">${_threadTimeLabel(t.last_ts)}</span>` : ''}
          ${_threadBadge(_chatUnreadByThread[t.thread_key] || 0)}
        </div>
      </div>`).join('') || `<div class="chat-empty">${q ? 'Ничего не найдено' : (_chatShowArchived ? 'Архив пуст' : 'Чатов пока нет')}</div>`;
    listEl.querySelectorAll('[data-thread-key]').forEach(item => {
      _attachChatThreadLongPress(item, item.dataset.threadKey, { thread_key: item.dataset.threadKey });
    });
  }

  listEl.querySelectorAll('[data-thread-key]').forEach(item => {
    item.addEventListener('click', () => openObjectOrMangelChat(item.dataset.threadKey, item.querySelector('.chat-thread-name').textContent));
  });
  listEl.querySelectorAll('.chat-thread-item[data-thread]').forEach(item => {
    item.addEventListener('click', () => openChatThread(item.dataset.thread || null, item.querySelector('.chat-thread-name').textContent));
  });
}

async function _loadUnreadByThread() {
  try {
    const data = await api('/api/chat/unread_by_thread');
    _chatUnreadByThread = data.unread_by_thread || {};
    renderChatThreadList();
    _renderChatWorkerStrip();
  } catch (e) {}
}

function openChatThread(threadUserId, title) {
  _chatActiveThread = threadUserId;
  _chatActiveThreadKey = null;
  document.getElementById('chat-thread-title').textContent = title;
  document.getElementById('chat-thread-list-view').style.display = 'none';
  document.getElementById('chat-thread-detail-view').style.display = 'flex';
  document.body.classList.add('chat-dialog-open');
  _hideBottomNavInline();
  _chatLastRenderSig = null;
  _loadChatMessages(true);
  _refreshChatThreadCloseState();
  markChatRead(threadUserId); // per-thread — сбрасываем badge только этого треда (10.29)
}

function openObjectOrMangelChat(threadKey, title, returnToView) {
  _chatActiveThread = null;
  _chatActiveThreadKey = threadKey;
  _chatReturnToView = returnToView || null;
  switchView('chat');
  document.getElementById('chat-thread-title').textContent = title;
  document.getElementById('chat-thread-list-view').style.display = 'none';
  document.getElementById('chat-thread-detail-view').style.display = 'flex';
  document.body.classList.add('chat-dialog-open');
  _hideBottomNavInline();
  document.getElementById('chat-close-thread-btn').style.display = 'none'; // закрытие тредов не поддержано для obj:/mangel:
  _chatLastRenderSig = null;
  _loadChatMessages(true);
  markChatRead(null, threadKey); // 25.07: obj:/mangel:/task: треды раньше никогда не отмечались прочитанными
}

async function _refreshChatThreadCloseState() {
  const closeBtn = document.getElementById('chat-close-thread-btn');
  const banner = document.getElementById('chat-closed-banner');
  const reopenBtn = document.getElementById('chat-reopen-btn');
  const inputBar = document.getElementById('chat-input-bar');
  if (closeBtn) closeBtn.style.display = _chatIsOwner ? 'flex' : 'none';

  let closed = false;
  try {
    const status = await api(`/api/chat/threads/status?with_=${_chatActiveThread || ''}`);
    closed = !!status.closed;
  } catch (e) {}

  if (banner) banner.style.display = closed ? 'flex' : 'none';
  if (reopenBtn) reopenBtn.style.display = closed && _chatIsOwner ? 'inline-block' : 'none';
  if (inputBar) inputBar.style.display = closed && !_chatIsOwner ? 'none' : 'flex';
  // 24.07: closeBtn.textContent больше не перезаписывается — стирал SVG-иконку замка
  // (была в статичной разметке app.html). Видимость уже полностью управляется display.
  if (closeBtn) closeBtn.style.display = _chatIsOwner && !closed ? 'flex' : 'none';
}

async function _closeCurrentChatThread() {
  if (!confirm('Закрыть этот чат? Работник получит уведомление.')) return;
  try {
    await api('/api/chat/threads/close', {
      method: 'POST',
      body: JSON.stringify({ to_user_id: _chatActiveThread }),
    });
    hapticImpact('medium');
    await _refreshChatThreadCloseState();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

async function _reopenCurrentChatThread() {
  try {
    await api('/api/chat/threads/reopen', {
      method: 'POST',
      body: JSON.stringify({ to_user_id: _chatActiveThread }),
    });
    hapticImpact('light');
    await _refreshChatThreadCloseState();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function closeChatThread() {
  document.getElementById('chat-thread-detail-view').style.display = 'none';
  document.getElementById('chat-thread-list-view').style.display = 'flex';
  document.body.classList.remove('chat-dialog-open');
  if (typeof applyRoleNav === 'function') applyRoleNav();
  _chatActiveThread = null;
  _chatActiveThreadKey = null;
  if (_chatReturnToView) {
    const target = _chatReturnToView;
    _chatReturnToView = null;
    // 24.07: object-detail не входит в switchView() (не .view-элемент, свой display-контракт) --
    // он остаётся видимым под #view-chat всё время, скрывать/показывать заново не нужно,
    // просто не переключаем на другой view поверх него.
    if (target !== 'object-detail') switchView(target);
  }
}

async function initChatView() {
  if (!_chatMyId) {
    try {
      const me = await api('/api/me');
      _chatMyId = me.user_id;
      _chatIsOwner = me.role === 'owner';
    } catch (e) {
      const list = document.getElementById('chat-thread-list');
      if (list) list.innerHTML = `<div style="padding:2rem 1rem;text-align:center;color:var(--red)">Не удалось загрузить чат: ${esc(e.message)}</div>`;
      return;
    }
  }

  await _loadChatWorkers();
  renderChatThreadList();
  _loadUnreadByThread();
  _loadMyChatThreads();
  _loadChatThreadPrefs().then(renderChatThreadList); // pin/mute/archive приходят отдельным запросом, ре-рендерим когда готовы
  _initChatSearchCircle(); // idempotent -- поиск-input теперь в search circle внутри worker-strip

  document.querySelectorAll('.chat-category-tabs [data-chat-category]').forEach(tab => {
    tab.addEventListener('click', () => {
      _chatCategory = tab.dataset.chatCategory;
      document.querySelectorAll('.chat-category-tabs [data-chat-category]').forEach(t => t.classList.toggle('active', t === tab));
      renderChatThreadList();
    });
  });

  // Сообщения активного треда теперь подхватываются единым _chatPollTick() (см. выше,
  // startChatPolling) — отдельный setInterval здесь был вторым независимым таймером,
  // консолидированным в этой фазе.

  document.getElementById('chat-thread-back-btn').addEventListener('click', closeChatThread);

  const sendBtn = document.getElementById('chat-send');
  const input = document.getElementById('chat-input');

  sendBtn.addEventListener('click', _sendChatMessage);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _sendChatMessage();
    }
  });

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });

  const attachBtn = document.getElementById('chat-attach-btn');
  const fileInput = document.getElementById('chat-file-input');
  if (attachBtn && fileInput && !attachBtn.dataset.wired) {
    attachBtn.dataset.wired = '1';
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => {
      const file = e.target.files[0];
      if (file) _sendChatAttachment(file);
      e.target.value = '';
    });
  }

  const voiceBtn = document.getElementById('chat-voice-btn');
  if (voiceBtn && !voiceBtn.dataset.wired) {
    voiceBtn.dataset.wired = '1';
    voiceBtn.addEventListener('click', _startVoiceRecording);
    document.getElementById('chat-voice-cancel-btn').addEventListener('click', () => _stopVoiceRecording(false));
    document.getElementById('chat-voice-stop-btn').addEventListener('click', () => _stopVoiceRecording(true));
  }

  const closeBtn = document.getElementById('chat-close-thread-btn');
  if (closeBtn && !closeBtn.dataset.wired) {
    closeBtn.dataset.wired = '1';
    closeBtn.addEventListener('click', _closeCurrentChatThread);
  }
  const reopenBtn = document.getElementById('chat-reopen-btn');
  if (reopenBtn && !reopenBtn.dataset.wired) {
    reopenBtn.dataset.wired = '1';
    reopenBtn.addEventListener('click', _reopenCurrentChatThread);
  }
}


// Голосовые сообщения (10.37) — MediaRecorder API, формат webm/opus (Telegram WebView
// на iOS/Android поддерживает через getUserMedia+MediaRecorder, как и обычный Safari).
let _voiceRecorder = null;
let _voiceRecordingThreadKey = null;
let _voiceRecordingThread = null;
let _voiceChunks = [];
let _voiceTimerInterval = null;
let _voiceStartTs = 0;

let _voiceMimeType = 'audio/webm';

function _pickVoiceMimeType() {
  const candidates = ['audio/webm', 'audio/mp4', 'audio/aac', 'audio/ogg'];
  for (const t of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
}

async function _startVoiceRecording() {
  _voiceRecordingThreadKey = _chatActiveThreadKey;
  _voiceRecordingThread = _chatActiveThread;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    _voiceChunks = [];
    _voiceMimeType = _pickVoiceMimeType();
    _voiceRecorder = _voiceMimeType ? new MediaRecorder(stream, { mimeType: _voiceMimeType }) : new MediaRecorder(stream);
    _voiceMimeType = _voiceRecorder.mimeType || _voiceMimeType || 'audio/webm';
    _voiceRecorder.ondataavailable = e => { if (e.data.size > 0) _voiceChunks.push(e.data); };
    _voiceRecorder.start();
    _voiceStartTs = Date.now();
    document.getElementById('chat-input-bar').style.display = 'none';
    document.getElementById('chat-voice-recording-bar').style.display = 'flex';
    _voiceTimerInterval = setInterval(() => {
      const sec = Math.floor((Date.now() - _voiceStartTs) / 1000);
      document.getElementById('chat-voice-rec-timer').textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
    }, 200);
    hapticImpact('light');
  } catch (e) {
    showToast('Нет доступа к микрофону: ' + e.message, 'error');
  }
}

function _stopVoiceRecording(send) {
  if (!_voiceRecorder) return;
  clearInterval(_voiceTimerInterval);
  document.getElementById('chat-input-bar').style.display = 'flex';
  document.getElementById('chat-voice-recording-bar').style.display = 'none';

  const recorder = _voiceRecorder;
  _voiceRecorder = null;
  recorder.stream.getTracks().forEach(t => t.stop());

  if (!send) { recorder.stop(); return; }

  recorder.onstop = async () => {
    const blob = new Blob(_voiceChunks, { type: _voiceMimeType || 'audio/webm' });
    if (blob.size < 500) return; // слишком короткая запись, игнорируем
    await _sendVoiceMessage(blob);
  };
  recorder.stop();
}

async function _sendVoiceMessage(blob) {
  try {
    const ext = (blob.type || '').includes('mp4') ? 'm4a' : (blob.type || '').includes('ogg') ? 'ogg' : 'webm';
    const formData = new FormData();
    formData.append('file', blob, `voice.${ext}`);
    if (_voiceRecordingThreadKey) formData.append('thread_key', _voiceRecordingThreadKey);
    else formData.append('to_user_id', _voiceRecordingThread || '');
    const res = await fetch(`${API_BASE}/api/chat/messages/voice`, {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    _chatLastRenderSig = null;
    await _loadChatMessages(true);
    hapticImpact('medium');
  } catch (e) {
    showToast('Ошибка отправки голосового: ' + e.message, 'error');
  }
}
