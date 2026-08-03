// Онбординг v2: показывается новому пользователю при первом входе (onboarding_completed
// !== true и quiz_completed !== true -- старый флаг тоже проверяется, существующие
// пользователи с quiz_completed:true НЕ блокируются повторным onboarding). 4 шага:
// 1) имя+аватар, 2) выбор навыков (skill-picker.js), 3) уровень для каждого навыка
// (skill-picker.js), 4) размеры (необязательно) -> завершение.
//
// Дата рождения полностью убрана из onboarding v2 -- ни поля, ни отправки на backend.
//
// 01.08: полностью переписан под единый каталог видов работ (backend/work_types.py) --
// ONBOARDING_GROUPS/статичный список навыков здесь больше не хранится, всё приходит
// через api('/api/work-types') внутри skill-picker.js.

const SIZE_OPTIONS = {
  shirt: ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL'],
  pants: ['44', '46', '48', '50', '52', '54', '56', '58'],
  shoe: ['38', '39', '40', '41', '42', '43', '44', '45', '46', '47'],
};

let _obStep = 1; // 1..4
let _obName = '';
let _obAvatarPending = null; // File объект, если пользователь выбрал фото до PATCH
let _obSkillPicker = null;
let _obLevelPicker = null;
let _obSizes = { shirt: '', pants: '', shoe: '' };
let _obOverlayEl = null;
// 01.08 (доп.раунд П7, реальный найденный баг): выбор навыков/уровней жил ТОЛЬКО
// внутри живого _obSkillPicker/_obLevelPicker -- каждый _obRenderStep2()/3() пересоздаёт
// компонент через innerHTML, а initialSelected/initialLevels никогда не передавались.
// Возврат на шаг 2 назад из шага 3, потом снова вперёд -- выбор терялся полностью.
// Общее состояние живёт здесь, каждый рендер шага восстанавливает его в новый picker.
let _obSelectedSkillIds = new Set();
let _obSkillLevels = new Map();

async function checkOnboardingQuiz() {
  try {
    const profile = await api('/api/profile/me');
    // 01.08 (спека п.3): существующие пользователи с quiz_completed:true (старый флаг)
    // НЕ блокируются onboarding v2 -- проверяем ОБА флага, любой truthy пропускает.
    if (profile.onboarding_completed || profile.quiz_completed) return;
    _obName = profile.name || (window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name) || '';
    _obStep = 1;
    await _showOnboardingOverlay();
  } catch (e) {
    // профиль недоступен — не блокировать app
  }
}

function _obTelegramFirstName() {
  return window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || '';
}

async function _showOnboardingOverlay() {
  _obOverlayEl = document.createElement('div');
  _obOverlayEl.id = 'onboarding-overlay';
  document.body.appendChild(_obOverlayEl);
  document.body.style.overflow = 'hidden';
  await _obRenderStep();
}

function _obCloseOverlay() {
  document.body.style.overflow = '';
  _obOverlayEl?.remove();
  _obOverlayEl = null;
  location.reload(); // простой и надёжный способ гарантированно подтянуть свежий профиль/UI
}

async function _obRenderStep() {
  if (!_obOverlayEl) return;
  if (_obStep === 1) return _obRenderStep1();
  if (_obStep === 2) return _obRenderStep2();
  if (_obStep === 3) return _obRenderStep3();
  if (_obStep === 4) return _obRenderStep4();
}

