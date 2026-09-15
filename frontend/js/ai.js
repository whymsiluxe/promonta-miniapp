// Таб "ИИ" — чат с GLM-4.5-Flash ассистентом (api.z.ai, Anthropic-compatible).
// Решение: GLM бесплатный — не тратим Claude Pro лимиты владельца.
// Только для owner; rate limit 20 запросов/час (отслеживается на backend).

let _aiMessages = []; // {role: 'user'|'assistant', content: string | contentBlock[]}
let _aiPendingFile = null; // {kind: 'image'|'text', filename, block?, text?}

function _escAi(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _formatAiText(text) {
  return _escAi(text)
    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--bg-light);padding:1px 4px;border-radius:3px;font-size:0.85em">$1</code>')
    .replace(/\n/g, '<br>');
}

function _renderAiMessages() {
  const container = document.getElementById('ai-messages');
  if (!container) return;

  if (_aiMessages.length === 0) {
    container.innerHTML = `
      <div class="ai-empty">Спрашивай что угодно: объекты, тексты клиентам, расчёты, немецкие письма... 🤖</div>
      <div class="ai-suggestion-chips">
        <div class="ai-suggestion-chip" data-ai-suggest="Проанализируй фото последнего объекта">📸 Проанализировать фото объекта</div>
        <div class="ai-suggestion-chip" data-ai-suggest="Переведи это на немецкий: ">🇩🇪 Перевести на немецкий</div>
        <div class="ai-suggestion-chip" data-ai-suggest="Составь текст клиенту про ">✉️ Написать клиенту</div>
        <div class="ai-suggestion-chip" data-ai-suggest="Что нового по бюджету на объектах?">💰 Что по бюджету?</div>
      </div>`;
    container.querySelectorAll('[data-ai-suggest]').forEach(chip => {
      chip.addEventListener('click', () => {
        const input = document.getElementById('ai-input');
        if (input) { input.value = chip.dataset.aiSuggest; input.focus({ preventScroll: true }); }
      });
    });
    return;
  }

  container.innerHTML = _aiMessages.map(msg => {
    let bodyHtml;
    if (Array.isArray(msg.content)) {
      bodyHtml = msg.content.map(block => {
        if (block.type === 'image') {
          return `<img class="ai-attached-img" src="data:${block.source.media_type};base64,${block.source.data}">`;
        }
        return `<div class="ai-text">${msg.role === 'assistant' ? _formatAiText(block.text) : _escAi(block.text)}</div>`;
      }).join('');
    } else {
      bodyHtml = `<div class="ai-text">${msg.role === 'assistant' ? _formatAiText(msg.content) : _escAi(msg.content)}</div>`;
    }
    return `<div class="ai-bubble ai-bubble-${msg.role}">${bodyHtml}</div>`;
  }).join('');

  _scrollChatToBottom(container.id);
}

