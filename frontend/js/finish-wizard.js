// Finish-shift wizard (B3, 27.07). Отдельный файл от checkin.js -- не смешиваем с
// существующим checkin-preview-modal (тот остаётся для start-shift, более простой flow).
// 6 шагов: Фото -> Что сделано -> Доп.работы -> Потребности/проблемы -> Гео финиша -> Сводка.
let _fwVoiceNoteFileId = ''; // 28.07: owner request -- голосовое "Что сделано" сохраняется как аудио, не только текстом
// Voice-ввод на шагах 2-4 через /api/transcribe (см. B4). AI/voice текст всегда editable,
// ничего не отправляется без явного подтверждения юзера (owner requirement).

let _fwStep = 1;
const FW_TOTAL_STEPS = 6;
let _fwSessionId = null;
let _fwObjectId = null;
let _fwPhotos = []; // File[]
let _fwWorkSummary = '';
let _fwExtraWorks = []; // [{description, zone, time_estimate, needs_approval}]
let _fwNeeds = []; // [{category, description}]
let _fwDefects = []; // [{description}]
let _fwPauseMinutes = 30;
let _fwFinishGeo = null; // {lat, lon}
// 03.08 (ТЗ Задача 1): персистентный на весь wizard-flow idempotency key -- раньше
// генерировался заново на КАЖДЫЙ вызов _fwSubmitFinish(), так что retry после сетевой
// ошибки/таймаута слал НОВЫЙ ключ и backend не мог распознать повтор того же запроса
// (двойное списание фото-загрузки/двойная запись сессии при повторной отправке).
// Сбрасывается только при открытии нового wizard-flow (openFinishShiftWizard), не при
// каждой попытке отправки.
let _fwIdempotencyKey = null;

const FW_NEED_CATEGORIES = [
  { key: 'materials', label: 'Материалы' },
  { key: 'tool', label: 'Инструмент' },
  { key: 'ppe', label: 'СИЗ' },
  { key: 'access', label: 'Доступ' },
  { key: 'other', label: 'Другое' },
];

function openFinishShiftWizard(sessionId, objectId) {
  _fwStep = 1;
  _fwSessionId = sessionId;
  _fwObjectId = objectId;
  _fwPhotos = [];
  _fwWorkSummary = '';
  _fwExtraWorks = [];
  _fwNeeds = [];
  _fwDefects = [];
  _fwIdempotencyKey = null; // новый wizard-flow -- новый ключ на первую попытку
  // 28.07: owner report -- было захардкожено 30 минут независимо от реальной паузы,
  // и нигде не показывалось в сводке. Читаем реально накопленное время паузы из
  // активной сессии (тот же источник, что checkin.js уже использует для старого flow).
  const activeSession = typeof _getActiveCheckinSession === 'function' ? _getActiveCheckinSession(objectId) : null;
  _fwPauseMinutes = Math.round((activeSession?.pauseAccumulatedSeconds || 0) / 60);
  _fwFinishGeo = null;
  document.getElementById('finish-wizard-modal').style.display = 'flex';
  _fwRenderStep();
}

function _fwCloseWizard() {
  if (_fwStep > 1 && !confirm('Прервать завершение смены? Введённые данные будут потеряны.')) return;
  document.getElementById('finish-wizard-modal').style.display = 'none';
}

function _fwGoToStep(n) {
  if (n < 1 || n > FW_TOTAL_STEPS) return;
  _fwStep = n;
  _fwRenderStep();
}

