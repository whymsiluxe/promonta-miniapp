// Единый компонент выбора навыков -- используется onboarding.js (шаги 2-3) и
// profile.js (Профиль → Настройки → Навыки). Единственный источник данных --
// GET /api/work-types (backend/work_types.py), никаких статичных копий каталога
// здесь или где-либо ещё во frontend.
//
// Два режима работы:
//  - createSkillPicker(container, {onChange}) -- выбор набора skill_id (шаг 2 onboarding,
//    открытие редактирования навыков в профиле). featured-карточки сверху + поиск +
//    группы-аккордеоны, один тап переключает выбор, featured и группа -- одно состояние.
//  - createSkillLevelPicker(container, selectedIds, {onChange}) -- уровень для каждого
//    уже выбранного навыка (шаг 3 onboarding).

let _skillCatalogCache = null;

async function _loadSkillCatalog() {
  if (_skillCatalogCache) return _skillCatalogCache;
  _skillCatalogCache = await api('/api/work-types');
  return _skillCatalogCache;
}

function _allCatalogItems(catalog) {
  const items = [];
  for (const g of catalog.groups) items.push(...g.items);
  return items;
}

/**
 * createSkillPicker(container, opts)
 *   opts.initialSelected -- Set<string> skill_id, предвыбранные навыки
 *   opts.onChange(selectedSet) -- вызывается при каждом изменении выбора
 * Возвращает { getSelected(): Set<string>, destroy() }.
 */
async function createSkillPicker(container, opts = {}) {
  const selected = new Set(opts.initialSelected || []);
  const onChange = opts.onChange || (() => {});
  let catalog;
  try {
    catalog = await _loadSkillCatalog();
  } catch (e) {
    container.innerHTML = `<div class="skill-picker-error">Не удалось загрузить список работ. <button type="button" class="skill-picker-retry-btn">Повторить</button></div>`;
    container.querySelector('.skill-picker-retry-btn')?.addEventListener('click', () => {
      _skillCatalogCache = null;
      createSkillPicker(container, opts);
    });
    return { getSelected: () => selected, destroy: () => {} };
  }

  let openGroupId = null;
  let searchQuery = '';

  function isSelected(id) { return selected.has(id); }

  function toggle(id) {
    if (selected.has(id)) selected.delete(id); else selected.add(id);
    render();
    onChange(selected);
  }

  function render() {
    const q = searchQuery.trim().toLowerCase();
    const featuredHtml = catalog.featured.map(w => `
      <button type="button" class="skill-picker-featured-card${isSelected(w.id) ? ' selected' : ''}" data-skill-id="${w.id}">
        ${isSelected(w.id) ? '<span class="skill-picker-check">✓</span>' : ''}
        <span class="skill-picker-featured-name">${_escSkill(w.name)}</span>
      </button>
    `).join('');

    let groupsHtml;
    if (q) {
      const matches = _allCatalogItems(catalog).filter(w =>
        w.name.toLowerCase().includes(q) || (w.keywords || []).some(k => k.toLowerCase().includes(q))
      );
      groupsHtml = `<div class="skill-picker-search-results">${matches.map(w => _skillRowHtml(w, isSelected(w.id))).join('') || '<div class="skill-picker-empty">Ничего не найдено</div>'}</div>`;
    } else {
      groupsHtml = catalog.groups.map(g => {
        const isOpen = openGroupId === g.id;
        const selectedCount = g.items.filter(w => isSelected(w.id)).length;
        return `
          <div class="skill-picker-group${isOpen ? ' open' : ''}">
            <button type="button" class="skill-picker-group-header" data-group-id="${g.id}">
              <span>${_escSkill(g.name)}</span>
              ${selectedCount ? `<span class="skill-picker-group-badge">${selectedCount}</span>` : ''}
              <span class="skill-picker-group-chevron">${isOpen ? '▾' : '▸'}</span>
            </button>
            ${isOpen ? `<div class="skill-picker-group-body">${g.items.map(w => _skillRowHtml(w, isSelected(w.id))).join('')}</div>` : ''}
          </div>
        `;
      }).join('');
    }

    container.innerHTML = `
      <div class="skill-picker-featured-label">Часто используемые</div>
      <div class="skill-picker-featured-grid">${featuredHtml}</div>
      <div class="skill-picker-all-label">Все навыки</div>
      <input type="search" class="skill-picker-search-input" placeholder="Поиск..." value="${_escSkill(searchQuery)}">
      <div class="skill-picker-groups">${groupsHtml}</div>
    `;

    container.querySelectorAll('[data-skill-id]').forEach(el => {
      el.addEventListener('click', () => toggle(el.dataset.skillId));
    });
    container.querySelectorAll('[data-group-id]').forEach(el => {
      el.addEventListener('click', () => {
        const gid = el.dataset.groupId;
        openGroupId = openGroupId === gid ? null : gid; // одновременно раскрыта только одна группа
        render();
      });
    });
    const searchInput = container.querySelector('.skill-picker-search-input');
    searchInput?.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      render();
    });
    if (document.activeElement === searchInput) searchInput.focus();
  }

  render();
  return { getSelected: () => selected, destroy: () => { container.innerHTML = ''; } };
}

