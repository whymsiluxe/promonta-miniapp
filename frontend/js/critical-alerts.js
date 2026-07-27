// Глобальный попап критических алертов (Фаза 10.16) — крутится независимо от того,
// какой view открыт, поверх всего приложения. Polling — тот же паттерн, что чат
// (см. CHAT_UNREAD_POLL_MS в chat.js), без WebSocket.

const CRITICAL_ALERT_POLL_MS = 15000;
let _criticalAlertModalOpen = false;
let _criticalAlertQueue = [];
let _criticalAlertPollTimer = null;

function initCriticalAlertsPolling() {
  if (_criticalAlertPollTimer) return;
  _pollCriticalAlerts();
  _criticalAlertPollTimer = setInterval(_pollCriticalAlerts, CRITICAL_ALERT_POLL_MS);
}

async function _pollCriticalAlerts() {
  try {
    const data = await api('/api/critical-alerts/pending');
    _criticalAlertQueue = data.alerts || [];
    if (_criticalAlertQueue.length && !_criticalAlertModalOpen) {
      _showCriticalAlertModal(_criticalAlertQueue[0]);
    }
  } catch (e) {}
}

function _showCriticalAlertModal(alert) {
  _criticalAlertModalOpen = true;
  const now = Math.floor(Date.now() / 1000);
  const isResolutionPrompt = alert.deadline_at && now >= alert.deadline_at && !alert.resolution;

  const modal = document.createElement('div');
  modal.id = 'critical-alert-modal';
  modal.innerHTML = isResolutionPrompt ? _criticalAlertResolutionHtml(alert) : _criticalAlertAckHtml(alert);
  document.body.appendChild(modal);
  hapticImpact('heavy');

  if (isResolutionPrompt) {
    document.getElementById('ca-resolve-yes').addEventListener('click', () => _resolveCriticalAlert(alert.id, 'yes'));
    document.getElementById('ca-resolve-no').addEventListener('click', () => _showCriticalAlertResolveNoForm(alert.id));
  } else {
    document.getElementById('ca-ack-btn').addEventListener('click', () => _ackCriticalAlert(alert.id));
  }
}

function _criticalAlertAckHtml(alert) {
  return `
    <div class="critical-alert-inner">
      <div class="critical-alert-icon">🔴</div>
      <div class="critical-alert-title">${esc(alert.title)}</div>
      ${alert.subtitle ? `<div class="critical-alert-subtitle">${esc(alert.subtitle)}</div>` : ''}
      <textarea id="ca-comment-input" class="critical-alert-comment" placeholder="Комментарий (опционально)…" rows="3"></textarea>
      <button class="critical-alert-btn critical-alert-btn-primary" id="ca-ack-btn">Принял</button>
    </div>`;
}

function _criticalAlertResolutionHtml(alert) {
  return `
    <div class="critical-alert-inner">
      <div class="critical-alert-icon">⏰</div>
      <div class="critical-alert-title">Вопрос решён?</div>
      <div class="critical-alert-subtitle">${esc(alert.title)}</div>
      <div class="critical-alert-actions-row">
        <button class="critical-alert-btn critical-alert-btn-yes" id="ca-resolve-yes">Да</button>
        <button class="critical-alert-btn critical-alert-btn-no" id="ca-resolve-no">Нет</button>
      </div>
    </div>`;
}

async function _ackCriticalAlert(alertId) {
  const comment = document.getElementById('ca-comment-input')?.value.trim() || '';
  try {
    await api(`/api/critical-alerts/${alertId}/ack`, {
      method: 'POST',
      body: JSON.stringify({ comment }),
    });
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    return;
  }
  _closeCriticalAlertModal();
}

function _showCriticalAlertResolveNoForm(alertId) {
  const inner = document.querySelector('#critical-alert-modal .critical-alert-inner');
  inner.innerHTML = `
    <div class="critical-alert-icon">✍️</div>
    <div class="critical-alert-title">Укажите причину</div>
    <textarea id="ca-resolve-note-input" class="critical-alert-comment" placeholder="Почему вопрос не решён…" rows="3"></textarea>
    <button class="critical-alert-btn critical-alert-btn-primary" id="ca-resolve-no-submit">Отправить</button>
  `;
  document.getElementById('ca-resolve-no-submit').addEventListener('click', async () => {
    const note = document.getElementById('ca-resolve-note-input').value.trim();
    if (!note) { showToast('Укажите причину', 'error'); return; }
    await _submitCriticalAlertResolution(alertId, 'no', note, []);
  });
}

async function _resolveCriticalAlert(alertId, resolution) {
  if (resolution === 'yes') {
    _criticalAlertPendingResolveId = alertId;
    document.getElementById('critical-alert-camera-input').click();
    return;
  }
}

let _criticalAlertPendingResolveId = null;

async function _handleCriticalAlertPhotos(files) {
  if (!_criticalAlertPendingResolveId || !files.length) return;
  await _submitCriticalAlertResolution(_criticalAlertPendingResolveId, 'yes', '', files);
  _criticalAlertPendingResolveId = null;
}

async function _submitCriticalAlertResolution(alertId, resolution, note, files) {
  try {
    const formData = new FormData();
    formData.append('resolution', resolution);
    formData.append('note', note);
    for (const f of files) formData.append('files', f);
    const res = await fetch(`${API_BASE}/api/critical-alerts/${alertId}/resolve`, {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    hapticImpact('medium');
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    return;
  }
  _closeCriticalAlertModal();
}

function _closeCriticalAlertModal() {
  const modal = document.getElementById('critical-alert-modal');
  if (modal) modal.remove();
  _criticalAlertModalOpen = false;
  _criticalAlertQueue.shift();
  if (_criticalAlertQueue.length) {
    setTimeout(() => _showCriticalAlertModal(_criticalAlertQueue[0]), 300);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.id = 'critical-alert-camera-input';
  input.accept = 'image/*';
  input.capture = 'environment';
  input.multiple = true;
  input.style.display = 'none';
  document.body.appendChild(input);
  input.addEventListener('change', e => {
    _handleCriticalAlertPhotos(Array.from(e.target.files));
    e.target.value = '';
  });
});
