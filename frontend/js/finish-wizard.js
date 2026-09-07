// Finish-shift wizard (B3, 27.07). Отдельный файл от checkin.js -- не смешиваем с
// существующим checkin-preview-modal (тот остаётся для start-shift, более простой flow).
// Round 3 (07.09): динамическая последовательность шагов -- без плана 6 шагов,
// с планом 8 шагов (добавляется plan-fact + tomorrow-prep).
let _fwVoiceNoteFileId = ''; // 28.07: owner request -- голосовое "Что сделано" сохраняется как аудио, не только текстом
// Voice-ввод на шагах 2-4 через /api/transcribe (см. B4). AI/voice текст всегда editable,
// ничего не отправляется без явного подтверждения юзера (owner requirement).

let _fwStep = 1;
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
// ошибки/таймаута слал НОВЫЙ ключ и backend не мог распознать повтор того же запроса.
let _fwIdempotencyKey = null;

// Round 3: daily plan state for this shift
let _fwDailyPlanId = '';
let _fwDailyPlanVersion = 0;
let _fwDailyPlanItems = []; // plan.items from window._todayPlanState
let _fwItemResults = []; // [{item_id, status, actual_quantity, unit, reason_code, comment}]
let _fwTomorrowIssues = []; // selected issue keys
let _fwTomorrowComment = '';

const FW_NEED_CATEGORIES = [
  { key: 'materials', label: 'Материалы' },
  { key: 'tool', label: 'Инструмент' },
  { key: 'ppe', label: 'СИЗ' },
  { key: 'access', label: 'Доступ' },
  { key: 'other', label: 'Другое' },
];

const _FW_TOMORROW_ISSUES = [
  { key: 'material_not_ready', label: 'Материалы не готовы' },
  { key: 'tools_needed', label: 'Нужен инструмент' },
  { key: 'access_blocked', label: 'Нет доступа на объект' },
  { key: 'other', label: 'Другое' },
];

const _FW_PLAN_STATUS_LABELS = {
  done: 'Выполнено',
  partial: 'Частично',
  not_done: 'Не выполнено',
  blocked: 'Заблокировано',
};

// ── Step sequence ──────────────────────────────────────────────────────────────

function _fwStepSequence() {
  if (_fwDailyPlanItems.length > 0) {
    return ['photo', 'summary', 'plan-fact', 'extra', 'needs', 'tomorrow-prep', 'geo', 'review'];
  }
  return ['photo', 'summary', 'extra', 'needs', 'geo', 'review'];
}

function _fwCurrentKey() { return _fwStepSequence()[_fwStep - 1]; }
function _fwNavNext() { _fwGoToStep(_fwStep + 1); }
function _fwNavBack() { _fwGoToStep(_fwStep - 1); }

// ── Lifecycle ──────────────────────────────────────────────────────────────────

function openFinishShiftWizard(sessionId, objectId) {
  _fwStep = 1;
  _fwSessionId = sessionId;
  _fwObjectId = objectId;
  _fwPhotos = [];
  _fwWorkSummary = '';
  _fwExtraWorks = [];
  _fwNeeds = [];
  _fwDefects = [];
  _fwIdempotencyKey = null;
  _fwVoiceNoteFileId = '';
  // 28.07: owner report -- было захардкожено 30 минут независимо от реальной паузы.
  const activeSession = typeof _getActiveCheckinSession === 'function' ? _getActiveCheckinSession(objectId) : null;
  _fwPauseMinutes = Math.round((activeSession?.pauseAccumulatedSeconds || 0) / 60);
  _fwFinishGeo = null;

  // Round 3: load accepted daily plan for this shift
  _fwDailyPlanItems = [];
  _fwDailyPlanId = '';
  _fwDailyPlanVersion = 0;
  _fwItemResults = [];
  _fwTomorrowIssues = [];
  _fwTomorrowComment = '';
  const planState = window._todayPlanState;
  if (planState?.has_plan && planState.acceptance && planState.plan?.items?.length) {
    _fwDailyPlanItems = planState.plan.items;
    _fwDailyPlanId = planState.plan.id || '';
    _fwDailyPlanVersion = planState.plan.version || 0;
  }

  document.getElementById('finish-wizard-modal').style.display = 'flex';
  _fwRenderStep();
}