function _fwRenderStep() {
  const body = document.getElementById('finish-wizard-body');
  const progressEl = document.getElementById('finish-wizard-progress');
  const titleEl = document.getElementById('finish-wizard-title');
  progressEl.textContent = `Шаг ${_fwStep} из ${FW_TOTAL_STEPS}`;

  const titles = ['', 'Фото результата', 'Что сделано', 'Доп. работы', 'Потребности и проблемы', 'Геолокация', 'Сводка'];
  titleEl.textContent = titles[_fwStep];

  if (_fwStep === 1) body.innerHTML = _fwRenderStep1();
  else if (_fwStep === 2) body.innerHTML = _fwRenderStep2();
  else if (_fwStep === 3) body.innerHTML = _fwRenderStep3();
  else if (_fwStep === 4) body.innerHTML = _fwRenderStep4();
  else if (_fwStep === 5) body.innerHTML = _fwRenderStep5();
  else if (_fwStep === 6) body.innerHTML = _fwRenderStep6();

  _fwWireStep();
}

// ---------- Step 1: Фото ----------
function _fwRenderStep1() {
  const thumbs = _fwPhotos.map((f, i) => `
    <div class="fw-photo-thumb">
      <img src="${URL.createObjectURL(f)}" alt="фото ${i + 1}">
      <button class="fw-photo-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');
  const enough = _fwPhotos.length >= 2;
  return `
    <div class="fw-hint">Сделай минимум 2 фото с разных ракурсов. Лучше 3-5 фото.</div>
    <div class="fw-photo-grid">${thumbs}</div>
    <button class="fw-add-photo-btn" id="fw-add-photo-btn" type="button">+ Добавить фото</button>
    <input type="file" id="fw-photo-input" accept="image/*" capture="environment" multiple style="display:none;">
    <button class="submit-btn fw-next-btn" id="fw-next-1" type="button" ${enough ? '' : 'disabled'}>Далее (${_fwPhotos.length}/2 фото минимум)</button>
  `;
}

function _fwWireStep1() {
  document.getElementById('fw-add-photo-btn')?.addEventListener('click', () => {
    document.getElementById('fw-photo-input')?.click();
  });
  document.getElementById('fw-photo-input')?.addEventListener('change', e => {
    _fwPhotos = _fwPhotos.concat(Array.from(e.target.files)).slice(0, 6);
    _fwRenderStep();
  });
  document.querySelectorAll('.fw-photo-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      _fwPhotos.splice(Number(btn.dataset.idx), 1);
      _fwRenderStep();
    });
  });
  document.getElementById('fw-next-1')?.addEventListener('click', () => {
    if (_fwPhotos.length < 2) return;
    _fwGoToStep(2);
  });
}

// ---------- Step 2: Что сделано (voice) ----------
function _fwRenderStep2() {
  return `
    <div class="fw-hint">Опиши, что сделано за смену. Текстом или голосом.</div>
    <textarea id="fw-work-summary" class="mangel-textarea" rows="4" placeholder="Например: оштукатурили стену в комнате 2, установили 3 окна">${esc(_fwWorkSummary)}</textarea>
    ${_fwVoiceButtonHtml('fw-voice-summary')}
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-2" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-2" type="button">Далее</button>
    </div>
  `;
}

function _fwWireStep2() {
  const textarea = document.getElementById('fw-work-summary');
  textarea?.addEventListener('input', () => { _fwWorkSummary = textarea.value; });
  _fwWireVoiceButton('fw-voice-summary', (text, fileId) => {
    textarea.value = (textarea.value ? textarea.value + ' ' : '') + text;
    _fwWorkSummary = textarea.value;
    if (fileId) _fwVoiceNoteFileId = fileId;
  });
  document.getElementById('fw-back-2')?.addEventListener('click', () => _fwGoToStep(1));
  document.getElementById('fw-next-2')?.addEventListener('click', () => {
    _fwWorkSummary = textarea.value.trim();
    _fwGoToStep(3);
  });
}

// ---------- Step 3: Доп. работы (structured list) ----------
function _fwRenderStep3() {
  const itemsHtml = _fwExtraWorks.map((w, i) => `
    <div class="fw-list-item" data-idx="${i}">
      <div class="fw-list-item-desc">${esc(w.description)}</div>
      <div class="fw-list-item-meta">${w.zone ? esc(w.zone) + ' · ' : ''}${w.time_estimate ? esc(w.time_estimate) : ''}${w.needs_approval ? ' · нужно согласование' : ''}</div>
      <button class="fw-list-item-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');
  return `
    <div class="fw-hint">Были ли доп. работы вне плана?</div>
    <div class="fw-list">${itemsHtml || '<div class="fw-empty">Пока не добавлено</div>'}</div>
    <div id="fw-extra-work-form" style="display:none;">
      <textarea id="fw-extra-desc" class="mangel-textarea" rows="2" placeholder="Описание работы"></textarea>
      ${_fwVoiceButtonHtml('fw-voice-extra')}
      <input type="text" id="fw-extra-zone" class="mangel-select" placeholder="Зона/комната (опционально)" style="margin-top:0.5rem;">
      <input type="text" id="fw-extra-time" class="mangel-select" placeholder="Примерное время (опционально)" style="margin-top:0.5rem;">
      <label class="fw-checkbox-label"><input type="checkbox" id="fw-extra-approval"> Нужно согласование с владельцем</label>
      <button class="submit-btn" id="fw-extra-save" type="button" style="margin-top:0.5rem;">Добавить пункт</button>
    </div>
    <button class="fw-add-photo-btn" id="fw-add-extra-btn" type="button">+ Добавить работу</button>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-3" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-3" type="button">Далее</button>
    </div>
  `;
}

function _fwWireStep3() {
  document.getElementById('fw-add-extra-btn')?.addEventListener('click', () => {
    document.getElementById('fw-extra-work-form').style.display = 'block';
  });
  _fwWireVoiceButton('fw-voice-extra', text => {
    const ta = document.getElementById('fw-extra-desc');
    ta.value = (ta.value ? ta.value + ' ' : '') + text;
  });
  document.getElementById('fw-extra-save')?.addEventListener('click', () => {
    const desc = document.getElementById('fw-extra-desc').value.trim();
    if (!desc) return;
    _fwExtraWorks.push({
      description: desc,
      zone: document.getElementById('fw-extra-zone').value.trim(),
      time_estimate: document.getElementById('fw-extra-time').value.trim(),
      needs_approval: document.getElementById('fw-extra-approval').checked,
    });
    _fwRenderStep();
  });
  document.querySelectorAll('.fw-list-item-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      _fwExtraWorks.splice(Number(btn.dataset.idx), 1);
      _fwRenderStep();
    });
  });
  document.getElementById('fw-back-3')?.addEventListener('click', () => _fwGoToStep(2));
  document.getElementById('fw-next-3')?.addEventListener('click', () => _fwGoToStep(4));
}

