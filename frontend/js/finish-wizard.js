// Finish-shift wizard (B3, 27.07). Отдельный файл от checkin.js -- не смешиваем с
// существующим checkin-preview-modal (тот остаётся для start-shift, более простой flow).
// 21.09 (Worker UX V2, Этап 8): 4 экрана всегда (Фото -> Что сделано/план-факт ->
// Проблемы и завтра -> Сводка), было 6/8 в зависимости от наличия DailyPlan.
// Геолокация больше не отдельный экран -- собирается в фоне (AUTO-CAPTURE PRINCIPLE),
// статус показан в Сводке. Каждый под-блок (план-факт/потребности/дефекты/завтра)
// сохранил свою исходную разметку/id/валидацию, объединены только контейнеры экранов.
let _fwVoiceNoteFileId = ''; // 28.07: owner request -- голосовое "Что сделано" сохраняется как аудио, не только текстом
// Voice-ввод на шагах 2-4 через /api/transcribe (см. B4). AI/voice текст всегда editable,
// ничего не отправляется без явного подтверждения юзера (owner requirement).

let _fwStep = 1;
let _fwSessionId = null;
let _fwObjectId = null;
let _fwPhotos = []; // File[]
let _fwPhotoUrls = new WeakMap();
let _fwWorkSummary = '';
let _fwExtraWorks = []; // [{description, zone, time_estimate, needs_approval}]
let _fwNeeds = []; // [{category, description}]
let _fwDefects = []; // [{description}]
let _fwPauseMinutes = 30;
let _fwFinishGeo = null; // {lat, lon, accuracy, timestamp}
let _fwGeoState = 'loading'; // loading | success | error
let _fwGeoCapturePromise = null; // single in-flight _getGeolocation() promise, null when idle
let _fwOverlayUnregister = null;
let _fwContextState = 'idle'; // loading | loaded_with_plan | loaded_without_plan | offline_cached | error
let _fwContextError = '';
let _fwFinishContext = null;
// 03.08 (ТЗ Задача 1): персистентный на весь wizard-flow idempotency key -- раньше
// генерировался заново на КАЖДЫЙ вызов _fwSubmitFinish(), так что retry после сетевой
// ошибки/таймаута слал НОВЫЙ ключ и backend не мог распознать повтор того же запроса.
let _fwIdempotencyKey = null;
let _fwOccurredAt = '';
const CHECKIN_OUTBOX_KIND_FINISH = 'checkin-finish';
let _finishOutboxRetrying = false;

// Round 3: daily plan state for this shift
let _fwDailyPlanId = '';
let _fwDailyPlanVersion = 0;
let _fwDailyPlanItems = []; // frozen accepted items from /finish-context
let _fwItemResults = []; // [{item_id, status, actual_quantity, unit, reason_code, comment}]
let _fwTomorrowIssues = []; // selected issue keys
let _fwTomorrowComment = '';
let _fwExtraDraftOpen = false;

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
  // 21.09 (merged from upstream, owner review finding): context-loading/error
  // used to be full-screen gates BEFORE the first render -- worker couldn't
  // even start adding photos while /finish-context was still in flight, and a
  // fetch failure blocked Finish entirely even though a plan-less shift is a
  // completely normal, always-supported case (checkin_finish itself never
  // required a plan). Photos never needed daily-plan items at all; only the
  // 'summary' step's plan-fact section does, and it already renders gracefully
  // with an empty list (see _fwRenderStepSummaryPlanFact) and re-renders
  // itself once the background fetch resolves or fails. A failed fetch with no
  // usable cache just leaves the item checklist empty -- same as a shift that
  // was never plan-linked -- the error is surfaced inline (review screen), not
  // as a wizard-blocking screen.
  return ['photo', 'summary', 'extra', 'review'];
}

function _fwCurrentKey() { return _fwStepSequence()[_fwStep - 1]; }
function _fwNavNext() { _fwGoToStep(_fwStep + 1); }
function _fwNavBack() { _fwGoToStep(_fwStep - 1); }

// ── Lifecycle ──────────────────────────────────────────────────────────────────

function _fwGetPhotoUrl(file) {
  let url = _fwPhotoUrls.get(file);
  if (!url) {
    url = URL.createObjectURL(file);
    _fwPhotoUrls.set(file, url);
  }
  return url;
}

function _fwRevokePhoto(file) {
  const url = _fwPhotoUrls.get(file);
  if (!url) return;
  URL.revokeObjectURL(url);
  _fwPhotoUrls.delete(file);
}

function _fwClearPhotoUrls() {
  _fwPhotos.forEach(_fwRevokePhoto);
  _fwPhotoUrls = new WeakMap();
}