// ---------- Шаг 1: приветствие, имя, аватар ----------
function _obRenderStep1() {
  if (!_obName) _obName = _obTelegramFirstName();
  _obOverlayEl.innerHTML = `
    <div class="onboarding-card">
      <div class="onboarding-dots">${_obDotsHtml(1)}</div>
      <h2 class="onboarding-title">Добро пожаловать в Promonta</h2>
      <p class="onboarding-subtitle">Заполни профиль, чтобы руководитель мог правильно назначать тебе объекты и виды работ.</p>
      <div class="onboarding-avatar-wrap">
        <div class="onboarding-avatar-circle" id="ob-avatar-circle">
          <span class="onboarding-avatar-placeholder">👤</span>
        </div>
        <div class="onboarding-avatar-actions">
          <button type="button" class="onboarding-avatar-btn" id="ob-avatar-camera">📷 Сделать фото</button>
          <button type="button" class="onboarding-avatar-btn" id="ob-avatar-gallery">🖼 Выбрать из галереи</button>
          <button type="button" class="onboarding-avatar-btn onboarding-avatar-skip" id="ob-avatar-skip">Добавить позже</button>
        </div>
        <input type="file" accept="image/*" capture="environment" id="ob-avatar-input-camera" style="display:none">
        <input type="file" accept="image/*" id="ob-avatar-input-gallery" style="display:none">
      </div>
      <label class="onboarding-name-label">Имя</label>
      <input type="text" class="onboarding-name-input" id="ob-name-input" value="${_escOb(_obName)}" maxlength="100" placeholder="Твоё имя">
      <div class="onboarding-error" id="ob-step1-error" style="display:none"></div>
      <div class="onboarding-nav-row">
        <button type="button" class="onboarding-submit-btn" id="ob-step1-next">Продолжить</button>
      </div>
    </div>
  `;

  const nameInput = document.getElementById('ob-name-input');
  nameInput.addEventListener('input', () => { _obName = nameInput.value; });

  const showAvatarPreview = (file) => {
    _obAvatarPending = file;
    const reader = new FileReader();
    reader.onload = (e) => {
      document.getElementById('ob-avatar-circle').innerHTML = `<img src="${e.target.result}" class="onboarding-avatar-img">`;
    };
    reader.readAsDataURL(file);
  };
  document.getElementById('ob-avatar-camera').addEventListener('click', () => document.getElementById('ob-avatar-input-camera').click());
  document.getElementById('ob-avatar-gallery').addEventListener('click', () => document.getElementById('ob-avatar-input-gallery').click());
  document.getElementById('ob-avatar-input-camera').addEventListener('change', (e) => { if (e.target.files[0]) showAvatarPreview(e.target.files[0]); });
  document.getElementById('ob-avatar-input-gallery').addEventListener('change', (e) => { if (e.target.files[0]) showAvatarPreview(e.target.files[0]); });
  document.getElementById('ob-avatar-skip').addEventListener('click', () => { _obAvatarPending = null; });

  document.getElementById('ob-step1-next').addEventListener('click', async () => {
    const name = nameInput.value.trim();
    const errEl = document.getElementById('ob-step1-error');
    if (!name) {
      errEl.textContent = 'Укажи имя';
      errEl.style.display = 'block';
      return;
    }
    _obName = name;
    const btn = document.getElementById('ob-step1-next');
    btn.disabled = true;
    btn.textContent = 'Сохраняю...';
    try {
      // Аватар не должен блокировать завершение onboarding -- ошибка загрузки
      // не мешает продолжить, только показывает понятное сообщение, имя не теряется.
      if (_obAvatarPending) {
        try {
          const fd = new FormData();
          fd.append('file', _obAvatarPending);
          const avatarRes = await fetch(`${API_BASE}/api/profile/me/avatar`, {
            method: 'POST', headers: { 'X-Telegram-Init-Data': initData }, body: fd,
          });
          // 01.08 (доп.раунд П7, реальный найденный баг): fetch() кидает исключение
          // ТОЛЬКО на сетевую ошибку -- 400 (не изображение) / 413 (слишком большой)
          // это успешный HTTP-ответ с ok:false, catch его не ловил вообще, ошибка
          // молча проглатывалась как будто аватар загрузился.
          if (!avatarRes.ok) {
            errEl.textContent = 'Не удалось загрузить фото, но можно продолжить';
            errEl.style.display = 'block';
          }
        } catch (e) {
          errEl.textContent = 'Не удалось загрузить фото, но можно продолжить';
          errEl.style.display = 'block';
        }
      }
      await api('/api/profile/me', { method: 'PATCH', body: JSON.stringify({ name: _obName }) });
      _obStep = 2;
      await _obRenderStep();
    } catch (e) {
      errEl.textContent = 'Не удалось сохранить имя: ' + e.message;
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Продолжить';
    }
  });
}