// ---------- Step 4: Потребности/проблемы (structured, categorized) ----------
function _fwRenderStep4() {
  const catButtons = FW_NEED_CATEGORIES.map(c =>
    `<button class="fw-cat-btn" data-cat="${c.key}" type="button">${esc(c.label)}</button>`).join('');
  const needsHtml = _fwNeeds.map((n, i) => `
    <div class="fw-list-item" data-idx="${i}">
      <div class="fw-list-item-desc">${esc(FW_NEED_CATEGORIES.find(c => c.key === n.category)?.label || n.category)}: ${esc(n.description)}</div>
      <button class="fw-need-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');
  const defectsHtml = _fwDefects.map((d, i) => `
    <div class="fw-list-item" data-idx="${i}">
      <div class="fw-list-item-desc">⚠️ ${esc(d.description)}</div>
      <button class="fw-defect-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');
  return `
    <div class="fw-hint">Что мешало работе или что нужно?</div>
    <div class="fw-cat-row">${catButtons}</div>
    <div id="fw-need-form" style="display:none;">
      <textarea id="fw-need-desc" class="mangel-textarea" rows="2" placeholder="Опиши, что нужно"></textarea>
      ${_fwVoiceButtonHtml('fw-voice-need')}
      <button class="submit-btn" id="fw-need-save" type="button" style="margin-top:0.5rem;">Добавить</button>
    </div>
    <div class="fw-list">${needsHtml}</div>
    <div class="fw-hint" style="margin-top:0.75rem;">Дефекты, которые заметил:</div>
    <div id="fw-defect-form" style="display:none;">
      <textarea id="fw-defect-desc" class="mangel-textarea" rows="2" placeholder="Опиши дефект"></textarea>
      ${_fwVoiceButtonHtml('fw-voice-defect')}
      <button class="submit-btn" id="fw-defect-save" type="button" style="margin-top:0.5rem;">Добавить дефект</button>
    </div>
    <div class="fw-list">${defectsHtml}</div>
    <button class="fw-add-photo-btn" id="fw-add-defect-btn" type="button">+ Сообщить о дефекте</button>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-4" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-4" type="button">Далее</button>
    </div>
  `;
}

let _fwPendingNeedCategory = null;

function _fwWireStep4() {
  document.querySelectorAll('.fw-cat-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _fwPendingNeedCategory = btn.dataset.cat;
      document.getElementById('fw-need-form').style.display = 'block';
      document.getElementById('fw-need-desc').focus();
    });
  });
  _fwWireVoiceButton('fw-voice-need', text => {
    const ta = document.getElementById('fw-need-desc');
    ta.value = (ta.value ? ta.value + ' ' : '') + text;
  });
  document.getElementById('fw-need-save')?.addEventListener('click', () => {
    const desc = document.getElementById('fw-need-desc').value.trim();
    if (!desc || !_fwPendingNeedCategory) return;
    _fwNeeds.push({ category: _fwPendingNeedCategory, description: desc });
    _fwPendingNeedCategory = null;
    _fwRenderStep();
  });
  document.querySelectorAll('.fw-need-remove').forEach(btn => {
    btn.addEventListener('click', () => { _fwNeeds.splice(Number(btn.dataset.idx), 1); _fwRenderStep(); });
  });

  document.getElementById('fw-add-defect-btn')?.addEventListener('click', () => {
    document.getElementById('fw-defect-form').style.display = 'block';
  });
  _fwWireVoiceButton('fw-voice-defect', text => {
    const ta = document.getElementById('fw-defect-desc');
    ta.value = (ta.value ? ta.value + ' ' : '') + text;
  });
  document.getElementById('fw-defect-save')?.addEventListener('click', () => {
    const desc = document.getElementById('fw-defect-desc').value.trim();
    if (!desc) return;
    _fwDefects.push({ description: desc });
    _fwRenderStep();
  });
  document.querySelectorAll('.fw-defect-remove').forEach(btn => {
    btn.addEventListener('click', () => { _fwDefects.splice(Number(btn.dataset.idx), 1); _fwRenderStep(); });
  });

  document.getElementById('fw-back-4')?.addEventListener('click', () => _fwGoToStep(3));
  document.getElementById('fw-next-4')?.addEventListener('click', () => _fwGoToStep(5));
}

