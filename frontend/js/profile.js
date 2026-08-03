// Профиль (Фаза 8 → Раунд1): чёткое разделение.
//   * Owner Profile = ЛИЧНЫЙ + административный (3 вкладки: Профиль | Доступ | Настройки).
//     Никаких worker-часов/колец/навыков/размеров/отпуска/выбора чужого сотрудника.
//   * Worker self-profile (когда Worker смотрит СЕБЯ) = полный (кольца часов, отпуск,
//     доступность, объекты, навыки, размеры) — не сломан, ветка по currentRole.
//   * Worker Card = ОТДЕЛЬНЫЙ режим-overlay (openWorkerCard), НЕ подмена профиля Owner:
//     часы/смена/объекты/навыки/доступность/размеры/табель для конкретного uid.
//     Открывается из Команды/объекта/доступа/аватара; Back возвращает туда, откуда открыт.

const WEEKDAY_LETTERS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const PROFILE_DAY_NORM_HOURS = 10; // 100% кольца = 10ч в день

let _profileStatsUserId = ''; // пусто = я сам (worker-self). Owner-self НЕ смотрит чужих тут.
let _profilePeriod = 'week'; // period-pills worker-self — week/month/3months/year
const PROFILE_PERIOD_LABEL = { week: 'Неделя', month: 'Месяц', '3months': '3 месяца', year: 'Год' };

// Раунд1 Задача 2.3: явный режим + точка возврата для Worker Card.
let _profileMode = 'owner-self'; // 'owner-self' | 'worker-card'
let _profileReturnView = null;   // куда вернуться из Worker Card (Back)

function initProfileView() {
  const slot = document.getElementById('profile-content');
  if (!slot) return;
  // Bottom-nav "Профиль" ВСЕГДА показывает СВОЙ профиль. Worker Card — отдельный overlay.
  _profileStatsUserId = '';
  _profileMode = 'owner-self';
  if (currentRole === 'owner') _renderOwnerSelfProfile(slot);
  else _renderWorkerSelfProfile(slot);
}

// ─────────────────────────── OWNER: личный + административный ───────────────────────────

function _renderOwnerSelfProfile(slot) {
  slot.innerHTML = `
    <div class="profile-header-card">
      <div class="profile-avatar-wrap" id="profile-avatar-wrap" title="Сменить фото">
        <img id="profile-avatar-img" alt="" style="display:none">
        <span id="profile-avatar-fallback"><svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg></span>
        <span class="profile-avatar-edit"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg></span>
      </div>
      <input type="file" id="profile-avatar-input" accept="image/*" style="display:none">
      <div class="profile-header-info">
        <div class="profile-name" id="profile-name">Загрузка…</div>
        <div class="profile-role-badge" id="profile-role-badge">Владелец</div>
        <div class="profile-secondary-id" id="profile-telegram-id"></div>
      </div>
    </div>

    <div class="profile-tabs" id="profile-tabs">
      <div class="profile-tab active" data-tab="me">Профиль</div>
      <div class="profile-tab" data-tab="team">Доступ</div>
      <div class="profile-tab" data-tab="settings">Настройки</div>
    </div>

    <div class="profile-tab-panel" data-panel="me">
      <div class="card">
        <div class="profile-owner-actions">
          <button class="profile-owner-action-btn" id="profile-owner-edit-name" type="button">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"></path></svg>
            Изменить имя
          </button>
          <button class="profile-owner-action-btn" id="profile-owner-edit-photo" type="button">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
            Изменить фото
          </button>
        </div>
      </div>
      <div class="card">
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title">Приложение</span>
        </div>
        <div id="profile-app-status" class="profile-app-status">
          <div class="profile-app-status-row"><span>Версия</span><span id="profile-app-version">—</span></div>
          <div class="profile-app-status-row"><span>AI-ассистент</span><span>GLM-режим</span></div>
        </div>
      </div>
    </div>

    <div class="profile-tab-panel" data-panel="team" style="display:none">
      <div class="accordion-section" style="display:block">
        <div id="profile-team-list" style="font-size:0.85rem;color:var(--text-light);padding:0.75rem 0">Загрузка…</div>
      </div>
    </div>

    <div class="profile-tab-panel" data-panel="settings" style="display:none">
      <div class="card">
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title">Имя</span>
        </div>
        <input type="text" id="profile-name-input" class="mangel-select" placeholder="Например: Иван" maxlength="100">
        <button class="submit-btn profile-inline-btn" id="profile-name-save-btn" type="button" style="margin-top:0.5rem">Сохранить имя</button>
        <div id="profile-name-status" style="font-size:0.8rem;color:var(--accent);margin-top:0.4rem"></div>
      </div>
      <div class="card">
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title">Фото профиля</span>
        </div>
        <button class="submit-btn profile-inline-btn" id="profile-settings-photo-btn" type="button">Изменить фото</button>
      </div>
      <div class="card">
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title">Система</span>
        </div>
        <div id="profile-settings-sysinfo" class="profile-app-status"></div>
      </div>
    </div>
  `;

  _bindProfileTabs();
  _bindOwnerSelfHandlers();
  _loadOwnerSelfProfile();
  _loadProfileTeam();
}