// ---------- Шаг 2: выбор навыков ----------
async function _obRenderStep2() {
  _obOverlayEl.innerHTML = `
    <div class="onboarding-card onboarding-card-skills">
      <div class="onboarding-dots">${_obDotsHtml(2)}</div>
      <h2 class="onboarding-title">Какие работы ты выполняешь?</h2>
      <div class="onboarding-skills-picker" id="ob-skills-picker"></div>
      <div class="onboarding-sticky-cta">
        <button type="button" class="onboarding-submit-btn" id="ob-step2-next" disabled>Продолжить · выбрано 0</button>
      </div>
    </div>
  `;
  const container = document.getElementById('ob-skills-picker');
  const nextBtn = document.getElementById('ob-step2-next');
  _obSkillPicker = await createSkillPicker(container, {
    initialSelected: _obSelectedSkillIds,
    onChange: (selected) => {
      _obSelectedSkillIds = selected;
      // 03.08 (реальный найденный баг): worker выбирал навык на шаге 2, указывал
      // уровень на шаге 3, возвращался назад и снимал навык -- запись оставалась в
      // _obSkillLevels и могла уйти в финальный payload для навыка, которого больше
      // нет в выборе. Чистим Map сразу при каждом изменении выбора, не только на
      // финальном шаге.
      for (const skillId of Array.from(_obSkillLevels.keys())) {
        if (!selected.has(skillId)) _obSkillLevels.delete(skillId);
      }
      nextBtn.disabled = selected.size === 0;
      nextBtn.textContent = `Продолжить · выбрано ${selected.size}`;
    },
  });
  nextBtn.disabled = _obSelectedSkillIds.size === 0;
  nextBtn.textContent = `Продолжить · выбрано ${_obSelectedSkillIds.size}`;
  nextBtn.addEventListener('click', () => {
    if (_obSkillPicker.getSelected().size === 0) return;
    _obSelectedSkillIds = _obSkillPicker.getSelected();
    _obStep = 3;
    _obRenderStep();
  });
}

// ---------- Шаг 3: уровни выбранных навыков ----------
async function _obRenderStep3() {
  const skillIds = Array.from(_obSelectedSkillIds);
  _obOverlayEl.innerHTML = `
    <div class="onboarding-card">
      <div class="onboarding-dots">${_obDotsHtml(3)}</div>
      <h2 class="onboarding-title">Твой уровень</h2>
      <div class="onboarding-levels-picker" id="ob-levels-picker"></div>
      <div class="onboarding-nav-row">
        <button type="button" class="onboarding-back-btn" id="ob-step3-back">Назад</button>
        <button type="button" class="onboarding-submit-btn" id="ob-step3-next" disabled>Продолжить</button>
      </div>
    </div>
  `;
  const container = document.getElementById('ob-levels-picker');
  const nextBtn = document.getElementById('ob-step3-next');
  _obLevelPicker = await createSkillLevelPicker(container, skillIds, {
    initialLevels: _obSkillLevels,
    onChange: (levels) => {
      _obSkillLevels = levels;
      nextBtn.disabled = !_obLevelPicker.isComplete();
    },
  });
  nextBtn.disabled = !_obLevelPicker.isComplete();
  document.getElementById('ob-step3-back').addEventListener('click', () => {
    _obSkillLevels = _obLevelPicker.getLevels();
    _obStep = 2;
    _obRenderStep();
  });
  nextBtn.addEventListener('click', () => {
    if (!_obLevelPicker.isComplete()) return;
    _obSkillLevels = _obLevelPicker.getLevels();
    _obStep = 4;
    _obRenderStep();
  });
}

