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
        if (input) { input.value = chip.dataset.aiSuggest; input.focus(); }
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

  container.scrollTop = container.scrollHeight;
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
      headers: { 'X-Telegram-Init-Data': initData },
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
  if (!text && !_aiPendingFile) return;

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

  btn.disabled = true;
  input.disabled = true;

  const container = document.getElementById('ai-messages');
  const typingId = 'ai-typing-' + Date.now();
  container.insertAdjacentHTML('beforeend',
    `<div id="${typingId}" class="ai-bubble ai-bubble-assistant ai-typing">●●●</div>`
  );
  container.scrollTop = container.scrollHeight;

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
    container.scrollTop = container.scrollHeight;
    // Remove failed user message so user can retry
    _aiMessages.pop();
  } finally {
    btn.disabled = false;
    input.disabled = false;
    input.focus();
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

function initAiView() {
  const view = document.getElementById('view-ai');
  if (!view) return;

  if (currentRole !== 'owner') {
    view.innerHTML = '<div class="no-access">🔒 Чат с ИИ — только для владельца</div>';
    return;
  }

  _renderAiMessages();
  _initAiModelSelect();

  const sendBtn = document.getElementById('ai-send');
  const clearBtn = document.getElementById('ai-clear');
  const input = document.getElementById('ai-input');
  const fileInput = document.getElementById('ai-file-input');

  sendBtn.addEventListener('click', _sendAiMessage);
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
