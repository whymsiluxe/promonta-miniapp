// Таб "Чат" — командный чат команды Promonta.
// Хранение: JSON-файл на VPS (последние 200 сообщений), polling каждые 8 сек.
// Решение: WebSocket избыточен для 2-5 чел., простой polling без зависимостей.

const CHAT_POLL_MS = 8000;
let _chatPollTimer = null;
let _chatLastTs = 0;
let _chatMyId = null;
let _chatIsOwner = false;
let _chatActiveThread = null; // null = группа, иначе user_id собеседника (DM)
let _chatActiveThreadKey = null; // 10.36: чат объекта/дефекта (obj:OBJ-001 / mangel:ticket_id) — приоритет над _chatActiveThread
let _chatWorkers = [];
let _chatReturnToView = null; // 21.07: откуда открыт чат (Потребности/Дефекты) — назад должен вернуть туда, не в общий список тредов

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
    container.innerHTML = '<div class="chat-empty">Сообщений пока нет. Напишите первым! 👋</div>';
    _chatLastTs = 0;
    return;
  }

  const maxTs = Math.max(...messages.map(m => m.ts));
  if (maxTs <= _chatLastTs) return;

  const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 30;
  _chatLastTs = maxTs;

  let lastDayKey = null;
  container.innerHTML = messages.map(msg => {
    const isOwn = msg.user_id === _chatMyId;
    const dayKey = new Date(msg.ts * 1000).toDateString();
    let divider = '';
    if (dayKey !== lastDayKey) {
      divider = `<div class="chat-day-divider">${_fmtChatDayLabel(msg.ts)}</div>`;
      lastDayKey = dayKey;
    }
    return `${divider}
    <div class="chat-bubble ${isOwn ? 'chat-bubble-own' : 'chat-bubble-other'}" data-msg-id="${msg.id}" data-uid="${msg.user_id}">
      ${!isOwn ? `<div class="chat-name" style="cursor:pointer" onclick="openUserCard('${msg.user_id}')">${_escChat(msg.name)}</div>` : ''}
      ${msg.attachment ? _renderChatAttachment(msg) : ''}
      ${msg.text ? `<div class="chat-text">${_escChat(msg.text)}</div>` : ''}
      <div class="chat-time">${_fmtChatTime(msg.ts)}</div>
    </div>`;
  }).join('');

  if (wasAtBottom || messages.length === 1) {
    container.scrollTop = container.scrollHeight;
  }

  _attachChatDeleteHandlers(container);
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