async function _handleAiFileSelect(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;

  const preview = document.getElementById('ai-attach-preview');
  preview.innerHTML = `<span class="ai-attach-loading">Загрузка ${_escAi(file.name)}...</span>`;
  preview.style.display = 'flex';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(API_BASE + '/api/ai-chat/upload', {
      method: 'POST',
      headers: { ..._authHeaders() },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    _aiPendingFile = data;

    const thumb = data.kind === 'image'
      ? `<img class="ai-attach-thumb" src="data:${data.block.source.media_type};base64,${data.block.source.data}">`
      : `<div class="ai-attach-icon">📄</div>`;

    preview.innerHTML = `
      ${thumb}
      <span class="ai-attach-name">${_escAi(data.filename)}</span>
      <button class="ai-attach-remove" id="ai-attach-remove" aria-label="Убрать файл">×</button>`;
    document.getElementById('ai-attach-remove').addEventListener('click', () => {
      _aiPendingFile = null;
      preview.style.display = 'none';
      preview.innerHTML = '';
    });
  } catch (err) {
    preview.innerHTML = `<span class="ai-attach-error">Ошибка: ${_escAi(err.message)}</span>`;
    setTimeout(() => { preview.style.display = 'none'; preview.innerHTML = ''; _aiPendingFile = null; }, 4000);
  }
}

async function _sendAiMessage() {
  const input = document.getElementById('ai-input');
  const btn = document.getElementById('ai-send');
  const text = input.value.trim();
  if ((!text && !_aiPendingFile) || (btn && btn.disabled)) return;

  let content;
  if (_aiPendingFile) {
    const blocks = [];
    if (_aiPendingFile.kind === 'image') {
      blocks.push(_aiPendingFile.block);
      blocks.push({ type: 'text', text: text || 'Что на этом фото?' });
    } else {
      blocks.push({ type: 'text', text: `Файл "${_aiPendingFile.filename}":\n\n${_aiPendingFile.text}\n\n---\n${text || 'Проанализируй этот файл.'}` });
    }
    content = blocks;
    _aiPendingFile = null;
    const preview = document.getElementById('ai-attach-preview');
    preview.style.display = 'none';
    preview.innerHTML = '';
  } else {
    content = text;
  }

  _aiMessages.push({ role: 'user', content });
  input.value = '';
  input.style.height = 'auto';
  _renderAiMessages();

  // 09.09: input.disabled=true убран -- тот же баг что был в _sendChatMessage
  // (chat.js) -- disabled на элементе в фокусе форсирует blur на iOS, клавиатура
  // закрывается на каждую отправку. Кнопку по-прежнему можно дизейблить (не в фокусе).
  btn.disabled = true;

  const container = document.getElementById('ai-messages');
  const typingId = 'ai-typing-' + Date.now();
  container.insertAdjacentHTML('beforeend',
    `<div id="${typingId}" class="ai-bubble ai-bubble-assistant ai-typing">●●●</div>`
  );
  _scrollChatToBottom(container.id);

  try {
    const data = await api('/api/ai-chat', {
      method: 'POST',
      body: JSON.stringify({ messages: _aiMessages }),
    });

    document.getElementById(typingId)?.remove();
    _aiMessages.push({ role: 'assistant', content: data.reply });
    _renderAiMessages();
    hapticImpact('light');
  } catch (e) {
    document.getElementById(typingId)?.remove();
    const errDiv = document.createElement('div');
    errDiv.className = 'ai-bubble ai-bubble-error';
    errDiv.textContent = '⚠️ ' + e.message;
    container.appendChild(errDiv);
    _scrollChatToBottom(container.id);
    // Remove failed user message so user can retry
    _aiMessages.pop();
  } finally {
    btn.disabled = false;
    input.focus({ preventScroll: true });
  }
}

function _clearAiChat() {
  _aiMessages = [];
  _renderAiMessages();
}

const AI_MODEL_LABELS = { glm: 'GLM', sonnet: 'Sonnet', opus: 'Opus' };

async function _initAiModelSelect() {
  const sel = document.getElementById('ai-model-select');
  if (!sel) return;
  try {
    const data = await api('/api/ai-model');
    sel.innerHTML = data.available.map(m =>
      `<option value="${m}"${m === data.model ? ' selected' : ''}>${AI_MODEL_LABELS[m] || m}</option>`
    ).join('');
  } catch (e) {
    sel.innerHTML = '<option>?</option>';
  }

  sel.addEventListener('change', async () => {
    const model = sel.value;
    try {
      await api('/api/ai-model', { method: 'POST', body: JSON.stringify({ model }) });
      hapticImpact('light');
    } catch (e) {
      showToast('Не удалось сменить модель: ' + e.message, 'error');
    }
  });
}

let _aiManagerCommandClose = null;

function _closeAiManagerCommandSheet() {
  if (_aiManagerCommandClose) {
    const close = _aiManagerCommandClose;
    _aiManagerCommandClose = null;
    close();
  }
}

function _aiManagerCommandDraftHtml(draft) {
  const rows = [
    ['Работник', draft.worker_name || draft.worker_query || ''],
    ['Дата', draft.date || draft.date_text || ''],
    ['Объект', draft.object_name || draft.object_query || ''],
    ['Задача', draft.task || ''],
    ['Комментарий', draft.comment || ''],
  ].filter(row => row[1]);
  return `
    <div class="ai-manager-command-draft-title">Черновик команды</div>
    ${rows.map(row => `
      <div class="ai-manager-command-draft-row">
        <span>${_escAi(row[0])}</span>
        <strong>${_escAi(row[1])}</strong>
      </div>
    `.trim()).join('')}
    ${draft.requires_confirmation ? '<div class="ai-manager-command-draft-row"><span>Статус</span><strong>нужно подтвердить</strong></div>' : ''}`;
}

async function _parseAiManagerCommand(modal) {
  const textEl = modal.querySelector('#ai-manager-command-text');
  const submitBtn = modal.querySelector('#ai-manager-command-parse');
  const draftEl = modal.querySelector('#ai-manager-command-draft');
  const text = textEl?.value.trim() || '';
  if (!text) {
    showToast('Введите команду', 'error');
    return;
  }
  submitBtn.disabled = true;
  draftEl.classList.remove('show');
  draftEl.innerHTML = '';
  try {
    const result = await api('/api/manager/command/parse', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
    draftEl.innerHTML = _aiManagerCommandDraftHtml(result.draft || {});
    draftEl.classList.add('show');
    hapticImpact('light');
  } catch (e) {
    showToast('Команда не разобрана: ' + e.message, 'error');
  } finally {
    submitBtn.disabled = false;
  }
}

function _openAiManagerCommandSheet() {
  _closeAiManagerCommandSheet();
  const backdrop = document.createElement('div');
  backdrop.className = 'chat-forward-modal-backdrop ai-manager-command-backdrop';
  const modal = document.createElement('div');
  modal.className = 'chat-forward-modal chat-forward-sheet ai-manager-command-sheet';
  modal.innerHTML = `
    <div class="chat-action-sheet-handle"></div>
    <div class="chat-forward-modal-title">Команда руководителя</div>
    <div class="ai-manager-command-form">
      <div class="ai-manager-command-field">
        <textarea id="ai-manager-command-text" class="ai-manager-command-text" placeholder="Поставь Ивану завтра задачу закончить потолок у Мюллера и скажи ему взять лазер"></textarea>
        <button id="ai-manager-command-voice" class="ai-manager-command-voice" type="button" aria-label="Продиктовать команду">
          <svg viewBox="0 0 24 24" width="17" height="17"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3M8.5 21h7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
      </div>
      <button id="ai-manager-command-parse" class="ai-manager-command-submit" type="button">Разобрать</button>
      <div id="ai-manager-command-draft" class="ai-manager-command-draft"></div>
    </div>`;
  document.body.appendChild(backdrop);
  document.body.appendChild(modal);

  let unregister = null;
  const onKeydown = e => { if (e.key === 'Escape') close(); };
  const close = () => {
    backdrop.remove();
    modal.remove();
    document.removeEventListener('keydown', onKeydown);
    if (unregister) { unregister(); unregister = null; }
    if (_aiManagerCommandClose === close) _aiManagerCommandClose = null;
  };
  _aiManagerCommandClose = close;
  if (typeof NavigationManager !== 'undefined') unregister = NavigationManager.registerOverlay(close);
  document.addEventListener('keydown', onKeydown);
  backdrop.addEventListener('pointerdown', e => { e.preventDefault(); close(); });
  backdrop.addEventListener('click', close);
  modal.addEventListener('pointerdown', e => e.stopPropagation());

  modal.querySelector('#ai-manager-command-parse').addEventListener('click', () => _parseAiManagerCommand(modal));
  const voiceBtn = modal.querySelector('#ai-manager-command-voice');
  if (typeof attachVoiceInputButton === 'function') {
    attachVoiceInputButton(voiceBtn, transcript => {
      const textEl = modal.querySelector('#ai-manager-command-text');
      if (textEl) textEl.value = transcript;
      _parseAiManagerCommand(modal);
    });
  } else if (voiceBtn) {
    voiceBtn.style.display = 'none';
  }
  modal.querySelector('#ai-manager-command-text')?.focus({ preventScroll: true });
}

function _bindAiManagerCommandEntry() {
  const btn = document.getElementById('ai-manager-command-btn');
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = '1';
  btn.addEventListener('click', _openAiManagerCommandSheet);
}

function initAiView() {
  const view = document.getElementById('view-ai');
  if (!view) return;

  if (currentRole !== 'owner') {
    view.innerHTML = '<div class="no-access">🔒 Чат с ИИ — только для владельца</div>';
    return;
  }

  _renderAiMessages();
  _initAiModelSelect();
  _bindAiManagerCommandEntry();
  // 09.09 v11c: тот же ResizeObserver что chat.js -- --chat-composer-height
  // общая переменная для .chat-input-bar/.ai-input-bar (CSS), но текущий bar
  // (общий или ИИ) может отличаться по высоте -- наблюдаем именно активный.
  if (typeof _observeChatComposerHeight === 'function') {
    _observeChatComposerHeight(document.querySelector('.ai-input-bar'));
  }

  const sendBtn = document.getElementById('ai-send');
  const clearBtn = document.getElementById('ai-clear');
  const input = document.getElementById('ai-input');
  const fileInput = document.getElementById('ai-file-input');

  // 09.09 v10: touch-safe send (см. shared.js _bindTouchSafeSend) -- pointerdown
  // preventDefault один не спасал на реальном Telegram iOS WKWebView, замена тем же
  // подходом что chat.js.
  _bindTouchSafeSend(sendBtn, input, _sendAiMessage);
  clearBtn.addEventListener('click', _clearAiChat);
  if (fileInput) {
    fileInput.addEventListener('change', _handleAiFileSelect);
  }

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _sendAiMessage();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });
}