// ---------- Шаг 4: размеры + завершение ----------
function _obRenderStep4() {
  _obOverlayEl.innerHTML = `
    <div class="onboarding-card">
      <div class="onboarding-dots">${_obDotsHtml(4)}</div>
      <h2 class="onboarding-title">Размеры (необязательно)</h2>
      <div class="onboarding-sizes">
        ${_obSizeSelectHtml('shirt', 'Футболка')}
        ${_obSizeSelectHtml('pants', 'Брюки')}
        ${_obSizeSelectHtml('shoe', 'Обувь')}
      </div>
      <div class="onboarding-error" id="ob-step4-error" style="display:none"></div>
      <div class="onboarding-nav-row">
        <button type="button" class="onboarding-back-btn" id="ob-step4-back">Назад</button>
        <button type="button" class="onboarding-submit-btn" id="ob-step4-finish">Завершить регистрацию</button>
      </div>
    </div>
  `;
  document.getElementById('ob-step4-back').addEventListener('click', () => { _obStep = 3; _obRenderStep(); });
  document.querySelectorAll('.onboarding-size-select').forEach(sel => {
    sel.addEventListener('change', () => { _obSizes[sel.dataset.sizeKey] = sel.value; });
  });
  document.getElementById('ob-step4-finish').addEventListener('click', async () => {
    const btn = document.getElementById('ob-step4-finish');
    const errEl = document.getElementById('ob-step4-error');
    btn.disabled = true;
    btn.textContent = 'Сохраняю...';
    // 03.08: строим ТОЛЬКО по текущим _obSelectedSkillIds (не по _obSkillLevels.entries()
    // напрямую) -- source of truth для того, какие навыки реально выбраны, это Set, а
    // Map уровней -- производное состояние, которое чистится при снятии навыка (см.
    // onChange шага 2 выше), но явная проверка здесь -- defense-in-depth на случай
    // рассинхронизации. Если у выбранного навыка почему-то нет уровня -- не отправляем
    // запрос вообще, backend всё равно бы отклонил onboarding_completed без уровня
    // каждого навыка, но лучше явная ошибка тут, чем непонятный 400 с сервера.
    const missingLevel = Array.from(_obSelectedSkillIds).find(id => !_obSkillLevels.has(id));
    if (missingLevel) {
      errEl.textContent = 'Укажи уровень для каждого выбранного навыка';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Завершить регистрацию';
      return;
    }
    const skillsV2 = Array.from(_obSelectedSkillIds).map(skill_id => ({
      skill_id,
      level: _obSkillLevels.get(skill_id),
      verified: false,
    }));
    try {
      // Спека: "Сначала сохранить профиль, затем установить onboarding_completed: true" --
      // здесь это один PATCH-запрос (backend делает то же самое атомарно: если
      // обязательные поля не прошли валидацию, onboarding_completed не устанавливается).
      await api('/api/profile/me', {
        method: 'PATCH',
        body: JSON.stringify({
          name: _obName,
          skills_v2: skillsV2,
          shirt_size: _obSizes.shirt || null,
          pants_size: _obSizes.pants || null,
          shoe_size: _obSizes.shoe || null,
          onboarding_completed: true,
        }),
      });
      _obCloseOverlay();
    } catch (e) {
      errEl.textContent = 'Не удалось завершить регистрацию: ' + e.message;
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Завершить регистрацию';
    }
  });
}

function _obSizeSelectHtml(key, label) {
  const options = SIZE_OPTIONS[key].map(v => `<option value="${v}">${v}</option>`).join('');
  return `
    <div class="onboarding-size-field">
      <label>${label}</label>
      <select class="onboarding-size-select" data-size-key="${key}">
        <option value="">—</option>
        ${options}
      </select>
    </div>
  `;
}

function _obDotsHtml(active) {
  return [1, 2, 3, 4].map(n => `<span class="onboarding-dot${n === active ? ' active' : ''}"></span>`).join('');
}

function _escOb(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : String(s);
  return div.innerHTML;
}