function _attachChatDeleteHandlers(container) {
  container.querySelectorAll('.chat-bubble').forEach(bubble => {
    const canDelete = _chatIsOwner || Number(bubble.dataset.uid) === _chatMyId;
    if (!canDelete) return;

    bubble.addEventListener('touchstart', () => {
      _chatLongPressTimer = setTimeout(() => {
        hapticImpact('medium');
        _confirmDeleteChatMessage(bubble.dataset.msgId, bubble);
      }, 500);
    }, { passive: true });

    bubble.addEventListener('touchend', () => clearTimeout(_chatLongPressTimer));
    bubble.addEventListener('touchmove', () => clearTimeout(_chatLongPressTimer));
  });
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

async function _loadChatMessages(forceScroll) {
  try {
    const path = _chatActiveThreadKey ? `/api/chat/messages?thread_key=${encodeURIComponent(_chatActiveThreadKey)}`
      : _chatActiveThread ? `/api/chat/messages?with_=${_chatActiveThread}` : '/api/chat/messages';
    const data = await api(path);
    _renderChatMessages(data.messages || []);
    if (forceScroll) {
      const c = document.getElementById('chat-messages');
      if (c) c.scrollTop = c.scrollHeight;
    }
  } catch (e) {
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
    _chatLastTs = 0;
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
    _chatLastTs = 0;
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
    btn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

const CHAT_UNREAD_POLL_MS = 15000;
let _chatUnreadTimer = null;

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

async function _pollUnreadChat() {
  try {
    const data = await api('/api/chat/unread_count');
    _renderUnreadBadge(data.unread || 0);
  } catch (e) {}
}

function startUnreadChatPolling() {
  _pollUnreadChat();
  if (_chatUnreadTimer) clearInterval(_chatUnreadTimer);
  _chatUnreadTimer = setInterval(_pollUnreadChat, CHAT_UNREAD_POLL_MS);
}

async function markChatRead(threadUserId) {
  if (!threadUserId) _renderUnreadBadge(0);
  try {
    const qs = threadUserId ? `?with_=${threadUserId}` : '';
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
}

let _chatUnreadByThread = {};
let _chatSearchQuery = '';


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

  if (_chatCategory === 'general') {
    const t = _threadByKey('group');
    const preview = t?.last_preview ? _escChat(t.last_preview) : 'Команда Promonta';
    const time = _threadTimeLabel(t?.last_ts);
    const groupItem = `
      <div class="chat-thread-item" data-thread="">
        <div class="chat-thread-avatar group">👤</div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">Общий чат</div>
          <div class="chat-thread-preview">${preview}</div>
        </div>
        <div class="chat-thread-meta">
          ${time ? `<span class="chat-thread-time">${time}</span>` : ''}
          ${_threadBadge(_chatUnreadByThread.group || 0)}
        </div>
      </div>`;
    listEl.innerHTML = groupItem;
  } else if (_chatCategory === 'dm') {
    const filteredWorkers = q ? _chatWorkers.filter(w => (w.name || '').toLowerCase().includes(q)) : _chatWorkers;
    listEl.innerHTML = filteredWorkers.map(w => {
      const t = _threadByKey(String(w.user_id));
      const preview = t?.last_preview ? _escChat(t.last_preview) : (w.role === 'owner' ? 'Владелец' : 'Работник');
      const time = _threadTimeLabel(t?.last_ts);
      return `
      <div class="chat-thread-item" data-thread="${w.user_id}">
        <div class="chat-thread-avatar">${(w.name || '?')[0].toUpperCase()}</div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">${_escChat(w.name || w.user_id)}</div>
          <div class="chat-thread-preview">${preview}</div>
        </div>
        <div class="chat-thread-meta">
          ${time ? `<span class="chat-thread-time">${time}</span>` : ''}
          ${_threadBadge(_chatUnreadByThread[String(w.user_id)] || 0)}
        </div>
      </div>`;
    }).join('') || '<div class="chat-empty">Нет личных чатов</div>';
  } else {
    const prefix = _chatCategory === 'obj' ? 'obj:' : _chatCategory === 'mangel' ? 'mangel:' : 'task:';
    let filtered = _chatMyThreads.filter(t => t.thread_key.startsWith(prefix));
    if (q) filtered = filtered.filter(t => t.title.toLowerCase().includes(q));
    listEl.innerHTML = filtered.map(t => `
      <div class="chat-thread-item" data-thread-key="${t.thread_key}">
        <div class="chat-thread-avatar group">💬</div>
        <div class="chat-thread-info">
          <div class="chat-thread-name">${_escChat(t.title)}</div>
          <div class="chat-thread-preview">${_escChat(t.last_preview || '')}</div>
        </div>
        <div class="chat-thread-meta">
          ${_threadTimeLabel(t.last_ts) ? `<span class="chat-thread-time">${_threadTimeLabel(t.last_ts)}</span>` : ''}
        </div>
      </div>`).join('') || '<div class="chat-empty">Чатов пока нет</div>';
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
  } catch (e) {}
}

function openChatThread(threadUserId, title) {
  _chatActiveThread = threadUserId;
  _chatActiveThreadKey = null;
  document.getElementById('chat-thread-title').textContent = title;
  document.getElementById('chat-thread-list-view').style.display = 'none';
  document.getElementById('chat-thread-detail-view').style.display = 'flex';
  _chatLastTs = 0;
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
  document.getElementById('chat-close-thread-btn').style.display = 'none'; // закрытие тредов не поддержано для obj:/mangel:
  _chatLastTs = 0;
  _loadChatMessages(true);
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
  if (closeBtn) closeBtn.textContent = closed ? '' : '🔒';
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
  _chatActiveThread = null;
  _chatActiveThreadKey = null;
  if (_chatReturnToView) {
    const target = _chatReturnToView;
    _chatReturnToView = null;
    switchView(target);
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

  const searchInput = document.getElementById('chat-thread-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      _chatSearchQuery = searchInput.value;
      renderChatThreadList();
    });
  }

  document.querySelectorAll('.chat-category-tabs [data-chat-category]').forEach(tab => {
    tab.addEventListener('click', () => {
      _chatCategory = tab.dataset.chatCategory;
      document.querySelectorAll('.chat-category-tabs [data-chat-category]').forEach(t => t.classList.toggle('active', t === tab));
      renderChatThreadList();
    });
  });

  if (_chatPollTimer) clearInterval(_chatPollTimer);
  _chatPollTimer = setInterval(() => {
    if (_chatActiveThread !== null || document.getElementById('chat-thread-detail-view').style.display !== 'none') {
      _loadChatMessages(false);
    }
  }, CHAT_POLL_MS);

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
    _chatLastTs = 0;
    await _loadChatMessages(true);
    hapticImpact('medium');
  } catch (e) {
    showToast('Ошибка отправки голосового: ' + e.message, 'error');
  }
}
