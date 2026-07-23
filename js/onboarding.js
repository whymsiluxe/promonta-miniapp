// Онбординг-квиз навыков: показывается при первом запуске, если quiz_completed === false.
// Блокирует основной UI до прохождения. При quiz_completed:true — мгновенно пропускается.
// 10.2: многостраничный slide-флоу (intro + N экранов чекбоксов по группам), не один длинный список.

const ONBOARDING_GROUPS = [
  { title: 'Отделка', items: ['Штукатурка', 'Малярные работы', 'Малярные работы фасада', 'Гипсокартон (сухая стройка)', 'Плитка', 'Фасад'] },
  { title: 'Инженерные системы', items: ['Электрика', 'Сантехника', 'Отопление / вентиляция', 'Утепление / изоляция'] },
  { title: 'Конструкции и монтаж', items: ['Кровля', 'Кровельная жесть / водостоки', 'Монтаж окон и дверей', 'Строительные леса', 'Каменная кладка', 'Столярные / плотницкие работы', 'Сварочные работы'] },
  { title: 'Прочее', items: ['Демонтаж', 'Стяжка пола / бетонные работы', 'Ландшафт / благоустройство территории'] },
];

const SIZE_OPTIONS = {
  shirt: ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL'],
  pants: ['44', '46', '48', '50', '52', '54', '56', '58'],
  shoe: ['38', '39', '40', '41', '42', '43', '44', '45', '46', '47'],
};

let _obSelected = new Set();
let _obSizes = { shirt: '', pants: '', shoe: '' };
let _obBirthday = '';
let _obStep = 0; // 0 = intro, 1..N = группы, N+1 = размеры
let _obDirection = 'next'; // для анимации слайда: next или back

async function checkOnboardingQuiz() {
  try {
    const profile = await api('/api/profile/me');
    if (profile.quiz_completed) return;
    await _showQuizOverlay(profile.skill_options || []);
  } catch (e) {
    // профиль недоступен — не блокировать app
  }
}

function _obGroupsFromOptions(skillOptions) {
  // Группируем по ONBOARDING_GROUPS, но не теряем навыки, которых нет в списке групп
  // (на случай расхождения между SKILL_OPTIONS на бэкенде и статичным списком групп здесь).
  const known = new Set(ONBOARDING_GROUPS.flatMap(g => g.items));
  const groups = ONBOARDING_GROUPS.map(g => ({ ...g, items: g.items.filter(i => skillOptions.includes(i)) }))
    .filter(g => g.items.length);
  const extra = skillOptions.filter(s => !known.has(s));
  if (extra.length) groups.push({ title: 'Другое', items: extra });
  return groups;
}

function _obTotalSteps(groups) { return groups.length + 2; } // +1 intro slide, +1 size slide

function _obRenderDots(groups) {
  const total = _obTotalSteps(groups);
  let dots = '';
  for (let i = 0; i < total; i++) {
    dots += `<span class="onboarding-dot${i === _obStep ? ' active' : ''}"></span>`;
  }
  return `<div class="onboarding-dots">${dots}</div>`;
}

function _obRenderIntro() {
  return `
    <div class="onboarding-slide onboarding-slide-intro">
      <div class="onboarding-logo">🏗️</div>
      <h1 class="onboarding-title">Добро пожаловать в Promonta!</h1>
      <p class="onboarding-sub">Отметь виды работ, которые ты умеешь делать — так мы сможем предлагать тебе подходящие задачи и объекты.</p>
    </div>`;
}

function _obRenderGroupSlide(group, idx) {
  return `
    <div class="onboarding-slide">
      <div class="onboarding-slide-label">Шаг ${idx + 1}</div>
      <h2 class="onboarding-slide-title">${group.title}</h2>
      <div class="onboarding-skills">
        ${group.items.map(s => `
          <label class="skill-chip${_obSelected.has(s) ? ' checked' : ''}" data-skill="${s.replace(/"/g, '&quot;')}">
            <input type="checkbox" value="${s}" ${_obSelected.has(s) ? 'checked' : ''}>
            <span>${s}</span>
          </label>
        `).join('')}
      </div>
    </div>`;
}