function _bindOwnerSelfHandlers() {
  const wrap = document.getElementById('profile-avatar-wrap');
  const input = document.getElementById('profile-avatar-input');
  const triggerPhoto = () => input && input.click();
  wrap?.addEventListener('click', triggerPhoto);
  document.getElementById('profile-owner-edit-photo')?.addEventListener('click', triggerPhoto);
  document.getElementById('profile-settings-photo-btn')?.addEventListener('click', triggerPhoto);
  document.getElementById('profile-owner-edit-name')?.addEventListener('click', () => {
    // переключить на вкладку Настройки, где поле имени
    const settingsTab = document.querySelector('#profile-tabs .profile-tab[data-tab="settings"]');
    settingsTab?.click();
    setTimeout(() => document.getElementById('profile-name-input')?.focus(), 60);
  });
  input?.addEventListener('change', async () => {
    if (!input.files || !input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    try {
      const res = await fetch(`${API_BASE}/api/profile/me/avatar`, { method: 'POST', headers: { ..._authHeaders() }, body: fd });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      hapticImpact('light');
      _loadAvatar(String(window._profileMyUserId || ''));
    } catch (e) {
      showToast('Ошибка загрузки аватара: ' + e.message, 'error');
    }
    input.value = '';
  });
  document.getElementById('profile-name-save-btn')?.addEventListener('click', _saveName);
}

async function _loadOwnerSelfProfile() {
  let stats;
  try {
    stats = await api('/api/profile/stats');
  } catch (e) {
    document.getElementById('profile-name').textContent = 'Ошибка загрузки профиля';
    return;
  }
  window._profileMyUserId = stats.user_id;
  document.getElementById('profile-name').textContent = stats.name || 'Владелец';
  const idEl = document.getElementById('profile-telegram-id');
  if (idEl) idEl.textContent = 'Telegram ID: ' + stats.user_id;
  const nameInput = document.getElementById('profile-name-input');
  if (nameInput) nameInput.value = (stats.name && stats.name !== String(stats.user_id)) ? stats.name : '';

  if (stats.has_avatar) _loadAvatar(stats.user_id);
  else {
    const img = document.getElementById('profile-avatar-img');
    const fb = document.getElementById('profile-avatar-fallback');
    if (img) img.style.display = 'none';
    if (fb) fb.style.display = 'block';
  }

  // Компактный статус приложения (версия/SHA из существующего /api/health — новых
  // health-эндпоинтов не добавляем, ТЗ 2.2).
  try {
    const h = await api('/api/health');
    const ver = h.version && h.version !== 'unknown' ? h.version : '';
    const commit = h.commit ? String(h.commit).slice(0, 7) : '';
    const label = [ver, commit].filter(Boolean).join(' · ') || '—';
    const vEl = document.getElementById('profile-app-version');
    if (vEl) vEl.textContent = label;
    const sys = document.getElementById('profile-settings-sysinfo');
    if (sys) sys.innerHTML = `
      <div class="profile-app-status-row"><span>Версия</span><span>${esc(ver || '—')}</span></div>
      <div class="profile-app-status-row"><span>Commit</span><span>${esc(commit || '—')}</span></div>`;
  } catch (e) {}
}

// ─────────────────────────── WORKER: полный собственный профиль ───────────────────────────

function _renderWorkerSelfProfile(slot) {
  slot.innerHTML = `
    <div class="profile-header-card">
      <div class="profile-avatar-wrap" id="profile-avatar-wrap" title="Сменить фото">
        <img id="profile-avatar-img" alt="" style="display:none">
        <span id="profile-avatar-fallback"><svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg></span>
        <span class="profile-avatar-edit">📷</span>
      </div>
      <input type="file" id="profile-avatar-input" accept="image/*" style="display:none">
      <div class="profile-header-info">
        <div class="profile-name" id="profile-name">Загрузка…</div>
        <div class="profile-role-badge" id="profile-role-badge"></div>
      </div>
    </div>

    <div class="profile-tabs" id="profile-tabs">
      <div class="profile-tab active" data-tab="me">Мой профиль</div>
      <div class="profile-tab" data-tab="settings">Настройки</div>
    </div>

    <div class="profile-tab-panel" data-panel="me">
      <div class="card profile-week-card">
        <div class="profile-period-pills" id="profile-period-pills">
          ${Object.keys(PROFILE_PERIOD_LABEL).map(p =>
            `<div class="profile-period-pill${p === _profilePeriod ? ' active' : ''}" data-period="${p}">${PROFILE_PERIOD_LABEL[p]}</div>`
          ).join('')}
        </div>
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title" id="profile-period-title">Часы за 7 дней</span>
          <span class="profile-week-total" id="profile-week-total">—</span>
        </div>
        <div class="profile-week-rings" id="profile-week-rings">
          <div style="color:var(--text-light);font-size:0.85rem">Загрузка…</div>
        </div>
        <a class="profile-csv-link-secondary" id="profile-export-stundenzettel-btn">Скачать табель (CSV)</a>
      </div>

      <div class="card profile-urlaub-card" id="profile-urlaub-card" style="display:none;">
        <div class="home-section-header" style="padding:0 0 0.5rem;">
          <span class="home-section-title">Отпуск</span>
          <span class="profile-week-total" id="profile-urlaub-remaining">—</span>
        </div>
        <div class="profile-urlaub-bar"><div class="profile-urlaub-bar-fill" id="profile-urlaub-bar-fill"></div></div>
        <div class="profile-urlaub-caption" id="profile-urlaub-caption"></div>
      </div>

      <div class="card profile-speed-card" id="profile-speed-card" style="display:none"></div>

      <div class="accordion-section" id="profile-availability-section" style="display:none">
        <div class="accordion-header"><span class="accordion-icon" style="background:var(--icon-bg-2)">📅</span><span class="accordion-title">Доступность</span><span class="accordion-chevron">▾</span></div>
        <div class="accordion-body collapsed"><div class="accordion-body-inner">
          <div id="profile-availability-summary" style="font-size:0.85rem;color:var(--text-light)">—</div>
          <button class="submit-btn profile-inline-btn" id="profile-availability-link-btn" type="button" onclick="switchView('abwesenheit')">Открыть календарь →</button>
        </div></div>
      </div>

      <div class="accordion-section">
        <div class="accordion-header"><span class="accordion-icon" style="background:var(--icon-bg-5)">🏗️</span><span class="accordion-title">Объекты</span><span class="accordion-chevron">▾</span></div>
        <div class="accordion-body collapsed"><div class="accordion-body-inner"><div id="profile-objects-list"></div></div></div>
      </div>
    </div>

    <div class="profile-tab-panel" data-panel="settings" style="display:none">
      <div class="accordion-section">
        <div class="accordion-header"><span class="accordion-icon" style="background:var(--icon-bg-4)">✎</span><span class="accordion-title">Имя</span><span class="accordion-chevron">▾</span></div>
        <div class="accordion-body collapsed"><div class="accordion-body-inner">
          <div style="font-size:0.8rem;color:var(--text-light);margin-bottom:0.5rem">Telegram молчит о твоём имени? Представься тут 👋</div>
          <input type="text" id="profile-name-input" class="mangel-select" placeholder="Например: Иван" maxlength="100">
          <button class="submit-btn profile-inline-btn" id="profile-name-save-btn" type="button" style="margin-top:0.5rem">Сохранить имя</button>
          <div id="profile-name-status" style="font-size:0.8rem;color:var(--accent);margin-top:0.4rem"></div>
        </div></div>
      </div>

      <div class="accordion-section">
        <div class="accordion-header"><span class="accordion-icon" style="background:var(--icon-bg-1)">🛠</span><span class="accordion-title">Навыки</span><span class="accordion-chevron">▾</span></div>
        <div class="accordion-body collapsed"><div class="accordion-body-inner">
          <div id="profile-skills-chips" class="profile-skills-chips"></div>
          <div id="profile-skills-edit" style="display:none"></div>
          <button class="submit-btn profile-inline-btn" id="profile-skills-edit-btn" type="button">Изменить навыки</button>
        </div></div>
      </div>

      <div class="accordion-section">
        <div class="accordion-header"><span class="accordion-icon" style="background:var(--icon-bg-2)">👕</span><span class="accordion-title">Размеры одежды</span><span class="accordion-chevron">▾</span></div>
        <div class="accordion-body collapsed"><div class="accordion-body-inner">
          <div class="profile-sizes-grid">
            <label>Штаны<input id="profile-size-pants" class="mangel-select" placeholder="напр. 52 / L"></label>
            <label>Футболка<input id="profile-size-shirt" class="mangel-select" placeholder="напр. XL"></label>
            <label>Обувь<input id="profile-size-shoe" class="mangel-select" placeholder="напр. 44"></label>
          </div>
          <button class="submit-btn profile-inline-btn" id="profile-sizes-save-btn" type="button">Сохранить размеры</button>
          <div id="profile-sizes-status" style="font-size:0.8rem;color:var(--accent);margin-top:0.4rem"></div>
        </div></div>
      </div>
    </div>
  `;

  initAccordions(document.getElementById('view-profile'));
  _bindProfileTabs();
  _bindProfileHandlers();
  _loadProfileStats();
  _loadProfileAvailabilitySummary();
}

function _bindProfileTabs() {
  const tabs = document.getElementById('profile-tabs');
  if (!tabs) return;
  tabs.addEventListener('click', e => {
    const tab = e.target.closest('.profile-tab');
    if (!tab) return;
    tabs.querySelectorAll('.profile-tab').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('#view-profile .profile-tab-panel').forEach(panel => {
      panel.style.display = panel.dataset.panel === tab.dataset.tab ? '' : 'none';
    });
    hapticImpact('light');
  });
}

// 21.07: worker — summary-строка Urlaub-баланс + deep-link в Календарь.
async function _loadProfileAvailabilitySummary() {
  const section = document.getElementById('profile-availability-section');
  const summaryEl = document.getElementById('profile-availability-summary');
  if (!section || !summaryEl) return;
  try {
    const stats = await api('/api/profile/stats');
    section.style.display = 'block';
    if (stats.urlaub) {
      summaryEl.textContent = `Urlaub: ${stats.urlaub.remaining}/${stats.urlaub.total} осталось`;
    }
  } catch (e) {}
}

// Owner "Доступ": управление whitelist (backend /api/roles). Чисто административная вкладка.
async function _loadProfileTeam() {
  const listEl = document.getElementById('profile-team-list');
  if (!listEl) return;
  try {
    const data = await api('/api/roles');
    const teamAvatar = (uid, name) => `<span class="profile-team-avatar" style="background:hsl(${_chatAvatarHue(uid)} 45% 42%)" onclick="openUserCard('${esc(uid)}')">${(name || '?')[0].toUpperCase()}</span>`;

    const rows = (data.roles || []).map(r => `
      <div class="profile-team-row">
        ${teamAvatar(r.user_id, r.name)}
        <span class="profile-team-name">${esc(r.name)} <span style="color:var(--text-light);font-size:0.75rem">(${r.role === 'owner' ? 'владелец' : 'работник'})</span></span>
        ${r.role !== 'owner' ? `<button class="profile-team-revoke-btn" data-uid="${esc(r.user_id)}">Убрать</button>` : ''}
      </div>`).join('');
    const pendingRows = (data.pending || []).map(p => `
      <div class="profile-team-row">
        ${teamAvatar(p.user_id, p.name)}
        <span class="profile-team-name">${esc(p.name)} <span style="color:var(--warning);font-size:0.75rem">(ожидает доступа)</span></span>
        <button class="profile-team-grant-btn" data-uid="${esc(p.user_id)}">Дать доступ</button>
      </div>`).join('');
    listEl.innerHTML = (rows || '') + (pendingRows || '') || 'Пока никого нет.';
    listEl.querySelectorAll('.profile-team-revoke-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Убрать доступ этому работнику?')) return;
        try {
          await api(`/api/roles/${btn.dataset.uid}`, { method: 'DELETE' });
          hapticImpact('medium');
          _loadProfileTeam();
        } catch (e) { showToast('Ошибка: ' + e.message, 'error'); }
      });
    });
    listEl.querySelectorAll('.profile-team-grant-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
          await api('/api/roles', { method: 'POST', body: JSON.stringify({ user_id: btn.dataset.uid, role: 'worker' }) });
          hapticImpact('light');
          _loadProfileTeam();
        } catch (e) {
          showToast('Ошибка: ' + e.message, 'error');
          btn.disabled = false;
        }
      });
    });
  } catch (e) {
    listEl.textContent = 'Ошибка загрузки команды: ' + e.message;
  }
}