// ---------- Step 5: Геолокация финиша (обязательна) ----------
function _fwRenderStep5() {
  return `
    <div class="fw-hint">Нужна твоя геолокация, чтобы завершить смену.</div>
    <div id="fw-geo-status" class="fw-geo-status">Определяем местоположение…</div>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-5" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-5" type="button" disabled>Далее</button>
    </div>
  `;
}

async function _fwWireStep5() {
  const statusEl = document.getElementById('fw-geo-status');
  const nextBtn = document.getElementById('fw-next-5');
  document.getElementById('fw-back-5')?.addEventListener('click', () => _fwGoToStep(4));

  const geo = await _getGeolocation();
  if (geo.lat && geo.lon) {
    _fwFinishGeo = geo;
    statusEl.textContent = '📍 Местоположение определено';
    statusEl.classList.add('fw-geo-ok');
    nextBtn.disabled = false;
    nextBtn.addEventListener('click', () => _fwGoToStep(6));
  } else {
    _fwFinishGeo = null;
    statusEl.textContent = 'Включи геолокацию, чтобы завершить смену';
    statusEl.classList.add('fw-geo-error');
    const retryBtn = document.createElement('button');
    retryBtn.className = 'submit-btn';
    retryBtn.type = 'button';
    retryBtn.style.marginTop = '0.5rem';
    retryBtn.textContent = 'Повторить';
    retryBtn.addEventListener('click', () => _fwRenderStep());
    statusEl.after(retryBtn);
  }
}