function _fwCloseWizard() {
  if (_fwStep > 1 && !confirm('Прервать завершение смены? Введённые данные будут потеряны.')) return;
  document.getElementById('finish-wizard-modal').style.display = 'none';
}

function _fwGoToStep(n) {
  const total = _fwStepSequence().length;
  if (n < 1 || n > total) return;
  _fwStep = n;
  _fwRenderStep();
}

function _fwRenderStep() {
  const body = document.getElementById('finish-wizard-body');
  const progressEl = document.getElementById('finish-wizard-progress');
  const titleEl = document.getElementById('finish-wizard-title');
  const seq = _fwStepSequence();
  progressEl.textContent = `Шаг ${_fwStep} из ${seq.length}`;

  const TITLES = {
    'photo': 'Фото результата',
    'summary': 'Что сделано',
    'plan-fact': 'Выполнение плана',
    'extra': 'Доп. работы',
    'needs': 'Потребности и проблемы',
    'tomorrow-prep': 'Готовность на завтра',
    'geo': 'Геолокация',
    'review': 'Сводка',
  };
  const key = _fwCurrentKey();
  titleEl.textContent = TITLES[key] || '';

  if (key === 'photo') body.innerHTML = _fwRenderStep1();
  else if (key === 'summary') body.innerHTML = _fwRenderStep2();
  else if (key === 'plan-fact') body.innerHTML = _fwRenderStepPlanFact();
  else if (key === 'extra') body.innerHTML = _fwRenderStep3();
  else if (key === 'needs') body.innerHTML = _fwRenderStep4();
  else if (key === 'tomorrow-prep') body.innerHTML = _fwRenderStepTomorrowPrep();
  else if (key === 'geo') body.innerHTML = _fwRenderStep5();
  else if (key === 'review') body.innerHTML = _fwRenderStep6();

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
    _fwNavNext();
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
  document.getElementById('fw-back-2')?.addEventListener('click', () => _fwNavBack());
  document.getElementById('fw-next-2')?.addEventListener('click', () => {
    _fwWorkSummary = textarea.value.trim();
    _fwNavNext();
  });
}

// ---------- Step plan-fact: Выполнение плана (Round 3) ----------
function _fwRenderStepPlanFact() {
  if (!_fwDailyPlanItems.length) {
    return `<div class="fw-hint">Плановых пунктов нет.</div>
      <div class="fw-nav-row">
        <button class="fw-back-btn" id="fw-back-pf" type="button">← Назад</button>
        <button class="submit-btn fw-next-btn" id="fw-next-pf" type="button">Далее</button>
      </div>`;
  }

  const itemsHtml = _fwDailyPlanItems.map((item, idx) => {
    const result = _fwItemResults.find(r => r.item_id === item.id) || {};
    const status = result.status || '';
    const btns = ['done', 'partial', 'not_done', 'blocked'].map(s =>
      `<button class="fw-status-btn${status === s ? ' fw-status-btn--active' : ''}" data-item="${item.id}" data-status="${s}" type="button">${_FW_PLAN_STATUS_LABELS[s]}</button>`
    ).join('');
    const showDetail = status && status !== 'done';
    return `
      <div class="fw-plan-item">
        <div class="fw-plan-item-title">${idx + 1}. ${esc(item.title)}</div>
        ${item.planned_quantity != null ? `<div class="fw-plan-item-meta">${item.planned_quantity} ${esc(item.unit || '')}</div>` : ''}
        <div class="fw-status-btns">${btns}</div>
        ${showDetail ? `
          <input type="number" class="fw-qty-input mangel-select" data-item="${item.id}"
            placeholder="Факт. кол-во" value="${result.actual_quantity != null ? result.actual_quantity : ''}"
            min="0" step="0.1" style="margin-top:0.4rem;width:100%;">
          <textarea class="mangel-textarea fw-comment-input" data-item="${item.id}"
            rows="1" placeholder="Комментарий" style="margin-top:0.25rem;">${esc(result.comment || '')}</textarea>
        ` : ''}
      </div>`;
  }).join('');

  return `
    <div class="fw-hint">Отметь, что удалось сделать по плану.</div>
    <div class="fw-plan-items">${itemsHtml}</div>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-pf" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-pf" type="button">Далее</button>
    </div>
  `;
}