// Worker-self handlers.
function _bindProfileHandlers() {
  const wrap = document.getElementById('profile-avatar-wrap');
  const input = document.getElementById('profile-avatar-input');
  wrap.addEventListener('click', () => { input.click(); });
  input.addEventListener('change', async () => {
    if (!input.files || !input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    try {
      const res = await fetch(`${API_BASE}/api/profile/me/avatar`, { method: 'POST', headers: { ..._authHeaders() }, body: fd });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      hapticImpact('light');
      _loadAvatar(String(window._profileMyUserId || ''));
    } catch (e) {
      showToast('Ошибка загрузки аватара: ' + e.message, 'error');
    }
    input.value = '';
  });

  document.getElementById('profile-skills-edit-btn').addEventListener('click', _toggleSkillsEdit);
  document.getElementById('profile-sizes-save-btn').addEventListener('click', _saveSizes);
  document.getElementById('profile-name-save-btn').addEventListener('click', _saveName);
  document.getElementById('profile-export-stundenzettel-btn').addEventListener('click', _downloadStundenzettel);

  document.getElementById('profile-period-pills').addEventListener('click', e => {
    const pill = e.target.closest('.profile-period-pill');
    if (!pill || pill.dataset.period === _profilePeriod) return;
    _profilePeriod = pill.dataset.period;
    document.querySelectorAll('#view-profile .profile-period-pill').forEach(p => p.classList.toggle('active', p.dataset.period === _profilePeriod));
    hapticImpact('light');
    _loadProfileStats();
  });
}

async function _downloadStundenzettel() {
  const btn = document.getElementById('profile-export-stundenzettel-btn');
  btn.disabled = true;
  try {
    const targetId = _profileStatsUserId || '';
    const res = await fetch(`${API_BASE}/api/checkin/stundenzettel?user_id=${targetId}`, { headers: { ..._authHeaders() } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || 'Stundenzettel.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка экспорта: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

// img src не умеет слать X-Telegram-Init-Data — тянем blob через fetch.
async function _loadAvatar(uid) {
  const img = document.getElementById('profile-avatar-img');
  const fallback = document.getElementById('profile-avatar-fallback');
  if (!img || !uid) return;
  try {
    const res = await fetch(`${API_BASE}/api/profile/${uid}/avatar`, { headers: { ..._authHeaders() } });
    if (!res.ok) return;
    img.src = URL.createObjectURL(await res.blob());
    img.style.display = 'block';
    fallback.style.display = 'none';
  } catch (e) {}
}

async function _loadProfileStats() {
  const params = new URLSearchParams();
  if (_profileStatsUserId) params.set('user_id', _profileStatsUserId);
  params.set('period', _profilePeriod);
  let stats;
  try {
    stats = await api('/api/profile/stats?' + params.toString());
  } catch (e) {
    document.getElementById('profile-name').textContent = 'Ошибка загрузки профиля';
    return;
  }
  if (!_profileStatsUserId) window._profileMyUserId = stats.user_id;

  document.getElementById('profile-name').textContent = stats.name || stats.user_id;
  const roleBadge = document.getElementById('profile-role-badge');
  roleBadge.textContent = stats.role === 'owner' ? 'Владелец' : 'Работник';

  if (stats.has_avatar) _loadAvatar(stats.user_id);
  else {
    const img = document.getElementById('profile-avatar-img');
    const fb = document.getElementById('profile-avatar-fallback');
    if (img) { img.style.display = 'none'; }
    if (fb) { fb.style.display = 'block'; }
  }

  const rings = document.getElementById('profile-week-rings');
  const periodTitle = document.getElementById('profile-period-title');
  const pd = stats.period_data;
  if (stats.period === 'week' || !pd) {
    periodTitle.textContent = 'Часы за 7 дней';
    rings.className = 'profile-week-rings';
    rings.innerHTML = (stats.week || []).map(d => {
      const pct = Math.min(100, d.hours / PROFILE_DAY_NORM_HOURS * 100);
      const hoursLabel = d.hours > 0 ? (Math.round(d.hours * 10) / 10) + '' : '·';
      return `
        <div class="profile-day-ring">
          ${renderRingProgress(pct, 40, 4, hoursLabel)}
          <div class="profile-day-letter">${WEEKDAY_LETTERS[d.weekday]}</div>
        </div>`;
    }).join('');
    document.getElementById('profile-week-total').textContent = (stats.week_total_hours || 0) + ' ч';
  } else if (pd.kind === 'heatmap') {
    periodTitle.textContent = 'Часы за месяц';
    rings.className = 'profile-month-heatmap';
    const maxH = Math.max(1, ...pd.days.map(d => d.hours));
    rings.innerHTML = pd.days.map(d => {
      const intensity = d.hours > 0 ? Math.min(1, d.hours / maxH) : 0;
      return `<div class="profile-heatmap-cell" style="background:color-mix(in srgb, var(--accent) ${Math.round(intensity * 100)}%, var(--bg-card-raised))" title="${d.date}: ${d.hours}ч"></div>`;
    }).join('');
    document.getElementById('profile-week-total').textContent = pd.total_hours + ' ч';
  } else if (pd.kind === 'bar') {
    periodTitle.textContent = stats.period === '3months' ? 'Часы за 3 месяца' : 'Часы за год';
    rings.className = 'profile-period-bar-chart';
    const maxH = Math.max(1, ...pd.buckets.map(b => b.hours));
    rings.innerHTML = pd.buckets.map(b =>
      `<div class="profile-bar-col" title="${b.label}: ${b.hours}ч"><div class="profile-bar-fill" style="height:${Math.round(b.hours / maxH * 100)}%"></div></div>`
    ).join('');
    document.getElementById('profile-week-total').textContent = pd.total_hours + ' ч';
  }

  if (stats.role === 'worker' && stats.urlaub) {
    const card = document.getElementById('profile-urlaub-card');
    card.style.display = 'block';
    const pct = Math.min(100, (stats.urlaub.used / stats.urlaub.total) * 100);
    document.getElementById('profile-urlaub-bar-fill').style.width = pct + '%';
    document.getElementById('profile-urlaub-remaining').textContent = `${stats.urlaub.remaining} дн. осталось`;
    document.getElementById('profile-urlaub-caption').textContent =
      `Использовано ${stats.urlaub.used} из ${stats.urlaub.total} дней в этом году`;
  }

  const speedCard = document.getElementById('profile-speed-card');
  if (stats.work_speed || stats.avg_session_hours) {
    const ws = stats.work_speed;
    const avgPct = stats.avg_session_hours ? Math.min(100, stats.avg_session_hours / 8 * 100) : 0;
    speedCard.style.display = 'block';
    speedCard.innerHTML = `
      <div class="profile-speed-row">
        ${renderRingProgress(avgPct, 56, 5, (stats.avg_session_hours || 0) + 'ч')}
        <div class="profile-speed-text">
          <div style="font-weight:600">Работа по фото</div>
          <div style="font-size:0.8rem;color:var(--text-light)">
            ${ws
              ? `AI-анализов смен: ${ws.analyzed_sessions}. ${ws.last_summary}`
              : 'Средняя длина смены по check-in фото. AI-заметки по прогрессу появятся после первого анализа смены.'}
          </div>
        </div>
      </div>`;
  } else {
    speedCard.style.display = 'block';
    speedCard.innerHTML = `<div style="font-size:0.85rem;color:var(--text-light);display:flex;align-items:center;gap:0.4rem">
      <svg viewBox="0 0 24 24" width="16" height="16" style="flex-shrink:0"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      Работа по фото: пока нет данных — сделайте первый check-in смены с фото на объекте.</div>`;
  }

  const objList = document.getElementById('profile-objects-list');
  const objects = stats.objects || [];
  objList.innerHTML = objects.length
    ? objects.map(o => `
        <div class="profile-object-row">
          <div class="profile-object-name">${esc(o.object_name)}</div>
          <div class="profile-object-meta">
            ${o.sessions ? `${o.sessions} смен · ${o.total_hours} ч` : ''}
            ${o.assigned_stages && o.assigned_stages.length ? ` · назначен: ${esc(o.assigned_stages.join(', '))}` : ''}
            ${o.last_date ? ` · ${o.last_date}` : ''}
          </div>
        </div>`).join('')
    : '<div style="font-size:0.85rem;color:var(--text-light)">Пока нет ни смен, ни назначений на объекты.</div>';

  await _ensureProfileSkillCatalogCache();
  const chips = document.getElementById('profile-skills-chips');
  const skillsV2 = stats.skills_v2 || [];
  chips.innerHTML = skillsV2.length
    ? skillsV2.map(s => {
        const name = _skillLevelDisplayName(s.skill_id);
        const levelLabel = { helper: 'Помощник', independent: 'Самостоятельно', master: 'Мастер' }[s.level] || s.level;
        const verifiedBadge = s.verified ? '<div class="profile-skill-verified">✓ Подтверждено компанией</div>' : '';
        return `<div class="profile-skill-chip-v2">
          <div class="profile-skill-chip-name">${esc(name)}</div>
          <div class="profile-skill-chip-level">${esc(levelLabel)}</div>
          ${verifiedBadge}
        </div>`;
      }).join('')
    : '<div style="font-size:0.85rem;color:var(--text-light)">Навыки не указаны.</div>';

  const nameInput = document.getElementById('profile-name-input');
  if (nameInput) nameInput.value = (stats.name && stats.name !== String(stats.user_id)) ? stats.name : '';

  document.getElementById('profile-size-pants').value = stats.sizes?.pants || '';
  document.getElementById('profile-size-shirt').value = stats.sizes?.shirt || '';
  document.getElementById('profile-size-shoe').value = stats.sizes?.shoe || '';
}

let _profileSkillCatalogByIdCache = null;

async function _ensureProfileSkillCatalogCache() {
  if (_profileSkillCatalogByIdCache) return;
  try {
    const catalog = await api('/api/work-types');
    _profileSkillCatalogByIdCache = {};
    for (const g of catalog.groups) for (const w of g.items) _profileSkillCatalogByIdCache[w.id] = w.name;
    for (const w of catalog.featured) _profileSkillCatalogByIdCache[w.id] = w.name;
  } catch (e) {
    _profileSkillCatalogByIdCache = {};
  }
}

function _skillLevelDisplayName(skillId) {
  return (_profileSkillCatalogByIdCache && _profileSkillCatalogByIdCache[skillId]) || skillId;
}

// Редактирование навыков worker-self через общий skill-picker.js.
let _profileSkillsSheetEl = null;

async function _toggleSkillsEdit() {
  if (_profileStatsUserId) return; // defensive guard
  if (_profileSkillsSheetEl) return;

  const me = await api('/api/profile/me');
  const currentSkillsV2 = me.skills_v2 || [];
  const initialSelected = new Set(currentSkillsV2.map(s => s.skill_id));
  const initialLevels = new Map(currentSkillsV2.map(s => [s.skill_id, s.level]));

  const overlay = document.createElement('div');
  overlay.className = 'bottom-sheet-overlay open';
  overlay.innerHTML = `
    <div class="bottom-sheet-panel profile-skills-sheet">
      <div class="bottom-sheet-handle"></div>
      <div class="form-header">
        <span>Навыки</span>
        <button type="button" class="obj-stage-add-sheet-close" id="profile-skills-sheet-close">✕</button>
      </div>
      <div class="profile-skills-sheet-body" id="profile-skills-sheet-step-picker"></div>
      <div class="profile-skills-sheet-body" id="profile-skills-sheet-step-levels" style="display:none"></div>
      <div class="form-submit-bar">
        <button type="button" class="submit-btn" id="profile-skills-sheet-continue">Продолжить</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  document.body.style.overflow = 'hidden';
  _profileSkillsSheetEl = overlay;

  const closeSheet = () => {
    overlay.remove();
    document.body.style.overflow = '';
    _profileSkillsSheetEl = null;
    unregisterOverlay?.();
  };
  const unregisterOverlay = typeof NavigationManager !== 'undefined' ? NavigationManager.registerOverlay(closeSheet) : null;
  document.getElementById('profile-skills-sheet-close').addEventListener('click', closeSheet);

  const pickerContainer = document.getElementById('profile-skills-sheet-step-picker');
  const levelsContainer = document.getElementById('profile-skills-sheet-step-levels');
  const continueBtn = document.getElementById('profile-skills-sheet-continue');

  let stage = 'picker';
  const picker = await createSkillPicker(pickerContainer, {
    initialSelected,
    onChange: (selected) => { continueBtn.disabled = selected.size === 0; },
  });
  continueBtn.disabled = initialSelected.size === 0;

  let levelPicker = null;
  continueBtn.addEventListener('click', async () => {
    if (stage === 'picker') {
      const selectedIds = Array.from(picker.getSelected());
      if (!selectedIds.length) return;
      pickerContainer.style.display = 'none';
      levelsContainer.style.display = 'block';
      continueBtn.textContent = 'Сохранить';
      continueBtn.disabled = true;
      levelPicker = await createSkillLevelPicker(levelsContainer, selectedIds, {
        initialLevels,
        onChange: () => { continueBtn.disabled = !levelPicker.isComplete(); },
      });
      continueBtn.disabled = !levelPicker.isComplete();
      stage = 'levels';
      return;
    }
    const skillsV2 = Array.from(levelPicker.getLevels().entries()).map(([skill_id, level]) => ({ skill_id, level, verified: false }));
    continueBtn.disabled = true;
    continueBtn.textContent = 'Сохраняю...';
    try {
      await api('/api/profile/me', { method: 'PATCH', body: JSON.stringify({ skills_v2: skillsV2 }) });
      hapticImpact('light');
      closeSheet();
      _loadProfileStats();
    } catch (e) {
      showToast('Ошибка сохранения: ' + e.message, 'error');
      continueBtn.disabled = false;
      continueBtn.textContent = 'Сохранить';
    }
  });
}

async function _saveName() {
  // owner-self: _profileStatsUserId пусто -> сохраняем СВОЁ имя. Worker-self: тоже своё.
  // Гард остаётся: чужой uid никогда не редактируется через /api/profile/me.
  if (_profileStatsUserId) return;
  const input = document.getElementById('profile-name-input');
  const statusEl = document.getElementById('profile-name-status');
  const name = input.value.trim();
  if (!name) {
    statusEl.textContent = 'Введи имя';
    statusEl.style.color = 'var(--red)';
    return;
  }
  try {
    await api('/api/profile/me', { method: 'PATCH', body: JSON.stringify({ name }) });
    hapticImpact('light');
    statusEl.style.color = 'var(--accent)';
    statusEl.textContent = '✓ Сохранено';
    const nameEl = document.getElementById('profile-name');
    if (nameEl) nameEl.textContent = name;
    setTimeout(() => { statusEl.textContent = ''; }, 2500);
  } catch (e) {
    statusEl.style.color = 'var(--red)';
    statusEl.textContent = 'Ошибка: ' + e.message;
  }
}

async function _saveSizes() {
  if (_profileStatsUserId) return;
  const statusEl = document.getElementById('profile-sizes-status');
  try {
    await api('/api/profile/me', {
      method: 'PATCH',
      body: JSON.stringify({
        pants_size: document.getElementById('profile-size-pants').value.trim(),
        shirt_size: document.getElementById('profile-size-shirt').value.trim(),
        shoe_size: document.getElementById('profile-size-shoe').value.trim(),
      }),
    });
    hapticImpact('light');
    statusEl.textContent = '✓ Сохранено';
    setTimeout(() => { statusEl.textContent = ''; }, 2500);
  } catch (e) {
    statusEl.textContent = 'Ошибка: ' + e.message;
  }
}

// ─────────────────────────── WORKER CARD — отдельный режим (overlay) ───────────────────────────
// ТЗ 2.3/3: НЕ подмена профиля Owner. Собственные scoped-ID (wc-*), собственный стейт,
// не трогает _profileMyUserId/имя/avatar Owner. Back через NavigationManager.registerOverlay.

let _workerCardEl = null;          // overlay элемент; null = закрыт (двойной тап -> один overlay)
let _workerCardUserId = '';
let _workerCardPeriod = 'week';
let _workerCardUnreg = null;

// Совместимость: shared.js/openUserCard раньше звал openWorkerFullProfile.
function openWorkerFullProfile(uid) { openWorkerCard(uid); }

function openWorkerCard(uid, returnCtx) {
  if (currentRole !== 'owner') {
    if (typeof openUserCard === 'function') openUserCard(uid);
    return;
  }
  if (_workerCardEl) return; // guard: двойной тап не открывает два overlay
  _workerCardUserId = String(uid);
  _workerCardPeriod = 'week';
  _profileMode = 'worker-card';
  _profileReturnView = returnCtx || null;

  const overlay = document.createElement('div');
  overlay.className = 'worker-card-overlay';
  overlay.id = 'worker-card-overlay';
  overlay.innerHTML = `
    <div class="worker-card-panel">
      <div class="worker-card-header">
        <button type="button" class="worker-card-back" id="wc-back" aria-label="Назад">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"></path></svg>
          <span>Сотрудник</span>
        </button>
      </div>
      <div class="worker-card-identity">
        <div class="worker-card-avatar-wrap">
          <img class="worker-card-avatar" id="wc-avatar-img" alt="" style="display:none">
          <div class="worker-card-avatar-fallback" id="wc-avatar-fallback">?</div>
        </div>
        <div class="worker-card-name" id="wc-name">Загрузка…</div>
        <div class="worker-card-role" id="wc-role">Работник</div>
        <div class="worker-card-shift" id="wc-shift"></div>
      </div>
      <div class="profile-period-pills" id="wc-period-pills">
        ${Object.keys(PROFILE_PERIOD_LABEL).map(p =>
          `<div class="profile-period-pill${p === _workerCardPeriod ? ' active' : ''}" data-period="${p}">${PROFILE_PERIOD_LABEL[p]}</div>`
        ).join('')}
      </div>
      <div class="worker-card-body" id="wc-body">
        <div style="color:var(--text-light);font-size:0.85rem;padding:1rem 0">Загрузка…</div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  document.body.style.overflow = 'hidden';
  _workerCardEl = overlay;

  _workerCardUnreg = (typeof NavigationManager !== 'undefined') ? NavigationManager.registerOverlay(closeWorkerCard) : null;
  overlay.querySelector('#wc-back').addEventListener('click', closeWorkerCard);
  overlay.querySelector('#wc-period-pills').addEventListener('click', e => {
    const pill = e.target.closest('.profile-period-pill');
    if (!pill || pill.dataset.period === _workerCardPeriod) return;
    _workerCardPeriod = pill.dataset.period;
    overlay.querySelectorAll('#wc-period-pills .profile-period-pill').forEach(p => p.classList.toggle('active', p.dataset.period === _workerCardPeriod));
    hapticImpact('light');
    _loadWorkerCard();
  });

  hapticImpact('light');
  _loadWorkerCard();
}

function closeWorkerCard() {
  if (_workerCardEl) { _workerCardEl.remove(); _workerCardEl = null; }
  document.body.style.overflow = '';
  _workerCardUserId = '';
  _profileMode = 'owner-self';
  if (_workerCardUnreg) { _workerCardUnreg(); _workerCardUnreg = null; }
}

async function _loadWorkerCard() {
  const uid = _workerCardUserId;
  const body = document.getElementById('wc-body');
  if (!body) return;
  const params = new URLSearchParams();
  params.set('user_id', uid);
  params.set('period', _workerCardPeriod);
  let stats, card;
  try {
    [stats, card] = await Promise.all([
      api('/api/profile/stats?' + params.toString()),
      api(`/api/users/${encodeURIComponent(uid)}/card`).catch(() => null),
    ]);
  } catch (e) {
    body.innerHTML = `<div style="color:var(--red);padding:1rem 0">Ошибка загрузки: ${esc(e.message)}
      <button type="button" class="wo-retry-btn" onclick="_loadWorkerCard()">Повторить</button></div>`;
    return;
  }
  if (!document.getElementById('wc-body')) return; // закрыли пока грузилось

  // Шапка: имя/роль/аватар (только этой карточки, НЕ трогаем профиль Owner).
  const nameEl = document.getElementById('wc-name');
  if (nameEl) nameEl.textContent = stats.name || 'Сотрудник';
  const roleEl = document.getElementById('wc-role');
  if (roleEl) roleEl.textContent = stats.role === 'owner' ? 'Владелец' : 'Работник';
  const fb = document.getElementById('wc-avatar-fallback');
  const img = document.getElementById('wc-avatar-img');
  const initials = (stats.name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
  if (fb) fb.textContent = initials;
  if (stats.has_avatar && img) {
    img.onload = () => { img.style.display = 'block'; if (fb) fb.style.display = 'none'; };
    if (typeof authImg === 'function') authImg(img, `/api/profile/${uid}/avatar`);
  }

  // Текущая смена (owner видит shift_status в user-card).
  const shiftEl = document.getElementById('wc-shift');
  if (shiftEl) {
    if (card && card.shift_status === 'working') {
      const mins = card.start_at ? Math.round((Date.now() / 1000 - card.start_at) / 60) : 0;
      const dur = mins >= 60 ? `${Math.floor(mins / 60)} ч ${mins % 60} мин` : `${mins} мин`;
      shiftEl.className = 'worker-card-shift worker-card-shift-active';
      shiftEl.textContent = `● На смене · ${card.object_name || ''}${card.stage_name ? ' · ' + card.stage_name : ''} · ${dur}`;
    } else if (card && card.shift_status === 'idle') {
      shiftEl.className = 'worker-card-shift';
      shiftEl.textContent = 'Сейчас не на смене';
    } else {
      shiftEl.textContent = '';
    }
  }

  body.innerHTML = _workerCardBodyHtml(stats, uid);

  // CSV табель (Owner-only).
  document.getElementById('wc-export-csv')?.addEventListener('click', async (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/api/checkin/stundenzettel?user_id=${encodeURIComponent(uid)}`, { headers: { ..._authHeaders() } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || 'Stundenzettel.csv';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      hapticImpact('light');
    } catch (e) {
      showToast('Ошибка экспорта: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
}

function _workerCardBodyHtml(stats, uid) {
  // Часы (period viz)
  const pd = stats.period_data;
  let hoursTitle, hoursHtml, hoursTotal;
  if (stats.period === 'week' || !pd) {
    hoursTitle = 'Часы за 7 дней';
    hoursHtml = `<div class="profile-week-rings">${(stats.week || []).map(d => {
      const pct = Math.min(100, d.hours / PROFILE_DAY_NORM_HOURS * 100);
      const lbl = d.hours > 0 ? (Math.round(d.hours * 10) / 10) + '' : '·';
      return `<div class="profile-day-ring">${renderRingProgress(pct, 40, 4, lbl)}<div class="profile-day-letter">${WEEKDAY_LETTERS[d.weekday]}</div></div>`;
    }).join('')}</div>`;
    hoursTotal = (stats.week_total_hours || 0) + ' ч';
  } else if (pd.kind === 'heatmap') {
    hoursTitle = 'Часы за месяц';
    const maxH = Math.max(1, ...pd.days.map(d => d.hours));
    hoursHtml = `<div class="profile-month-heatmap">${pd.days.map(d => {
      const intensity = d.hours > 0 ? Math.min(1, d.hours / maxH) : 0;
      return `<div class="profile-heatmap-cell" style="background:color-mix(in srgb, var(--accent) ${Math.round(intensity * 100)}%, var(--bg-card-raised))" title="${d.date}: ${d.hours}ч"></div>`;
    }).join('')}</div>`;
    hoursTotal = pd.total_hours + ' ч';
  } else {
    hoursTitle = stats.period === '3months' ? 'Часы за 3 месяца' : 'Часы за год';
    const maxH = Math.max(1, ...pd.buckets.map(b => b.hours));
    hoursHtml = `<div class="profile-period-bar-chart">${pd.buckets.map(b =>
      `<div class="profile-bar-col" title="${b.label}: ${b.hours}ч"><div class="profile-bar-fill" style="height:${Math.round(b.hours / maxH * 100)}%"></div></div>`
    ).join('')}</div>`;
    hoursTotal = pd.total_hours + ' ч';
  }

  const urlaubHtml = stats.urlaub ? `
    <div class="card">
      <div class="home-section-header" style="padding:0 0 0.5rem;">
        <span class="home-section-title">Отпуск</span>
        <span class="profile-week-total">${stats.urlaub.remaining} дн. осталось</span>
      </div>
      <div class="profile-urlaub-bar"><div class="profile-urlaub-bar-fill" style="width:${Math.min(100, (stats.urlaub.used / stats.urlaub.total) * 100)}%"></div></div>
      <div class="profile-urlaub-caption">Использовано ${stats.urlaub.used} из ${stats.urlaub.total} дней в этом году${stats.krankheit_days_this_year ? ` · больничных ${stats.krankheit_days_this_year}` : ''}</div>
    </div>` : '';

  const objects = stats.objects || [];
  const objectsHtml = `
    <div class="card">
      <div class="home-section-header" style="padding:0 0 0.5rem;"><span class="home-section-title">Объекты</span></div>
      ${objects.length ? objects.map(o => `
        <div class="profile-object-row">
          <div class="profile-object-name">${esc(o.object_name)}</div>
          <div class="profile-object-meta">
            ${o.sessions ? `${o.sessions} смен · ${o.total_hours} ч` : ''}
            ${o.assigned_stages && o.assigned_stages.length ? ` · назначен: ${esc(o.assigned_stages.join(', '))}` : ''}
            ${o.last_date ? ` · ${o.last_date}` : ''}
          </div>
        </div>`).join('') : '<div style="font-size:0.85rem;color:var(--text-light)">Пока нет ни смен, ни назначений.</div>'}
    </div>`;

  const skillsV2 = stats.skills_v2 || [];
  const skillsHtml = `
    <div class="card">
      <div class="home-section-header" style="padding:0 0 0.5rem;"><span class="home-section-title">Навыки</span></div>
      <div class="profile-skills-chips">${skillsV2.length ? skillsV2.map(s => {
        const name = _skillLevelDisplayName(s.skill_id);
        const levelLabel = { helper: 'Помощник', independent: 'Самостоятельно', master: 'Мастер' }[s.level] || s.level;
        return `<div class="profile-skill-chip-v2"><div class="profile-skill-chip-name">${esc(name)}</div><div class="profile-skill-chip-level">${esc(levelLabel)}</div>${s.verified ? '<div class="profile-skill-verified">✓ Подтверждено компанией</div>' : ''}</div>`;
      }).join('') : '<div style="font-size:0.85rem;color:var(--text-light)">Навыки не указаны.</div>'}</div>
    </div>`;

  const sizes = stats.sizes || {};
  const hasSizes = sizes.pants || sizes.shirt || sizes.shoe;
  const sizesHtml = hasSizes ? `
    <div class="card">
      <div class="home-section-header" style="padding:0 0 0.5rem;"><span class="home-section-title">Размеры одежды</span></div>
      <div class="profile-object-meta" style="font-size:0.85rem">
        ${sizes.pants ? `Штаны: ${esc(sizes.pants)}` : ''}${sizes.shirt ? ` · Футболка: ${esc(sizes.shirt)}` : ''}${sizes.shoe ? ` · Обувь: ${esc(sizes.shoe)}` : ''}
      </div>
    </div>` : '';

  return `
    <div class="card profile-week-card">
      <div class="home-section-header" style="padding:0 0 0.5rem;">
        <span class="home-section-title">${hoursTitle}</span>
        <span class="profile-week-total">${hoursTotal}</span>
      </div>
      ${hoursHtml}
    </div>
    ${urlaubHtml}
    ${objectsHtml}
    ${skillsHtml}
    ${sizesHtml}
    <button class="submit-btn profile-inline-btn" id="wc-export-csv" type="button">Скачать табель (CSV)</button>
  `;
}