async function openFinishShiftWizard(sessionId, objectId) {
  _fwStopVoiceRecording();
  _fwClearPhotoUrls();
  _fwStep = 1;
  _fwSessionId = sessionId;
  _fwObjectId = objectId;
  _fwPhotos = [];
  _fwWorkSummary = '';
  _fwExtraWorks = [];
  _fwNeeds = [];
  _fwDefects = [];
  _fwIdempotencyKey = null;
  _fwOccurredAt = '';
  _fwVoiceNoteFileId = '';
  // 28.07: owner report -- было захардкожено 30 минут независимо от реальной паузы.
  const activeSession = typeof _getActiveCheckinSession === 'function' ? _getActiveCheckinSession(objectId) : null;
  _fwPauseMinutes = Math.round((activeSession?.pauseAccumulatedSeconds || 0) / 60);
  _fwFinishGeo = null;
  _fwGeoState = 'loading';
  _fwGeoCapturePromise = null;

  // Round 3: load accepted daily plan for this shift
  _fwDailyPlanItems = [];
  _fwDailyPlanId = '';
  _fwDailyPlanVersion = 0;
  _fwItemResults = [];
  _fwTomorrowIssues = [];
  _fwTomorrowComment = '';
  _fwExtraDraftOpen = false;
  // 'idle', not 'loading' -- _fwStepSequence() no longer gates on context state
  // (see comment there), so this never needs to hold up the first render.
  _fwContextState = 'idle';
  _fwContextError = '';
  _fwFinishContext = null;

  document.getElementById('finish-wizard-modal').style.display = 'flex';
  if (typeof NavigationManager !== 'undefined' && !_fwOverlayUnregister) {
    _fwOverlayUnregister = NavigationManager.registerOverlay(() => _fwCloseWizardInternal());
  }
  _fwRenderStep(); // render immediately with an empty item list -- don't block modal open on the network
  _fwLoadFinishContext(sessionId, objectId);
  // 21.09 (Worker UX V2, Этап 8, AUTO-CAPTURE PRINCIPLE): геолокация — то, что
  // система может получить сама, не требует отдельного блокирующего экрана.
  // Раньше был отдельный шаг "geo" ПОСЛЕ review-контента; теперь запрашивается
  // в фоне сразу при открытии wizard (параллельно с фото/summary), к моменту
  // просмотра Сводки обычно уже готова. Кнопка "Завершить" (_fwSubmitFinish)
  // по-прежнему требует непустую _fwFinishGeo -- сам submit-контракт не менялся.
  _fwStartBackgroundGeoCapture(sessionId);
}

// Единственная точка входа для сбора geo -- вызывается при открытии wizard И
// как retry с review-экрана. Один in-flight promise на sessionId (не плодит
// параллельные getCurrentPosition() при повторном тапе "Повторить" пока
// первый запрос ещё не резолвился) + явный state loading/success/error
// (раньше был только implicit null/truthy _fwFinishGeo, неотличимый от
// "ещё грузится"). Stale-session guard -- тот же паттерн что
// _fwLoadFinishContext (`if (_fwSessionId !== sessionId) return;`), чтобы
// поздний geo-response не записался в уже другую/новую сессию wizard.
function _fwStartBackgroundGeoCapture(sessionId) {
  if (_fwGeoCapturePromise) return _fwGeoCapturePromise;
  _fwGeoState = 'loading';
  _fwGeoCapturePromise = _getGeolocation().then(geo => {
    if (_fwSessionId !== sessionId) return; // wizard закрыт/переоткрыт для другой смены за это время
    if (geo.lat && geo.lon) {
      _fwFinishGeo = geo;
      _fwGeoState = 'success';
    } else {
      _fwFinishGeo = null;
      _fwGeoState = 'error';
    }
    _fwGeoCapturePromise = null;
    if (_fwCurrentKey() === 'review') _fwRenderStep();
  });
  return _fwGeoCapturePromise;
}

function _fwFinishContextCacheKey(sessionId) {
  return `finish_context_${sessionId}`;
}