function _fwWireStepPlanFact() {
  document.getElementById('fw-back-pf')?.addEventListener('click', () => _fwNavBack());

  document.querySelectorAll('.fw-status-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const itemId = btn.dataset.item;
      const status = btn.dataset.status;
      let result = _fwItemResults.find(r => r.item_id === itemId);
      if (!result) {
        const item = _fwDailyPlanItems.find(i => i.id === itemId) || {};
        result = { item_id: itemId, status: '', actual_quantity: null, unit: item.unit || '', reason_code: '', comment: '' };
        _fwItemResults.push(result);
      }
      result.status = status;
      _fwRenderStep();
    });
  });

  document.querySelectorAll('.fw-qty-input').forEach(inp => {
    inp.addEventListener('input', () => {
      const result = _fwItemResults.find(r => r.item_id === inp.dataset.item);
      if (result) result.actual_quantity = inp.value !== '' ? parseFloat(inp.value) : null;
    });
  });

  document.querySelectorAll('.fw-comment-input').forEach(ta => {
    ta.addEventListener('input', () => {
      const result = _fwItemResults.find(r => r.item_id === ta.dataset.item);
      if (result) result.comment = ta.value.trim();
    });
  });

  document.getElementById('fw-next-pf')?.addEventListener('click', () => {
    // Snapshot current input values before re-render
    document.querySelectorAll('.fw-qty-input').forEach(inp => {
      const result = _fwItemResults.find(r => r.item_id === inp.dataset.item);
      if (result && inp.value !== '') result.actual_quantity = parseFloat(inp.value);
    });
    document.querySelectorAll('.fw-comment-input').forEach(ta => {
      const result = _fwItemResults.find(r => r.item_id === ta.dataset.item);
      if (result) result.comment = ta.value.trim();
    });
    _fwNavNext();
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
  document.getElementById('fw-back-3')?.addEventListener('click', () => _fwNavBack());
  document.getElementById('fw-next-3')?.addEventListener('click', () => _fwNavNext());
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

  document.getElementById('fw-back-4')?.addEventListener('click', () => _fwNavBack());
  document.getElementById('fw-next-4')?.addEventListener('click', () => _fwNavNext());
}

// ---------- Step tomorrow-prep: Готовность на завтра (Round 3) ----------
function _fwRenderStepTomorrowPrep() {
  const issuesBtns = _FW_TOMORROW_ISSUES.map(issue =>
    `<button class="fw-issue-btn${_fwTomorrowIssues.includes(issue.key) ? ' fw-issue-btn--active' : ''}" data-issue="${issue.key}" type="button">${esc(issue.label)}</button>`
  ).join('');

  return `
    <div class="fw-hint">Отметь проблемы с готовностью на завтра (если есть).</div>
    <div class="fw-issue-btns">${issuesBtns}</div>
    <textarea id="fw-tomorrow-comment" class="mangel-textarea" rows="2"
      placeholder="Комментарий (опционально)" style="margin-top:0.5rem;">${esc(_fwTomorrowComment)}</textarea>
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-tp" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-tp" type="button">Далее</button>
    </div>
  `;
}

function _fwWireStepTomorrowPrep() {
  document.getElementById('fw-back-tp')?.addEventListener('click', () => _fwNavBack());

  document.querySelectorAll('.fw-issue-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.issue;
      const idx = _fwTomorrowIssues.indexOf(key);
      if (idx === -1) _fwTomorrowIssues.push(key);
      else _fwTomorrowIssues.splice(idx, 1);
      btn.classList.toggle('fw-issue-btn--active');
    });
  });

  document.getElementById('fw-tomorrow-comment')?.addEventListener('input', e => {
    _fwTomorrowComment = e.target.value.trim();
  });

  document.getElementById('fw-next-tp')?.addEventListener('click', () => {
    const ta = document.getElementById('fw-tomorrow-comment');
    if (ta) _fwTomorrowComment = ta.value.trim();
    // Auto-create a Need for each selected issue (best-effort dedup by description)
    _fwTomorrowIssues.forEach(issueKey => {
      const issueLabel = _FW_TOMORROW_ISSUES.find(i => i.key === issueKey)?.label || issueKey;
      const comment = _fwTomorrowComment ? `: ${_fwTomorrowComment}` : '';
      const desc = `Завтра: ${issueLabel}${comment}`;
      if (!_fwNeeds.some(n => n.description === desc)) {
        _fwNeeds.push({ category: 'other', description: desc });
      }
    });
    _fwNavNext();
  });
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
  document.getElementById('fw-back-5')?.addEventListener('click', () => _fwNavBack());

  const geo = await _getGeolocation();
  if (geo.lat && geo.lon) {
    _fwFinishGeo = geo;
    statusEl.textContent = '📍 Местоположение определено';
    statusEl.classList.add('fw-geo-ok');
    nextBtn.disabled = false;
    nextBtn.addEventListener('click', () => _fwNavNext());
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

// ---------- Step 6 (last): Сводка + отправка ----------
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
  const planHtml = _fwItemResults.length
    ? _fwItemResults.map(r => {
        const item = _fwDailyPlanItems.find(i => i.id === r.item_id);
        const icon = { done: '✓', partial: '~', not_done: '✗', blocked: '🚫' }[r.status] || '?';
        return `<li>${icon} ${esc(item?.title || r.item_id)}</li>`;
      }).join('')
    : null;

  return `
    <div class="fw-summary-section"><b>Фото:</b> ${_fwPhotos.length} шт.</div>
    <div class="fw-summary-section"><b>Что сделано:</b> ${esc(_fwWorkSummary) || '<span class="fw-empty-li">не указано</span>'}</div>
    ${planHtml ? `<div class="fw-summary-section"><b>По плану:</b><ul>${planHtml}</ul></div>` : ''}
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
  document.getElementById('fw-back-6')?.addEventListener('click', () => _fwNavBack());
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

    // Round 3: attach plan execution report if worker filled in item results
    if (_fwItemResults.length > 0 && _fwDailyPlanId) {
      formData.append('daily_plan_report', JSON.stringify({
        plan_id: _fwDailyPlanId,
        plan_version: _fwDailyPlanVersion,
        item_results: _fwItemResults,
        tomorrow_issues: _fwTomorrowIssues,
        tomorrow_comment: _fwTomorrowComment,
      }));
    }

    // 03.08 (ТЗ Задача 1): переиспользуем ключ, если он уже был создан прошлой попыткой
    _fwIdempotencyKey = _fwIdempotencyKey || crypto.randomUUID();
    const res = await fetch(`${API_BASE}/api/checkin/${_fwSessionId}/finish`, {
      method: 'POST',
      headers: { ..._authHeaders(), 'Idempotency-Key': _fwIdempotencyKey },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);

    // Реальное создание Need/Mangel тикетов -- только после успешного finish.
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
    // "Смена идёт" оставалась устаревшей. Тот же паттерн, что уже есть в checkin.js.
    if (typeof _loadWorkerShiftCta === 'function' && document.getElementById('worker-shift-cta')) {
      _loadWorkerShiftCta();
    }
    // Round 3: clear today-plan bar after plan is executed
    if (typeof _updateTodayPlanBar === 'function') {
      _updateTodayPlanBar({ has_plan: false });
      window._todayPlanState = null;
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
  const key = _fwCurrentKey();
  if (key === 'photo') _fwWireStep1();
  else if (key === 'summary') _fwWireStep2();
  else if (key === 'plan-fact') _fwWireStepPlanFact();
  else if (key === 'extra') _fwWireStep3();
  else if (key === 'needs') _fwWireStep4();
  else if (key === 'tomorrow-prep') _fwWireStepTomorrowPrep();
  else if (key === 'geo') _fwWireStep5();
  else if (key === 'review') _fwWireStep6();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('finish-wizard-close')?.addEventListener('click', _fwCloseWizard);
});