function _skillRowHtml(w, selected) {
  return `
    <button type="button" class="skill-picker-row${selected ? ' selected' : ''}" data-skill-id="${w.id}">
      <span class="skill-picker-row-name">${_escSkill(w.name)}</span>
      ${selected ? '<span class="skill-picker-check">✓</span>' : ''}
    </button>
  `;
}

/**
 * createSkillLevelPicker(container, skillIds, opts)
 *   skillIds -- array<string> уже выбранных skill_id
 *   opts.initialLevels -- Map<skill_id, level> предзаполненные уровни (редактирование)
 *   opts.onChange(levelsMap) -- вызывается при каждом изменении
 * Возвращает { getLevels(): Map<string,string>, isComplete(): bool, destroy() }.
 */
async function createSkillLevelPicker(container, skillIds, opts = {}) {
  const levels = new Map(opts.initialLevels || []);
  const onChange = opts.onChange || (() => {});
  const catalog = await _loadSkillCatalog();
  const byId = {};
  _allCatalogItems(catalog).forEach(w => { byId[w.id] = w; });
  for (const w of catalog.featured) byId[w.id] = w; // featured items тоже должны резолвиться

  const LEVEL_LABELS = { helper: 'Помощник', independent: 'Самостоятельно', master: 'Мастер' };

  function setLevel(skillId, level) {
    levels.set(skillId, level);
    render();
    onChange(levels);
  }

  function isComplete() {
    return skillIds.every(id => levels.has(id));
  }

  function render() {
    const doneCount = skillIds.filter(id => levels.has(id)).length;
    container.innerHTML = `
      <div class="skill-level-progress">Уровень указан: ${doneCount} из ${skillIds.length}</div>
      <div class="skill-level-explain">
        <div><b>Помощник</b> — работаю под руководством</div>
        <div><b>Самостоятельно</b> — выполняю работу сам</div>
        <div><b>Мастер</b> — отвечаю за результат и могу руководить</div>
      </div>
      <div class="skill-level-list">
        ${skillIds.map(id => {
          const name = byId[id] ? byId[id].name : id;
          const current = levels.get(id);
          return `
            <div class="skill-level-row">
              <div class="skill-level-row-name">${_escSkill(name)}</div>
              <div class="skill-level-buttons">
                ${['helper', 'independent', 'master'].map(lv => `
                  <button type="button" class="skill-level-btn${current === lv ? ' selected' : ''}" data-skill-id="${id}" data-level="${lv}">${LEVEL_LABELS[lv]}</button>
                `).join('')}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
    container.querySelectorAll('.skill-level-btn').forEach(btn => {
      btn.addEventListener('click', () => setLevel(btn.dataset.skillId, btn.dataset.level));
    });
  }

  render();
  return { getLevels: () => levels, isComplete, destroy: () => { container.innerHTML = ''; } };
}

function _escSkill(s) {
  const div = document.createElement('div');
  div.textContent = s == null ? '' : String(s);
  return div.innerHTML;
}