function _obRenderSizeSlide() {
  const rows = [
    { key: 'shirt', label: 'Размер одежды', icon: '👕', options: SIZE_OPTIONS.shirt },
    { key: 'pants', label: 'Размер брюк', icon: '👖', options: SIZE_OPTIONS.pants },
    { key: 'shoe', label: 'Размер обуви', icon: '👟', options: SIZE_OPTIONS.shoe },
  ];
  return `
    <div class="onboarding-slide">
      <div class="onboarding-slide-label">Последний шаг</div>
      <h2 class="onboarding-slide-title">Размеры для спецодежды</h2>
      <div class="onboarding-sizes">
        ${rows.map(row => `
          <div class="size-row">
            <div class="size-row-label"><span class="size-row-icon">${row.icon}</span>${row.label}</div>
            <div class="size-row-options">
              ${row.options.map(opt => `
                <button type="button" class="size-chip${_obSizes[row.key] === opt ? ' checked' : ''}" data-size-key="${row.key}" data-size-val="${opt}">${opt}</button>
              `).join('')}
            </div>
          </div>
        `).join('')}
        <div class="size-row">
          <div class="size-row-label"><span class="size-row-icon">🎂</span>Дата рождения (необязательно)</div>
          <input type="date" id="ob-birthday-input" class="onboarding-birthday-input" value="${_obBirthday}">
        </div>
      </div>
    </div>`;
}

function _obRenderStep(groups) {
  if (_obStep === 0) return _obRenderIntro();
  if (_obStep === groups.length + 1) return _obRenderSizeSlide();
  const group = groups[_obStep - 1];
  return _obRenderGroupSlide(group, _obStep - 1);
}

function _showQuizOverlay(skillOptions) {
  const groups = _obGroupsFromOptions(skillOptions);
  _obStep = 0;
  _obSelected = new Set();

  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.id = 'onboarding-overlay';

    function render() {
      const total = _obTotalSteps(groups);
      const isLast = _obStep === total - 1;
      overlay.innerHTML = `
        <div class="onboarding-card">
          ${_obRenderDots(groups)}
          <div class="onboarding-slide-wrap"><div class="onboarding-slide-anim onboarding-anim-${_obDirection}">${_obRenderStep(groups)}</div></div>
          <div class="onboarding-nav-row">
            ${_obStep > 0 ? `<button class="onboarding-back-btn" id="onboarding-back" type="button">← Назад</button>` : '<span></span>'}
            <button class="onboarding-submit-btn" id="onboarding-next" type="button">${isLast ? 'Готово ✓' : 'Далее →'}</button>
          </div>
          <div class="onboarding-error" id="onboarding-error" style="display:none"></div>
        </div>
      `;

      overlay.querySelectorAll('.skill-chip').forEach(chip => {
        chip.addEventListener('click', e => {
          if (e.target.tagName !== 'INPUT') e.preventDefault();
          const skill = chip.dataset.skill;
          const checkbox = chip.querySelector('input');
          if (_obSelected.has(skill)) {
            _obSelected.delete(skill);
            checkbox.checked = false;
          } else {
            _obSelected.add(skill);
            checkbox.checked = true;
          }
          chip.classList.toggle('checked', _obSelected.has(skill));
          hapticImpact('light');
        });
      });

      overlay.querySelectorAll('.size-chip').forEach(chip => {
        chip.addEventListener('click', () => {
          const key = chip.dataset.sizeKey;
          const val = chip.dataset.sizeVal;
          _obSizes[key] = val;
          overlay.querySelectorAll(`.size-chip[data-size-key="${key}"]`).forEach(c => c.classList.toggle('checked', c.dataset.sizeVal === val));
          hapticImpact('light');
        });
      });

      const backBtn = document.getElementById('onboarding-back');
      if (backBtn) backBtn.addEventListener('click', () => { _obDirection = 'back'; _obStep--; render(); });

      document.getElementById('onboarding-next').addEventListener('click', async () => {
        const birthdayInput = document.getElementById('ob-birthday-input');
        if (birthdayInput) _obBirthday = birthdayInput.value;
        if (!isLast) { _obDirection = 'next'; _obStep++; render(); return; }

        const btn = document.getElementById('onboarding-next');
        const errEl = document.getElementById('onboarding-error');
        btn.disabled = true;
        btn.textContent = '...';
        errEl.style.display = 'none';

        try {
          await api('/api/profile/me', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              skills: Array.from(_obSelected), quiz_completed: true,
              shirt_size: _obSizes.shirt || null, pants_size: _obSizes.pants || null, shoe_size: _obSizes.shoe || null,
              birthday: _obBirthday || null,
            })
          });
          overlay.classList.add('onboarding-fade-out');
          setTimeout(() => { overlay.remove(); resolve(); }, 350);
        } catch (e) {
          errEl.textContent = 'Ошибка сохранения, попробуйте ещё раз';
          errEl.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Готово ✓';
        }
      });
    }

    render();
    document.body.appendChild(overlay);
  });
}
