// Фотоотчёт старт/финиш смены (Фаза 4a). Привязан к stages-view (детейл объекта).
// Активная check-in сессия хранится в localStorage per-object, чтобы пережить переключение вкладок.

let _checkinPauseMinutes = 0;
let _checkinSelectedStageName = null; // выбранный этап при старте смены (опционально, см. stage picker)
let _checkinSurveyPauseMinutes = 30; // единый Zeiterfassung-язык форм (batch 12) — тот же stepper что в ручном вводе
let _checkinPendingAction = null; // 'start' | 'finish' — какое действие ждёт выбора фото

function _checkinSessionKey(objectId) {
  return `checkin_session_${objectId}`;
}

function _getActiveCheckinSession(objectId) {
  const raw = localStorage.getItem(_checkinSessionKey(objectId));
  return raw ? JSON.parse(raw) : null;
}

function _setActiveCheckinSession(objectId, session) {
  if (session) {
    localStorage.setItem(_checkinSessionKey(objectId), JSON.stringify(session));
  } else {
    localStorage.removeItem(_checkinSessionKey(objectId));
  }
}

function _getGeolocation() {
  return new Promise(resolve => {
    if (!navigator.geolocation) { resolve({ lat: '', lon: '' }); return; }
    navigator.geolocation.getCurrentPosition(
      pos => resolve({ lat: String(pos.coords.latitude), lon: String(pos.coords.longitude) }),
      () => resolve({ lat: '', lon: '' }),
      { timeout: 5000 }
    );
  });
}

// 24.07: источник истины — сервер (/api/checkin), не localStorage. localStorage
// в Telegram WebView нестабилен между сессиями (подтверждено живым багом: старт смены
// через FAB на Home записывал сессию, но stages-view открытый через "Завершить" на
// дашборде читал пустой/устаревший localStorage — обе кнопки оставались в неверном
// состоянии). _getActiveCheckinSession(localStorage) остаётся как synchronous fallback
// для мест, где нельзя ждать — сама запись сессии при старте/финише не меняется.
let _checkinButtonsGeneration = 0;

async function refreshCheckinButtons() {
  const objectId = _stagesCurrentObjectId;
  const startBtn = document.getElementById('checkin-start-btn');
  const finishBtn = document.getElementById('checkin-finish-btn');
  const analyzeBtn = document.getElementById('checkin-analyze-btn');
  if (!startBtn || !finishBtn || !analyzeBtn) return;

  // 24.07: generation counter вместо сравнения objectId — предыдущий фикс (сравнивать
  // _stagesCurrentObjectId до/после await) не спасал, если ДВА вызова этой функции
  // случились для ОДНОГО И ТОГО ЖЕ объекта (initCheckinControls на входе на экран +
  // повторный вызов после успешного /api/checkin/start): objectId у обоих совпадает,
  // а более медленный первый (ещё "нет сессии") мог завершиться ПОСЛЕ второго (уже
  // "сессия открыта") и переписать UI обратно на неверное "Старт" состояние. Теперь
  // каждый вызов получает свой номер; если к моменту готовности ответа успел стартовать
  // более новый вызов — этот результат считается устаревшим и отбрасывается, независимо
  // от того совпадает ли objectId.
  const myGeneration = ++_checkinButtonsGeneration;

  let session = null;
  try {
    const data = await api(`/api/checkin?object_id=${encodeURIComponent(objectId)}`);
    if (myGeneration !== _checkinButtonsGeneration) return;
    // 24.07: НЕ фильтровать по дате здесь — сервер (Europe/Berlin) и клиент (UTC через
    // toISOString) расходятся в дате на границе полуночи CEST, что ложно скрывало только
    // что открытую смену. "Открыта" определяется исключительно finish_at, не датой.
    const sessions = data.sessions || [];
    const open = sessions.find(s => s.finish_at === null || s.finish_at === undefined);
    if (open) {
      session = {
        id: open.id, finished: false,
        pauseStartedAt: open.pause_started_at || null,
        pauseAccumulatedSeconds: open.pause_accumulated_seconds || 0,
      };
    } else if (sessions.length) {
      session = { id: sessions[sessions.length - 1].id, finished: true };
    }
    if (session) _setActiveCheckinSession(objectId, session);
  } catch (e) {
    // сеть недоступна — используем последнее известное локальное состояние, не блокируем UI
    session = _getActiveCheckinSession(objectId);
  }
  if (myGeneration !== _checkinButtonsGeneration) return;

  const pauseBtn = document.getElementById('checkin-pause-toggle-btn');

  if (session && !session.finished) {
    startBtn.disabled = true;
    startBtn.textContent = '▶ Смена начата';
    finishBtn.disabled = false;
    analyzeBtn.style.display = 'none';
    if (pauseBtn) {
      pauseBtn.style.display = 'flex';
      pauseBtn.dataset.paused = session.pauseStartedAt ? '1' : '0';
      pauseBtn.textContent = session.pauseStartedAt ? '▶ Продолжить' : '⏸ Пауза';
    }
  } else if (session && session.finished) {
    startBtn.disabled = false;
    startBtn.textContent = '▶ Старт смены';
    finishBtn.disabled = true;
    analyzeBtn.style.display = 'block';
    if (pauseBtn) pauseBtn.style.display = 'none';
  } else {
    startBtn.disabled = false;
    startBtn.textContent = '▶ Старт смены';
    finishBtn.disabled = true;
    analyzeBtn.style.display = 'none';
    if (pauseBtn) pauseBtn.style.display = 'none';
  }
}