// ---------- Step 6: Сводка + отправка ----------
function _fwRenderStep6() {
  const extraWorksHtml = _fwExtraWorks.length
    ? _fwExtraWorks.map(w => `<li>${esc(w.description)}${w.zone ? ' (' + esc(w.zone) + ')' : ''}</li>`).join('')
    : '<li class="fw-empty-li">Нет</li>';
  const needsHtml = _fwNeeds.length
    ? _fwNeeds.map(n => `<li>${esc(FW_NEED_CATEGORIES.find(c => c.key === n.category)?.label || n.category)}: ${esc(n.description)}</li>`).join('')
    : '<li class="fw-empty-li">Нет</li>';
  const defectsHtml = _fwDefects.length
    ? _fwDefects.map(d => `<li>⚠️ ${esc(d.description)}</li>`).join('')
    : '<li class="fw-empty-li">Нет</li>';

  return `
    <div class="fw-summary-section"><b>Фото:</b> ${_fwPhotos.length} шт.</div>
    <div class="fw-summary-section"><b>Что сделано:</b> ${esc(_fwWorkSummary) || '<span class="fw-empty-li">не указано</span>'}</div>
    <div class="fw-summary-section"><b>Доп. работы:</b><ul>${extraWorksHtml}</ul></div>
    <div class="fw-summary-section"><b>Потребности:</b><ul>${needsHtml}</ul></div>
    <div class="fw-summary-section"><b>Дефекты:</b><ul>${defectsHtml}</ul></div>
    <div class="fw-summary-section"><b>Пауза за смену:</b> ${_fwPauseMinutes > 0 ? `${_fwPauseMinutes} мин.` : 'без пауз'}</div>
    <div class="fw-summary-section"><b>Геолокация:</b> ${_fwFinishGeo ? '📍 определена' : '⚠️ не определена'}</div>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-6" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-submit-finish" type="button">Завершить смену</button>
    </div>
    <div id="fw-submit-status" class="fw-submit-status"></div>
  `;
}

function _fwWireStep6() {
  document.getElementById('fw-back-6')?.addEventListener('click', () => _fwGoToStep(5));
  document.getElementById('fw-submit-finish')?.addEventListener('click', _fwSubmitFinish);
}