function _fwReadCachedFinishContext(sessionId) {
  try {
    const raw = localStorage.getItem(_fwFinishContextCacheKey(sessionId));
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function _fwWriteCachedFinishContext(sessionId, data) {
  try {
    localStorage.setItem(_fwFinishContextCacheKey(sessionId), JSON.stringify(data));
  } catch (e) {}
}

// 21.09 (P0, owner review finding, round 2 then hardened round 3): the
// offline cache above was write-on-read only -- written the FIRST time
// Finish Wizard successfully fetched /finish-context online. Real failure
// mode this missed: Start online -> full day of work -> network drops
// before Finish is opened even once -- there is nothing to fall back to.
//
// Round 2's fix (a second GET /finish-context request fired right after
// Start) was still non-deterministic: if connectivity dropped in the
// (typically short, but real) window between Start succeeding and that
// second request completing, the cache still wouldn't exist. Round 3:
// checkin_start()'s response now embeds the exact same finish-context shape
// directly (backend/main.py's _build_finish_context(), shared with the GET
// endpoint) -- prefer that zero-extra-round-trip field when the caller
// already has it (startResponse), and only fall back to a live GET request
// when it doesn't (e.g. a Start success path that hasn't been updated to
// pass it through, or a defensive call site).
async function _prefetchFinishContextAfterStart(sessionId, startResponse) {
  if (!sessionId) return;
  // 21.09 (owner review finding, round 4): checking mere field PRESENCE
  // (hasOwnProperty) is not enough -- checkin_start()'s own best-effort
  // try/except around _build_finish_context() can legitimately send back
  // `finish_context: null` if that call raised server-side. hasOwnProperty
  // would still be true for a null value, so this used to return early
  // without ever falling back to a live GET, silently leaving no cache at
  // all instead of at least attempting the round-2 fallback path.
  if (startResponse?.finish_context != null) {
    const embedded = startResponse.finish_context;
    if (embedded?.has_plan) _fwWriteCachedFinishContext(sessionId, embedded);
    return;
  }
  try {
    const data = await api(`/api/checkin/${sessionId}/finish-context`);
    if (data?.has_plan) _fwWriteCachedFinishContext(sessionId, data);
  } catch (e) { /* non-fatal -- Finish still works via its own online fetch/cache-miss path */ }
}

function _fwApplyFinishContext(data, state) {
  _fwFinishContext = data || null;
  _fwDailyPlanItems = [];
  _fwDailyPlanId = '';
  _fwDailyPlanVersion = 0;

  if (data?.has_plan && data.plan?.items?.length) {
    _fwDailyPlanItems = data.plan.items;
    _fwDailyPlanId = data.plan.id || '';
    _fwDailyPlanVersion = data.plan.version || 0;
    _fwContextState = state || 'loaded_with_plan';
    return;
  }
  _fwContextState = state || 'loaded_without_plan';
}

async function _fwLoadFinishContext(sessionId, objectId) {
  try {
    const data = await api(`/api/checkin/${sessionId}/finish-context`);
    if (_fwSessionId !== sessionId) return;
    _fwApplyFinishContext(data, data?.has_plan ? 'loaded_with_plan' : 'loaded_without_plan');
    if (data?.has_plan) _fwWriteCachedFinishContext(sessionId, data);
    _fwStep = 1;
    _fwRenderStep();
  } catch (e) {
    if (_fwSessionId !== sessionId) return;
    const cached = _fwReadCachedFinishContext(sessionId);
    if (cached?.has_plan && (!objectId || String(cached.object_id || cached.plan?.object_id || '') === String(objectId))) {
      _fwApplyFinishContext(cached, 'offline_cached');
      _fwStep = 1;
      _fwRenderStep();
      return;
    }
    // 21.09 (owner review finding): no cache and the fetch failed -- treated
    // the same as "this shift was never plan-linked" (has_plan=false is a
    // normal state, not an error), not as a wizard-blocking screen. The
    // failure is still recorded for an inline note on the review step.
    _fwContextState = 'error';
    _fwContextError = e.message || 'Не удалось загрузить контекст смены';
    _fwRenderStep();
  }
}

function _fwCloseWizardInternal() {
  _fwStopVoiceRecording();
  _fwClearPhotoUrls();
  document.getElementById('finish-wizard-modal').style.display = 'none';
  _fwContextState = 'idle';
  _fwContextError = '';
  _fwFinishContext = null;
  _fwOverlayUnregister = null;
}

async function _fwCloseWizard() {
  // 18.09 (audit finding): was window.confirm() -- a jarring OS-chrome popup on
  // top of an otherwise fully custom iOS-like wizard UI. promontaConfirm() (shared.js)
  // is the reusable replacement, same early-return shape, async instead of sync.
  if (_fwStep > 1 && !await promontaConfirm('Прервать завершение смены? Введённые данные будут потеряны.', { danger: true })) return;
  if (_fwOverlayUnregister) {
    const unregister = _fwOverlayUnregister;
    _fwOverlayUnregister = null;
    unregister();
  }
  _fwCloseWizardInternal();
}

function _fwCloseWizardAfterSuccess() {
  if (_fwOverlayUnregister) {
    const unregister = _fwOverlayUnregister;
    _fwOverlayUnregister = null;
    unregister();
  }
  _fwCloseWizardInternal();
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
    'extra': 'Проблемы и завтра',
    'review': 'Сводка',
  };
  const key = _fwCurrentKey();
  titleEl.textContent = TITLES[key] || '';

  if (key === 'photo') body.innerHTML = _fwRenderStep1();
  else if (key === 'summary') body.innerHTML = _fwRenderStepSummaryPlanFact();
  else if (key === 'extra') body.innerHTML = _fwRenderStep3();
  else if (key === 'review') body.innerHTML = _fwRenderStep6();

  _fwWireStep();
}

// ---------- Step 1: Фото ----------
function _fwRenderStep1() {
  const thumbs = _fwPhotos.map((f, i) => `
    <div class="fw-photo-thumb">
      <img src="${_fwGetPhotoUrl(f)}" alt="фото ${i + 1}">
      <button class="fw-photo-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');
  const enough = _fwPhotos.length >= 2;
  const remaining = Math.max(0, 2 - _fwPhotos.length);
  return `
    <div class="fw-hint">Сделай минимум 2 фото с разных ракурсов. Лучше 3-5 фото.</div>
    <div class="fw-photo-requirement${enough ? ' fw-photo-requirement-ok' : ''}">
      ${enough ? 'Минимум выполнен' : `Нужно ещё ${remaining} фото`}
    </div>
    <div class="fw-photo-grid">${thumbs}</div>
    <div class="fw-photo-actions">
      <button class="fw-add-photo-btn" id="fw-camera-btn" type="button">Снять фото</button>
      <button class="fw-add-photo-btn" id="fw-gallery-btn" type="button">Из галереи</button>
    </div>
    <input type="file" id="fw-camera-input" accept="image/*" capture="environment" style="display:none;">
    <input type="file" id="fw-gallery-input" accept="image/*" multiple style="display:none;">
    <button class="submit-btn fw-next-btn" id="fw-next-1" type="button" ${enough ? '' : 'disabled'}>${enough ? 'Далее' : `Нужно ещё ${remaining} фото`}</button>
  `;
}

function _fwWireStep1() {
  const appendPhotos = files => {
    if (!files.length) return;
    _fwPhotos = _fwPhotos.concat(Array.from(files)).slice(0, 6);
    _fwRenderStep();
  };
  document.getElementById('fw-camera-btn')?.addEventListener('click', () => {
    document.getElementById('fw-camera-input')?.click();
  });
  document.getElementById('fw-gallery-btn')?.addEventListener('click', () => {
    document.getElementById('fw-gallery-input')?.click();
  });
  document.getElementById('fw-camera-input')?.addEventListener('change', e => {
    appendPhotos(e.target.files);
  });
  document.getElementById('fw-gallery-input')?.addEventListener('change', e => {
    appendPhotos(e.target.files);
  });
  document.querySelectorAll('.fw-photo-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const [removed] = _fwPhotos.splice(Number(btn.dataset.idx), 1);
      if (removed) _fwRevokePhoto(removed);
      _fwRenderStep();
    });
  });
  document.getElementById('fw-next-1')?.addEventListener('click', () => {
    if (_fwPhotos.length < 2) return;
    _fwNavNext();
  });
}

// ---------- Step "summary": Что сделано + план-факт (Worker UX V2, Этап 8) ----------
// 21.09: раньше два отдельных экрана ("Что сделано" -> "Выполнение плана"),
// объединены в один скролл-экран с общей кнопкой "Далее" — цель плана 3-4
// экрана вместо 6-8. Каждый под-блок сохранил свою исходную разметку/id
// (fw-work-summary/fw-status-btn/... не переименованы), меняется только то,
// что они теперь рендерятся и валидируются вместе, одной кнопкой.
function _fwRenderStepSummaryPlanFact() {
  const planItemsHtml = _fwDailyPlanItems.length ? _fwDailyPlanItems.map((item, idx) => {
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
  }).join('') : '';

  const canContinue = !!_fwWorkSummary.trim();

  return `
    <div class="fw-hint">Опиши, что сделано за смену. Можно надиктовать голосом и поправить текст.</div>
    <textarea id="fw-work-summary" class="mangel-textarea" rows="4" placeholder="Например: оштукатурили стену в комнате 2, установили 3 окна">${esc(_fwWorkSummary)}</textarea>
    ${_fwVoiceButtonHtml('fw-voice-summary')}
    <div class="fw-field-error" id="fw-summary-error" style="display:none;">Заполни короткий отчёт по смене</div>
    ${_fwDailyPlanItems.length ? `
      <div class="fw-hint" style="margin-top:1rem;">Отметь, что удалось сделать по плану.</div>
      <div class="fw-plan-items">${planItemsHtml}</div>
    ` : ''}
    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-summary" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-summary" type="button" ${canContinue ? '' : 'disabled'}>Далее</button>
    </div>
  `;
}

function _fwWireStepSummaryPlanFact() {
  const textarea = document.getElementById('fw-work-summary');
  const nextBtn = document.getElementById('fw-next-summary');
  const errorEl = document.getElementById('fw-summary-error');
  const syncSummary = () => {
    _fwWorkSummary = textarea.value;
    const ok = !!_fwWorkSummary.trim();
    if (nextBtn) nextBtn.disabled = !ok;
    if (errorEl && ok) errorEl.style.display = 'none';
  };
  textarea?.addEventListener('input', syncSummary);
  _fwWireVoiceButton('fw-voice-summary', (text, fileId) => {
    textarea.value = (textarea.value ? textarea.value + ' ' : '') + text;
    syncSummary();
    if (fileId) _fwVoiceNoteFileId = fileId;
  });
  document.getElementById('fw-back-summary')?.addEventListener('click', () => _fwNavBack());

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
      _fwWorkSummary = textarea.value; // сохранить перед re-render (перерисовка теряет незакоммиченный ввод иначе)
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

  document.getElementById('fw-next-summary')?.addEventListener('click', () => {
    _fwWorkSummary = textarea.value.trim();
    if (!_fwWorkSummary) {
      if (errorEl) errorEl.style.display = 'block';
      showToast('Заполни, что сделано за смену', 'error');
      textarea.focus();
      return;
    }

    if (_fwDailyPlanItems.length) {
      // Snapshot current input values before re-render/navigation
      document.querySelectorAll('.fw-qty-input').forEach(inp => {
        const result = _fwItemResults.find(r => r.item_id === inp.dataset.item);
        if (result && inp.value !== '') result.actual_quantity = parseFloat(inp.value);
      });
      document.querySelectorAll('.fw-comment-input').forEach(ta => {
        const result = _fwItemResults.find(r => r.item_id === ta.dataset.item);
        if (result) result.comment = ta.value.trim();
      });
      const missing = _fwDailyPlanItems.filter(item => {
        const result = _fwItemResults.find(r => r.item_id === item.id);
        return !result?.status;
      });
      if (missing.length) {
        showToast('Отметь выполнение каждого пункта плана', 'error');
        return;
      }
    }

    _fwNavNext();
  });
}

// ---------- Step "extra": Проблемы и завтра (Worker UX V2, Этап 8) ----------
// 21.09: раньше три отдельных экрана (Доп. работы -> Потребности/Дефекты ->
// Готовность на завтра), объединены в один скролл-экран с общей кнопкой
// "Далее" — все три под-блока были и остаются полностью опциональными
// (ни один не блокировал "Далее" раньше), поэтому объединённая кнопка не
// добавляет новую валидацию, только один снапшот вместо трёх последовательных.
function _fwRenderStep3() {
  const extraItemsHtml = _fwExtraWorks.map((w, i) => `
    <div class="fw-list-item" data-idx="${i}">
      <div class="fw-list-item-desc">${esc(w.description)}</div>
      <div class="fw-list-item-meta">${w.zone ? esc(w.zone) + ' · ' : ''}${w.time_estimate ? esc(w.time_estimate) : ''}${w.needs_approval ? ' · нужно согласование' : ''}</div>
      <button class="fw-list-item-remove" data-idx="${i}" type="button">✕</button>
    </div>`).join('');

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

  const issuesBtns = _FW_TOMORROW_ISSUES.map(issue =>
    `<button class="fw-issue-btn${_fwTomorrowIssues.includes(issue.key) ? ' fw-issue-btn--active' : ''}" data-issue="${issue.key}" type="button">${esc(issue.label)}</button>`
  ).join('');

  return `
    <div class="fw-hint">Были ли доп. работы вне плана?</div>
    <div class="fw-list">${extraItemsHtml || '<div class="fw-empty">Пока не добавлено</div>'}</div>
    <div id="fw-extra-work-form" style="display:${_fwExtraDraftOpen ? 'block' : 'none'};">
      <textarea id="fw-extra-desc" class="mangel-textarea" rows="2" placeholder="Описание работы"></textarea>
      ${_fwVoiceButtonHtml('fw-voice-extra')}
      <input type="text" id="fw-extra-zone" class="mangel-select" placeholder="Зона/комната (опционально)" style="margin-top:0.5rem;">
      <input type="text" id="fw-extra-time" class="mangel-select" placeholder="Примерное время (опционально)" style="margin-top:0.5rem;">
      <label class="fw-checkbox-label"><input type="checkbox" id="fw-extra-approval"> Нужно согласование с владельцем</label>
      <button class="submit-btn" id="fw-extra-save" type="button" style="margin-top:0.5rem;">Добавить пункт</button>
    </div>
    <button class="fw-add-photo-btn" id="fw-add-extra-btn" type="button">+ Добавить работу</button>

    <div class="fw-hint" style="margin-top:1rem;">Что мешало работе или что нужно?</div>
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

    ${_fwDailyPlanItems.length ? `
      <div class="fw-hint" style="margin-top:1rem;">Отметь проблемы с готовностью на завтра (если есть).</div>
      <div class="fw-issue-btns">${issuesBtns}</div>
      <textarea id="fw-tomorrow-comment" class="mangel-textarea" rows="2"
        placeholder="Комментарий (опционально)" style="margin-top:0.5rem;">${esc(_fwTomorrowComment)}</textarea>
    ` : ''}

    <div class="fw-nav-row">
      <button class="fw-back-btn" id="fw-back-3" type="button">← Назад</button>
      <button class="submit-btn fw-next-btn" id="fw-next-3" type="button">Далее</button>
    </div>
  `;
}

let _fwPendingNeedCategory = null;

function _fwWireStep3() {
  // -- Доп. работы --
  document.getElementById('fw-add-extra-btn')?.addEventListener('click', () => {
    _fwExtraDraftOpen = true;
    document.getElementById('fw-extra-work-form').style.display = 'block';
    document.getElementById('fw-extra-desc')?.focus();
  });
  _fwWireVoiceButton('fw-voice-extra', text => {
    const ta = document.getElementById('fw-extra-desc');
    ta.value = (ta.value ? ta.value + ' ' : '') + text;
  });
  const saveExtraDraft = () => {
    const desc = document.getElementById('fw-extra-desc').value.trim();
    if (!desc) return false;
    _fwExtraWorks.push({
      description: desc,
      zone: document.getElementById('fw-extra-zone').value.trim(),
      time_estimate: document.getElementById('fw-extra-time').value.trim(),
      needs_approval: document.getElementById('fw-extra-approval').checked,
    });
    _fwExtraDraftOpen = false;
    return true;
  };
  document.getElementById('fw-extra-save')?.addEventListener('click', () => {
    if (!saveExtraDraft()) return;
    _fwRenderStep();
  });
  document.querySelectorAll('.fw-list-item-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      _fwExtraWorks.splice(Number(btn.dataset.idx), 1);
      _fwRenderStep();
    });
  });

  // -- Потребности --
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

  // -- Дефекты --
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

  // -- Готовность на завтра --
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

  document.getElementById('fw-back-3')?.addEventListener('click', () => _fwNavBack());
  document.getElementById('fw-next-3')?.addEventListener('click', () => {
    saveExtraDraft();

    const needText = document.getElementById('fw-need-desc')?.value.trim() || '';
    if (needText && _fwPendingNeedCategory) {
      _fwNeeds.push({ category: _fwPendingNeedCategory, description: needText });
      _fwPendingNeedCategory = null;
    }
    const defectText = document.getElementById('fw-defect-desc')?.value.trim() || '';
    if (defectText) _fwDefects.push({ description: defectText });

    const tomorrowTa = document.getElementById('fw-tomorrow-comment');
    if (tomorrowTa) _fwTomorrowComment = tomorrowTa.value.trim();
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
    <div class="fw-summary-section"><b>Что сделано:</b> ${esc(_fwWorkSummary)}</div>
    ${planHtml ? `<div class="fw-summary-section"><b>По плану:</b><ul>${planHtml}</ul></div>` : ''}
    <div class="fw-summary-section"><b>Доп. работы:</b><ul>${extraWorksHtml}</ul></div>
    <div class="fw-summary-section"><b>Потребности:</b><ul>${needsHtml}</ul></div>
    <div class="fw-summary-section"><b>Дефекты:</b><ul>${defectsHtml}</ul></div>
    <div class="fw-summary-section"><b>Пауза за смену:</b> ${_fwPauseMinutes > 0 ? `${_fwPauseMinutes} мин.` : 'без пауз'}</div>
    ${_fwContextState === 'error' ? `<div class="fw-summary-section" style="color:var(--text-light);">⚠️ Не удалось проверить план смены (${esc(_fwContextError || 'нет связи')}) — завершение работает без плана, как обычно.</div>` : ''}
    <div class="fw-summary-section" id="fw-geo-summary-row">
      <b>Геолокация:</b> ${
        _fwGeoState === 'success' ? '📍 определена'
        : _fwGeoState === 'loading' ? '⏳ определяем…'
        : '⚠️ не удалось определить <button type="button" class="fw-geo-retry-btn" id="fw-geo-retry-btn">Повторить</button>'
      }
    </div>
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
  document.getElementById('fw-geo-retry-btn')?.addEventListener('click', () => _fwStartBackgroundGeoCapture(_fwSessionId));
}

function _fwFinishOutboxId(idempotencyKey) {
  return `checkin-finish:${idempotencyKey}`;
}

function _fwBuildFinishOutboxRecord() {
  _fwIdempotencyKey = _fwIdempotencyKey || crypto.randomUUID();
  _fwOccurredAt = _fwOccurredAt || String(Date.now());
  const occurredAt = _fwOccurredAt;
  const fields = {
    lat: _fwFinishGeo.lat,
    lon: _fwFinishGeo.lon,
    occurred_at: occurredAt,
    done_summary: _fwWorkSummary,
    extra_works: JSON.stringify(_fwExtraWorks),
    needs: JSON.stringify(_fwNeeds),
    defects: JSON.stringify(_fwDefects),
    pause_minutes: String(_fwPauseMinutes),
  };
  if (_fwFinishGeo.accuracy) fields.accuracy = _fwFinishGeo.accuracy;
  if (_fwFinishGeo.timestamp) fields.geo_timestamp = _fwFinishGeo.timestamp;
  if (_fwVoiceNoteFileId) fields.voice_note_file_id = _fwVoiceNoteFileId;
  if (_fwItemResults.length > 0 && _fwDailyPlanId) {
    fields.daily_plan_report = JSON.stringify({
      plan_id: _fwDailyPlanId,
      plan_version: _fwDailyPlanVersion,
      item_results: _fwItemResults,
      tomorrow_issues: _fwTomorrowIssues,
      tomorrow_comment: _fwTomorrowComment,
    });
  }
  return {
    id: _fwFinishOutboxId(_fwIdempotencyKey),
    kind: CHECKIN_OUTBOX_KIND_FINISH,
    sessionId: _fwSessionId,
    objectId: _fwObjectId,
    fields,
    files: Array.from(_fwPhotos),
    needs: _fwNeeds,
    defects: _fwDefects,
    occurredAt,
    idempotencyKey: _fwIdempotencyKey,
  };
}

function _fwAppendFinishRecordFormData(record) {
  const formData = new FormData();
  Object.entries(record.fields || {}).forEach(([key, value]) => formData.append(key, value || ''));
  (record.files || []).forEach(f => formData.append('files', f));
  return formData;
}

async function _fwCreatePostFinishTickets(objectId, needs, defects) {
  const failures = [];
  for (const need of needs || []) {
    try {
      await api('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ title: need.description, object_id: objectId }),
      });
    } catch (e) {
      failures.push({ kind: 'Потребность', message: e?.message || 'ошибка', status: e?.status });
    }
  }
  for (const defect of defects || []) {
    try {
      const fd = new FormData();
      fd.append('object_id', objectId);
      fd.append('description', defect.description);
      const res = await fetch(`${API_BASE}/api/mangel`, {
        method: 'POST',
        headers: { ..._authHeaders() },
        body: fd,
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({}))).detail;
        const err = new Error(detail || `HTTP ${res.status}`);
        err.status = res.status;
        throw err;
      }
    } catch (e) {
      failures.push({ kind: 'Дефект', message: e?.message || 'ошибка', status: e?.status });
    }
  }
  if (failures.length) {
    const msg = failures.map(f => `${f.kind}: ${f.message}`).join('; ');
    const err = new Error(`Не удалось создать записи после финиша: ${msg}`);
    const transient = failures.some(f => promontaOutboxIsTransientError({ status: f.status, message: f.message }));
    err.status = transient ? 503 : (failures[0].status || 500);
    throw err;
  }
}

// 18.09 (audit finding): this used to be its own copy of the transient-error
// heuristic (no err.status awareness, same bug as shared.js's
// promontaOutboxIsTransientError had before this pass), and it made a DIFFERENT
// transient/permanent call than promontaOutboxRecordFailure() did for the exact
// same kind of error on retry -- first-attempt and retry-from-outbox paths must
// agree on what counts as retriable. Now a thin wrapper over the one shared
// classification in shared.js, not a second copy that can drift from it.
function _fwIsTransientFinishError(err) {
  return promontaOutboxIsTransientError(err);
}

async function _fwSendFinishOutboxRecord(record, { fromOutbox = false } = {}) {
  const res = await fetch(`${API_BASE}/api/checkin/${record.sessionId}/finish`, {
    method: 'POST',
    headers: { ..._authHeaders(), 'Idempotency-Key': record.idempotencyKey },
    body: _fwAppendFinishRecordFormData(record),
  });
  if (!res.ok) {
    // err.status must carry the real HTTP status so promontaOutboxIsTransientError()
    // can tell a permanent 4xx apart from a transient 5xx/429 -- see checkin.js's
    // _uploadCheckinPhotos for the same fix applied to the start-shift upload path.
    const detail = (await res.json().catch(() => ({}))).detail;
    const err = new Error(detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const session = await res.json();
  await _fwCreatePostFinishTickets(record.objectId, record.needs, record.defects);
  if (fromOutbox) await promontaOutboxDelete(record.id);
  return session;
}

async function _fwQueueFinishOutbox(record) {
  return promontaOutboxPut(record);
}

function _fwMarkFinishConfirmed(record, notify) {
  _setActiveCheckinSession(record.objectId, { id: record.sessionId, finished: true });
  _fwRefreshWorkerShiftSurfaces();
  window._todayPlanState = null;
  // 21.09 (P1, owner review finding): use the shared surfaces updater, not
  // _updateTodayPlanBar() alone -- otherwise Today's compact DailyPlan card
  // (home.js) kept showing the just-finished shift's plan until Home was
  // re-entered/re-initialized.
  if (typeof _updateWorkerDailyPlanSurfaces === 'function') {
    _updateWorkerDailyPlanSurfaces({ has_plan: false });
  } else if (typeof _updateTodayPlanBar === 'function') {
    _updateTodayPlanBar({ has_plan: false });
  }
  if (notify) showToast('Смена завершена', 'success');
}

function _fwRefreshWorkerShiftSurfaces() {
  if (typeof refreshCheckinButtons === 'function') refreshCheckinButtons();
  if (typeof _refreshWorkerCheckinFabIcon === 'function') _refreshWorkerCheckinFabIcon();
  if (typeof _loadWorkerShiftCta === 'function' && document.getElementById('worker-shift-cta')) {
    _loadWorkerShiftCta();
  }
}

async function _retryFinishOutboxRecords() {
  if (_finishOutboxRetrying || !navigator.onLine || typeof promontaOutboxList !== 'function') return;
  _finishOutboxRetrying = true;
  try {
    const records = await promontaOutboxList(CHECKIN_OUTBOX_KIND_FINISH).catch(() => []);
    // 17.09 (audit finding, P0): same dead_letter fix as checkin.js's start-outbox
    // retry -- see promontaOutboxRecordFailure() in shared.js for the shared logic.
    for (const record of records.filter(r => r.state !== 'dead_letter')) {
      await promontaOutboxPatch(record.id, {
        state: 'sending',
        attempts: (record.attempts || 0) + 1,
        lastError: null,
      });
      try {
        await _fwSendFinishOutboxRecord(record, { fromOutbox: true });
        _fwMarkFinishConfirmed(record, false);
        showToast('Отложенный финиш смены отправлен', 'success');
      } catch (e) {
        await promontaOutboxRecordFailure({ ...record, attempts: (record.attempts || 0) + 1 }, e);
      }
    }
  } finally {
    _finishOutboxRetrying = false;
  }
}

async function _fwSubmitFinish() {
  const btn = document.getElementById('fw-submit-finish');
  const statusEl = document.getElementById('fw-submit-status');
  if (_fwPhotos.length < 2) {
    showToast('Для финиша нужны минимум 2 фото', 'error');
    _fwGoToStep(1);
    return;
  }
  if (!_fwWorkSummary.trim()) {
    showToast('Заполни, что сделано за смену', 'error');
    _fwGoToStep(2);
    return;
  }
  if (!_fwFinishGeo?.lat || !_fwFinishGeo?.lon) {
    // Дожидаемся существующий in-flight promise (см. _fwStartBackgroundGeoCapture) --
    // если фоновый сбор уже идёт, ждём именно его, не стартуем второй параллельный
    // getCurrentPosition(). Если он уже завершился с ошибкой (_fwGeoState === 'error'),
    // это последняя синхронная попытка перед блокировкой submit.
    await _fwStartBackgroundGeoCapture(_fwSessionId);
    if (!_fwFinishGeo?.lat || !_fwFinishGeo?.lon) {
      showToast('Нужна геолокация финиша — включи и попробуй снова', 'error');
      return;
    }
  }
  btn.disabled = true;
  btn.textContent = 'Отправка…';
  statusEl.textContent = '';

  let finishRecord = null;
  try {
    finishRecord = _fwBuildFinishOutboxRecord();
    if (!navigator.onLine) {
      await _fwQueueFinishOutbox(finishRecord);
      _fwRefreshWorkerShiftSurfaces();
      _fwCloseWizardAfterSuccess();
      showToast('Финиш сохранён в офлайн-очередь', 'success');
      return;
    }
    await _fwSendFinishOutboxRecord(finishRecord);

    hapticImpact('medium');
    _fwMarkFinishConfirmed(finishRecord, false);
    _fwCloseWizardAfterSuccess();
    showToast('Смена завершена', 'success');
  } catch (e) {
    if (finishRecord && _fwIsTransientFinishError(e)) {
      try {
        await _fwQueueFinishOutbox(finishRecord);
        _fwRefreshWorkerShiftSurfaces();
        _fwCloseWizardAfterSuccess();
        showToast('Связь сорвалась — финиш сохранён в офлайн-очередь', 'success');
        return;
      } catch (queueErr) {
        statusEl.textContent = 'Не удалось сохранить офлайн: ' + queueErr.message;
      }
    } else {
      statusEl.textContent = 'Ошибка: ' + e.message;
    }
    statusEl.classList.add('fw-submit-error');
    btn.disabled = false;
    btn.textContent = 'Завершить смену';
  }
}

// ---------- Voice input (общий для шагов 2-4) ----------
function _fwVoiceButtonHtml(id) {
  return `<div class="fw-voice-wrap">
    <button class="fw-voice-btn" id="${id}" type="button" data-state="idle">Голосом</button>
    <div class="fw-voice-status" id="${id}-status"></div>
  </div>`;
}

let _fwActiveRecorder = null;
let _fwActiveVoiceStream = null;

function _fwPickVoiceMimeType() {
  return ['audio/webm', 'audio/mp4', 'audio/ogg'].find(t =>
    window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
}

function _fwStopVoiceRecording() {
  if (_fwActiveRecorder && _fwActiveRecorder.state === 'recording') {
    _fwActiveRecorder.stop();
    return;
  }
  if (_fwActiveVoiceStream) {
    _fwActiveVoiceStream.getTracks().forEach(t => t.stop());
    _fwActiveVoiceStream = null;
  }
  _fwActiveRecorder = null;
}

function _fwWireVoiceButton(btnId, onTranscript) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const statusEl = document.getElementById(`${btnId}-status`);
  const setStatus = text => { if (statusEl) statusEl.textContent = text || ''; };
  btn.addEventListener('click', async () => {
    if (btn.dataset.state === 'recording') {
      _fwActiveRecorder?.stop();
      return;
    }
    if (_fwActiveRecorder) {
      showToast('Сначала останови текущую запись', 'error');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      showToast('Запись голоса не поддерживается', 'error');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _fwActiveVoiceStream = stream;
      const chunks = [];
      const mimeType = _fwPickVoiceMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const usedMime = recorder.mimeType || mimeType || 'audio/webm';
      _fwActiveRecorder = recorder;
      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        _fwActiveVoiceStream = null;
        _fwActiveRecorder = null;
        btn.dataset.state = 'transcribing';
        btn.textContent = 'Распознаю...';
        setStatus('Можно продолжать после вставки текста');
        const blob = new Blob(chunks, { type: usedMime });
        if (blob.size < 500) {
          btn.dataset.state = 'idle';
          btn.textContent = 'Голосом';
          setStatus('');
          showToast('Запись слишком короткая', 'error');
          return;
        }
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
          const transcript = (data.raw_transcript || data.transcript || '').trim();
          if (!transcript) throw new Error('Пустая транскрипция');
          onTranscript(transcript, data.file_id || '');
          setStatus('Текст вставлен, можно поправить');
        } catch (e) {
          showToast('Не удалось распознать голос: ' + e.message, 'error');
          setStatus('');
        } finally {
          btn.dataset.state = 'idle';
          btn.textContent = 'Голосом';
        }
      };
      recorder.start();
      btn.dataset.state = 'recording';
      btn.textContent = 'Остановить запись';
      setStatus('Идёт запись');
    } catch (e) {
      showToast('Нет доступа к микрофону', 'error');
    }
  });
}

function _fwWireStep() {
  const key = _fwCurrentKey();
  if (key === 'photo') _fwWireStep1();
  else if (key === 'summary') _fwWireStepSummaryPlanFact();
  else if (key === 'extra') _fwWireStep3();
  else if (key === 'review') _fwWireStep6();
}

window.addEventListener('online', _retryFinishOutboxRecords);
setTimeout(_retryFinishOutboxRecords, 1800);

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('finish-wizard-close')?.addEventListener('click', _fwCloseWizard);
});