async function _toggleCheckinPause() {
  const session = _getActiveCheckinSession(_stagesCurrentObjectId);
  if (!session) return;
  const btn = document.getElementById('checkin-pause-toggle-btn');
  btn.disabled = true;
  try {
    const result = await api(`/api/checkin/${session.id}/pause`, { method: 'POST' });
    hapticImpact('light');
    await refreshCheckinButtons();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

async function runCheckinAnalysis() {
  const session = _getActiveCheckinSession(_stagesCurrentObjectId);
  if (!session) return;
  const resultEl = document.getElementById('checkin-analysis-result');
  const btn = document.getElementById('checkin-analyze-btn');
  btn.disabled = true;
  btn.textContent = 'Анализирую…';
  resultEl.style.display = 'block';
  resultEl.innerHTML = '<div style="color:var(--text-light)">Загрузка AI-анализа (может занять минуту)…</div>';

  try {
    const [progress, materials, defects] = await Promise.allSettled([
      api(`/api/checkin/${session.id}/analyze-progress`, { method: 'POST' }),
      api(`/api/checkin/${session.id}/analyze-materials`, { method: 'POST' }),
      api(`/api/checkin/${session.id}/analyze-defects`, { method: 'POST' }),
    ]);

    const escMultiline = (s) => esc(String(s == null ? '' : s)).replace(/\n/g, '<br>');

    let html = '';
    if (progress.status === 'fulfilled') {
      html += `<div class="checkin-analysis-block"><div class="checkin-analysis-label">Прогресс работ</div>${escMultiline(progress.value.analysis)}</div>`;
    }
    if (materials.status === 'fulfilled') {
      html += `<div class="checkin-analysis-block"><div class="checkin-analysis-label">Расход материала (оценка)</div>${escMultiline(materials.value.analysis)}</div>`;
    }
    if (defects.status === 'fulfilled') {
      const d = defects.value;
      html += `<div class="checkin-analysis-block"><div class="checkin-analysis-label">Проверка дефектов</div>${escMultiline(d.analysis)}${d.ticket_created ? ' <b>→ создан тикет в Дефекты</b>' : ''}</div>`;
    }
    resultEl.innerHTML = html || '<div style="color:var(--red)">Не удалось получить анализ</div>';
    hapticImpact('light');
  } catch (e) {
    resultEl.innerHTML = `<div style="color:var(--red)">Ошибка анализа: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ AI-анализ смены';
  }
}

async function _uploadCheckinPhotos(url, files, extraFields, idempotencyKey) {
  const geo = await _getGeolocation();
  if (!geo.lat || !geo.lon) {
    throw new Error('Включи геолокацию, чтобы начать/завершить смену');
  }
  const formData = new FormData();
  formData.append('object_id', _stagesCurrentObjectId);
  formData.append('lat', geo.lat);
  formData.append('lon', geo.lon);
  if (extraFields) {
    Object.entries(extraFields).forEach(([k, v]) => formData.append(k, v || ''));
  }
  for (const f of files) formData.append('files', f);

  const res = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    headers: {
      'X-Telegram-Init-Data': initData,
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    body: formData,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  return res.json();
}

// 10.31: раньше выбранные фото сразу загружались без предпросмотра — если один
// кадр вышел смазанным, нельзя было переснять именно его, только всю партию заново.
// Теперь фото сначала попадают в _checkinPreviewFiles (превью-грид с крестиком-удалить
// на каждом + кнопкой "Добавить фото"), реальный upload — только по "Подтвердить".
let _checkinPreviewFiles = [];
let _checkinIdempotencyKey = null;

function _handleCheckinPhotoSelected(files) {
  if (!files.length) return;
  _checkinPreviewFiles = _checkinPreviewFiles.concat(Array.from(files)).slice(0, 4);
  _renderCheckinPreview();
  _openCheckinPreviewModal();
}

function _openCheckinPreviewModal() {
  const modal = document.getElementById('checkin-preview-modal');
  const title = document.getElementById('checkin-preview-title');
  const survey = document.getElementById('checkin-finish-survey');
  const isFinish = _checkinPendingAction === 'finish';
  title.textContent = isFinish ? 'Фото окончания смены (минимум 2)' : 'Фото начала смены';
  survey.style.display = isFinish ? 'block' : 'none';
  if (isFinish) {
    // 24.07: default теперь реально накопленное время паузы (кнопка Пауза/Продолжить
    // во время смены), не хардкод 30 — юзер может доправить вручную если что-то не учтено.
    const session = _getActiveCheckinSession(_stagesCurrentObjectId);
    const accumulatedSeconds = session?.pauseAccumulatedSeconds || 0;
    _checkinSurveyPauseMinutes = Math.round(accumulatedSeconds / 60);
    _updateCheckinSurveyPauseDisplay();
  }
  modal.style.display = 'flex';
}

function _closeCheckinPreviewModal() {
  document.getElementById('checkin-preview-modal').style.display = 'none';
  _checkinPreviewFiles = [];
  _checkinPendingAction = null;
  _checkinIdempotencyKey = null;
  document.getElementById('checkin-survey-done').value = '';
  document.getElementById('checkin-survey-extra').value = '';
  document.getElementById('checkin-survey-next').value = '';
  document.getElementById('checkin-survey-pause').value = '30';
}

function _renderCheckinPreview() {
  const grid = document.getElementById('checkin-preview-grid');
  const confirmBtn = document.getElementById('checkin-preview-confirm-btn');
  grid.innerHTML = _checkinPreviewFiles.map((f, i) => {
    const url = URL.createObjectURL(f);
    return `<div class="checkin-preview-item">
      <img src="${url}" alt="фото ${i + 1}" loading="lazy">
      <button class="checkin-preview-remove" data-idx="${i}" type="button">✕</button>
    </div>`;
  }).join('');
  grid.querySelectorAll('.checkin-preview-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      _checkinPreviewFiles.splice(Number(btn.dataset.idx), 1);
      _renderCheckinPreview();
    });
  });
  const minRequired = _checkinPendingAction === 'finish' ? 2 : 1;
  confirmBtn.disabled = _checkinPreviewFiles.length < minRequired;
  confirmBtn.textContent = _checkinPreviewFiles.length
    ? `Подтвердить (${_checkinPreviewFiles.length} фото)` : 'Подтвердить';
}

// 21.07: offline-aware retry — плохая связь на объекте не должна терять фото/данные смены.
// Файлы и idempotency-key уже сохранены в памяти (не сброшены при неудаче), поэтому повтор
// отправки — не заново фотографировать, а просто "Повторить" с тем же ключом (сервер
// дедуплицирует по Idempotency-Key). Настоящая бинарная offline-очередь (IndexedDB) избыточна
// для соло-приложения — retry-friendly UI даёт 90% пользы за 10% сложности.
let _checkinSyncStatusEl = null;

function _setCheckinSyncStatus(text, isError) {
  const modal = document.getElementById('checkin-preview-modal');
  if (!_checkinSyncStatusEl) {
    _checkinSyncStatusEl = document.createElement('div');
    _checkinSyncStatusEl.className = 'checkin-sync-status';
    modal.querySelector('.checkin-preview-inner')?.appendChild(_checkinSyncStatusEl);
  }
  _checkinSyncStatusEl.textContent = text || '';
  _checkinSyncStatusEl.classList.toggle('checkin-sync-error', !!isError);
  _checkinSyncStatusEl.style.display = text ? 'block' : 'none';
}

async function _confirmCheckinPreview() {
  if (!_checkinPreviewFiles.length) return;

  // 24.07: "Что сделано за день" и "Что нужно подготовить на завтра" обязательны
  // при финише — owner должен всегда получать эти данные, не полагаться на то что
  // worker вспомнит заполнить. HTML required без <form> не валидирует сам, проверяем
  // явно перед отправкой.
  if (_checkinPendingAction === 'finish') {
    const doneEl = document.getElementById('checkin-survey-done');
    const nextEl = document.getElementById('checkin-survey-next');
    if (!doneEl.value.trim() || !nextEl.value.trim()) {
      showToast('Заполни "Что сделано за день" и "Что нужно подготовить на завтра" — обязательные поля', 'error');
      (!doneEl.value.trim() ? doneEl : nextEl).focus();
      return;
    }
    if (_checkinPreviewFiles.length < 2) {
      showToast('Прикрепи минимум 2 фото выполненной работы', 'error');
      return;
    }
  }

  const confirmBtn = document.getElementById('checkin-preview-confirm-btn');
  confirmBtn.disabled = true;

  if (!navigator.onLine) {
    confirmBtn.disabled = false;
    _setCheckinSyncStatus('Нет связи — фото сохранены, нажми "Подтвердить" когда появится интернет', true);
    return;
  }

  confirmBtn.textContent = 'Отправка…';
  _setCheckinSyncStatus('Отправка…');
  if (!_checkinIdempotencyKey) _checkinIdempotencyKey = crypto.randomUUID();
  try {
    if (_checkinPendingAction === 'start') {
      const startFields = _checkinSelectedStageName ? { stage_name: _checkinSelectedStageName } : null;
      const session = await _uploadCheckinPhotos('/api/checkin/start', _checkinPreviewFiles, startFields, _checkinIdempotencyKey);
      _setActiveCheckinSession(_stagesCurrentObjectId, { id: session.id, finished: false });
      _checkinSelectedStageName = null;
      hapticImpact('light');
    } else if (_checkinPendingAction === 'finish') {
      const session = _getActiveCheckinSession(_stagesCurrentObjectId);
      const surveyFields = {
        done_summary: document.getElementById('checkin-survey-done').value,
        extra_work: document.getElementById('checkin-survey-extra').value,
        next_day_needs: document.getElementById('checkin-survey-next').value,
        pause_minutes: document.getElementById('checkin-survey-pause').value || '0',
      };
      await _uploadCheckinPhotos(`/api/checkin/${session.id}/finish`, _checkinPreviewFiles, surveyFields, _checkinIdempotencyKey);
      _setActiveCheckinSession(_stagesCurrentObjectId, { id: session.id, finished: true });
      hapticImpact('medium');
    }
    _setCheckinSyncStatus('');
    refreshCheckinButtons();
    // 24.07: после старта/финиша через FAB (не заходя в объект) карточка "Смена
    // идёт/не начата" на Home оставалась устаревшей, пока юзер не уходил с Home и не
    // возвращался — initWorkerHomeView() перерисовывается только при switchView('home'),
    // а тут юзер физически остаётся на том же view. Обновляем карточку напрямую, если
    // она есть в DOM прямо сейчас.
    if (typeof _loadWorkerShiftCta === 'function' && document.getElementById('worker-shift-cta')) {
      _loadWorkerShiftCta();
    }
    _closeCheckinPreviewModal();
  } catch (e) {
    // Файлы и idempotency-key НЕ сбрасываются — повторный тап "Подтвердить" безопасен (дедуп на сервере),
    // не нужно переснимать фото заново при плохой связи. Geo-ошибка — отдельный случай:
    // повтор не поможет, пока юзер физически не включит геолокацию (не временный network-сбой).
    const isGeoError = /геолокац/i.test(e.message || '');
    _setCheckinSyncStatus(
      isGeoError
        ? 'Включи геолокацию в настройках и нажми "Подтвердить" ещё раз'
        : 'Не удалось отправить — данные сохранены, нажми "Подтвердить" ещё раз',
      true
    );
    showToast('Ошибка check-in: ' + e.message, 'error');
    confirmBtn.disabled = false;
    confirmBtn.textContent = `Подтвердить (${_checkinPreviewFiles.length} фото)`;
  }
}

function _closeCheckinManualForm() {
  document.getElementById('checkin-manual-form').style.display = 'none';
}

function _updateCheckinPauseDisplay() {
  document.getElementById('checkin-pause-value').textContent = `${_checkinPauseMinutes} мин.`;
}

function _updateCheckinSurveyPauseDisplay() {
  document.getElementById('checkin-survey-pause-value').textContent = `${_checkinSurveyPauseMinutes} мин.`;
  document.getElementById('checkin-survey-pause').value = _checkinSurveyPauseMinutes;
}

async function _submitCheckinManual() {
  const objectId = _stagesCurrentObjectId;
  const date = document.getElementById('checkin-date-input').value;
  const startTime = document.getElementById('checkin-start-time-input').value;
  const endTime = document.getElementById('checkin-end-time-input').value;
  if (!date || !startTime || !endTime) { showToast('Заполните дату и время', 'error'); return; }

  try {
    await api('/api/checkin/manual', {
      method: 'POST',
      body: JSON.stringify({
        object_id: objectId,
        art: document.getElementById('checkin-art-select').value,
        date,
        start_time: startTime,
        end_time: endTime,
        pause_minutes: _checkinPauseMinutes,
        description: document.getElementById('checkin-description').value,
      }),
    });
    hapticImpact('light');
    _closeCheckinManualForm();
  } catch (e) {
    showToast('Ошибка сохранения: ' + e.message, 'error');
  }
}

function initCheckinControls() {
  refreshCheckinButtons();

  // 10.31: теперь вызывается и из worker-checkin-fab.js (FAB может сработать раньше,
  // чем worker когда-либо откроет детейл объекта) — без guard второй вызов задвоил бы
  // все обработчики клика (двойной upload/двойное открытие превью на один тап).
  const startBtn = document.getElementById('checkin-start-btn');
  if (startBtn.dataset.wired) return;
  startBtn.dataset.wired = '1';

  const pauseBtn = document.getElementById('checkin-pause-toggle-btn');
  if (pauseBtn) pauseBtn.addEventListener('click', _toggleCheckinPause);

  // 21.07: связь восстановилась, модалка с несинхронизированными фото ещё открыта — авто-retry
  // без ожидания что worker сам заметит и тапнет ещё раз (может отвлечься на работу на объекте).
  window.addEventListener('online', () => {
    const modal = document.getElementById('checkin-preview-modal');
    const confirmBtn = document.getElementById('checkin-preview-confirm-btn');
    if (modal.style.display === 'flex' && _checkinPreviewFiles.length && !confirmBtn.disabled) {
      _confirmCheckinPreview();
    }
  });

  startBtn.addEventListener('click', () => {
    _checkinPendingAction = 'start';
    document.getElementById('checkin-photo-input').click();
  });
  document.getElementById('checkin-finish-btn').addEventListener('click', () => {
    _checkinPendingAction = 'finish';
    document.getElementById('checkin-photo-input').click();
  });
  document.getElementById('checkin-photo-input').addEventListener('change', e => {
    _handleCheckinPhotoSelected(Array.from(e.target.files));
    e.target.value = '';
  });
  document.getElementById('checkin-preview-add-btn').addEventListener('click', () => {
    document.getElementById('checkin-photo-input').click();
  });
  document.getElementById('checkin-preview-confirm-btn').addEventListener('click', _confirmCheckinPreview);
  document.getElementById('checkin-preview-close').addEventListener('click', () => {
    if (confirm('Отменить фото-фиксацию?')) _closeCheckinPreviewModal();
  });
  document.getElementById('checkin-analyze-btn').addEventListener('click', runCheckinAnalysis);

  document.getElementById('checkin-manual-link-btn').addEventListener('click', () => {
    const form = document.getElementById('checkin-manual-form');
    if (form.style.display === 'block') {
      _closeCheckinManualForm();
      return;
    }
    document.getElementById('checkin-date-input').value = new Date().toISOString().slice(0, 10);
    form.style.display = 'block';
  });
  document.getElementById('checkin-manual-cancel-btn').addEventListener('click', _closeCheckinManualForm);
  document.getElementById('checkin-manual-save-btn').addEventListener('click', _submitCheckinManual);
  document.getElementById('checkin-pause-minus').addEventListener('click', () => {
    _checkinPauseMinutes = Math.max(0, _checkinPauseMinutes - 15);
    _updateCheckinPauseDisplay();
  });
  document.getElementById('checkin-pause-plus').addEventListener('click', () => {
    _checkinPauseMinutes += 15;
    _updateCheckinPauseDisplay();
  });
  document.getElementById('checkin-survey-pause-minus').addEventListener('click', () => {
    _checkinSurveyPauseMinutes = Math.max(0, _checkinSurveyPauseMinutes - 5);
    _updateCheckinSurveyPauseDisplay();
  });
  document.getElementById('checkin-survey-pause-plus').addEventListener('click', () => {
    _checkinSurveyPauseMinutes += 5;
    _updateCheckinSurveyPauseDisplay();
  });
}