async function _fwSubmitFinish() {
  const btn = document.getElementById('fw-submit-finish');
  const statusEl = document.getElementById('fw-submit-status');
  btn.disabled = true;
  btn.textContent = 'Отправка…';
  statusEl.textContent = '';

  try {
    const formData = new FormData();
    formData.append('lat', _fwFinishGeo.lat);
    formData.append('lon', _fwFinishGeo.lon);
    formData.append('done_summary', _fwWorkSummary);
    formData.append('extra_works', JSON.stringify(_fwExtraWorks));
    formData.append('needs', JSON.stringify(_fwNeeds));
    formData.append('defects', JSON.stringify(_fwDefects));
    formData.append('pause_minutes', String(_fwPauseMinutes));
    if (_fwVoiceNoteFileId) formData.append('voice_note_file_id', _fwVoiceNoteFileId);
    _fwPhotos.forEach(f => formData.append('files', f));

    // 03.08 (ТЗ Задача 1): переиспользуем ключ, если он уже был создан прошлой попыткой
    // (retry после ошибки) -- новый генерируем только на самую первую отправку.
    _fwIdempotencyKey = _fwIdempotencyKey || crypto.randomUUID();
    const res = await fetch(`${API_BASE}/api/checkin/${_fwSessionId}/finish`, {
      method: 'POST',
      headers: { ..._authHeaders(), 'Idempotency-Key': _fwIdempotencyKey },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);

    // Реальное создание Need/Mangel тикетов -- только после успешного finish,
    // явное подтверждение уже было (юзер дошёл до конца wizard и нажал "Завершить").
    // Best-effort: сбой создания тикета не должен ломать успешно завершённую смену.
    for (const need of _fwNeeds) {
      try {
        await api('/api/tasks', {
          method: 'POST',
          body: JSON.stringify({ title: need.description, object_id: _fwObjectId }),
        });
      } catch (e) { console.warn('need creation failed', e); }
    }
    for (const defect of _fwDefects) {
      try {
        const fd = new FormData();
        fd.append('object_id', _fwObjectId);
        fd.append('description', defect.description);
        await fetch(`${API_BASE}/api/mangel`, {
          method: 'POST',
          headers: { ..._authHeaders() },
          body: fd,
        });
      } catch (e) { console.warn('defect creation failed', e); }
    }

    hapticImpact('medium');
    _setActiveCheckinSession(_fwObjectId, { id: _fwSessionId, finished: true });
    document.getElementById('finish-wizard-modal').style.display = 'none';
    showToast('Смена завершена', 'success');
    if (typeof refreshCheckinButtons === 'function') refreshCheckinButtons();
    // 28.07: owner report -- завершил смену через finish-wizard, но Home-карточка
    // "Смена идёт" (worker-shift-cta, отдельный независимый источник состояния)
    // оставалась устаревшей, т.к. этот wizard никогда её не трогал -- только
    // checkin.js (старый finish-flow) синхронизировал её, finish-wizard.js не был
    // подключён к этому же обновлению. Тот же паттерн, что уже есть в checkin.js.
    if (typeof _loadWorkerShiftCta === 'function' && document.getElementById('worker-shift-cta')) {
      _loadWorkerShiftCta();
    }
  } catch (e) {
    statusEl.textContent = 'Ошибка: ' + e.message;
    statusEl.classList.add('fw-submit-error');
    btn.disabled = false;
    btn.textContent = 'Завершить смену';
  }
}

// ---------- Voice input (общий для шагов 2-4) ----------
function _fwVoiceButtonHtml(id) {
  return `<button class="fw-voice-btn" id="${id}" type="button" data-state="idle">🎤 Голосом</button>`;
}

let _fwActiveRecorder = null;

function _fwWireVoiceButton(btnId, onTranscript) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.addEventListener('click', async () => {
    if (btn.dataset.state === 'recording') {
      _fwActiveRecorder?.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      showToast('Запись голоса не поддерживается', 'error');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const recorder = new MediaRecorder(stream);
      _fwActiveRecorder = recorder;
      recorder.ondataavailable = e => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        btn.dataset.state = 'transcribing';
        btn.textContent = 'Распознаю…';
        const blob = new Blob(chunks, { type: 'audio/webm' });
        try {
          const fd = new FormData();
          fd.append('file', blob, 'voice.webm');
          const res = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST',
            headers: { ..._authHeaders() },
            body: fd,
          });
          if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
          const data = await res.json();
          onTranscript(data.raw_transcript || '', data.file_id || '');
        } catch (e) {
          showToast('Не удалось распознать голос: ' + e.message, 'error');
        } finally {
          btn.dataset.state = 'idle';
          btn.textContent = '🎤 Голосом';
        }
      };
      recorder.start();
      btn.dataset.state = 'recording';
      btn.textContent = '⏹ Остановить запись';
    } catch (e) {
      showToast('Нет доступа к микрофону', 'error');
    }
  });
}

function _fwWireStep() {
  if (_fwStep === 1) _fwWireStep1();
  else if (_fwStep === 2) _fwWireStep2();
  else if (_fwStep === 3) _fwWireStep3();
  else if (_fwStep === 4) _fwWireStep4();
  else if (_fwStep === 5) _fwWireStep5();
  else if (_fwStep === 6) _fwWireStep6();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('finish-wizard-close')?.addEventListener('click', _fwCloseWizard);
});
