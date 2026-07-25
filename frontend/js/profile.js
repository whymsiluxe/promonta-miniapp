// Профиль работника (Фаза 8): аватар, 7 колец часов, work-speed, история объектов,
// навыки, размеры одежды. Все метрики считает backend (/api/profile/stats) на чтении.

const WEEKDAY_LETTERS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const PROFILE_DAY_NORM_HOURS = 10; // 100% кольца = 10ч в день

let _profileStatsUserId = ''; // пусто = я сам; owner может смотреть работников
let _profilePeriod = 'week'; // 21.07: period-pills (Kalo batch 1) — week/month/3months/year, 3 визуальных режима
const PROFILE_PERIOD_LABEL = { week: 'Неделя', month: 'Месяц', '3months': '3 месяца', year: 'Год' };

function initProfileView() {
  const slot = document.getElementById('profile-content');
  if (!slot) return;

  const tabsHtml = currentRole === 'owner'
    ? `<div class="profile-tabs" id="profile-tabs">
        <div class="profile-tab active" data-tab="me">Мой профиль</div>
        <div class="profile-tab" data-tab="team">Команда</div>
        <div class="profile-tab" data-tab="settings">Настройки</div>
      </div>`
    : `<div class="profile-tabs" id="profile-tabs">
        <div class="profile-tab active" data-tab="me">Мой профиль</div>
        <div class="profile-tab" data-tab="settings">Настройки</div>
      </div>`;

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

    ${tabsHtml}

    <div class="profile-tab-panel" data-panel="me">
      <div id="profile-worker-picker-slot"></div>

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
        ${currentRole === 'owner'
          ? `<button class="submit-btn profile-inline-btn" id="profile-export-stundenzettel-btn" type="button">📄 Скачать табель (CSV)</button>`
          : `<a class="profile-csv-link-secondary" id="profile-export-stundenzettel-btn">Скачать табель (CSV)</a>`}
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

    ${currentRole === 'owner' ? `
    <div class="profile-tab-panel" data-panel="team" style="display:none">
      <div class="accordion-section" style="display:block">
        <div id="profile-team-list" style="font-size:0.85rem;color:var(--text-light);padding:0.75rem 0">Загрузка…</div>
      </div>
    </div>` : ''}

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
  if (currentRole === 'owner') {
    _renderWorkerPicker();
    _loadProfileTeam();
  } else {
    _loadProfileAvailabilitySummary();
  }
}

function _bindProfileTabs() {
  const tabs = document.getElementById('profile-tabs');
  if (!tabs) return;
  tabs.addEventListener('click', e => {
    const tab = e.target.closest('.profile-tab');
    if (!tab) return;
    tabs.querySelectorAll('.profile-tab').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.profile-tab-panel').forEach(panel => {
      panel.style.display = panel.dataset.panel === tab.dataset.tab ? '' : 'none';
    });
    hapticImpact('light');
  });
}

// 21.07: worker — summary-строка Urlaub-баланс + deep-link в Календарь, НЕ дублирование UI календаря
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

// 21.07: owner — управление whitelist прямо из Профиля (backend /api/roles уже готов, только UI не было)
async function _loadProfileTeam() {
  const listEl = document.getElementById('profile-team-list');
  if (!listEl) return;
  try {
    const data = await api('/api/roles');
    // 25.07: цветные avatar-инициалы (тот же _chatAvatarHue() детерминированный hue,
    // уже использован в списке чатов) -- список команды раньше был голым текстом,
    // одобренный референс ("TEAM" список) показывал круглые цветные аватарки слева.
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
        try {
          await api('/api/roles', { method: 'POST', body: JSON.stringify({ user_id: btn.dataset.uid, role: 'worker' }) });
          hapticImpact('light');
          _loadProfileTeam();
        } catch (e) { showToast('Ошибка: ' + e.message, 'error'); }
      });
    });
  } catch (e) {
    listEl.textContent = 'Ошибка загрузки команды: ' + e.message;
  }
}

function _bindProfileHandlers() {
  const wrap = document.getElementById('profile-avatar-wrap');
  const input = document.getElementById('profile-avatar-input');
  wrap.addEventListener('click', () => {
    if (_profileStatsUserId) return; // чужой профиль (owner-просмотр) — фото не меняем
    input.click();
  });
  input.addEventListener('change', async () => {
    if (!input.files || !input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    try {
      const res = await fetch(`${API_BASE}/api/profile/me/avatar`, {
        method: 'POST',
        headers: { 'X-Telegram-Init-Data': initData },
        body: fd,
      });
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
    document.querySelectorAll('.profile-period-pill').forEach(p => p.classList.toggle('active', p.dataset.period === _profilePeriod));
    hapticImpact('light');
    _loadProfileStats();
  });
}

async function _downloadStundenzettel() {
  const btn = document.getElementById('profile-export-stundenzettel-btn');
  btn.disabled = true;
  try {
    const targetId = _profileStatsUserId || '';
    const res = await fetch(`${API_BASE}/api/checkin/stundenzettel?user_id=${targetId}`, {
      headers: { 'X-Telegram-Init-Data': initData },
    });
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
    const res = await fetch(`${API_BASE}/api/profile/${uid}/avatar`, {
      headers: { 'X-Telegram-Init-Data': initData },
    });
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

  // 21.07: 3 визуальных режима по периоду (batch 1 Kalo) — не одна вьюха с другим диапазоном дат.
  // week: 7 колец (как было). month: compact heatmap. 3months/year: bar-график по неделям.
  const rings = document.getElementById('profile-week-rings');
  const periodTitle = document.getElementById('profile-period-title');
  const pd = stats.period_data;
  if (stats.team_hours) {
    // owner смотрит СВОЙ профиль — не личные часы (пусты, owner не делает check-in),
    // а агрегат "часы команды за неделю", bar по каждому работнику.
    periodTitle.textContent = 'Часы команды за неделю';
    const team = stats.team_hours;
    if (team.length === 1) {
      // 24.07: единственный работник = единственный столбик = мат. всегда 100% высоты —
      // бар-график тут бессмыслен (не с чем сравнивать), выглядел как "сплошная заливка".
      // Крупная карточка-число вместо голого бара — не просто "убрать баг", юзер попросил
      // сделать красиво: карточка в стиле RaisedTab (тёплая тень, приподнятая поверхность).
      rings.className = 'profile-period-bar-chart';
      const t = team[0];
      rings.innerHTML = `
        <div class="profile-single-worker-card">
          <div class="profile-single-worker-icon">
            <svg viewBox="0 0 24 24" width="22" height="22"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 21c0-4 3.5-7 7-7M12 21c0-4-3.5-7-7-7M12 21V3M9 6l3-3 3 3"/></svg>
          </div>
          <div class="profile-single-worker-hours">${esc(String(t.hours))}<span class="profile-single-worker-unit">ч</span></div>
          <div class="profile-single-worker-name">${esc(t.name)}</div>
        </div>`;
    } else {
      rings.className = 'profile-period-bar-chart profile-team-bar-chart';
      const maxH = Math.max(1, ...team.map(t => t.hours));
      rings.innerHTML = team.length ? team.map(t =>
        `<div class="profile-bar-col" title="${esc(t.name)}: ${t.hours}ч">
          <div class="profile-bar-fill" style="height:${Math.round(t.hours / maxH * 100)}%"></div>
          <div class="profile-bar-label">${esc(t.name).split(' ')[0]}</div>
        </div>`
      ).join('') : '<div style="color:var(--text-light);font-size:0.85rem">Нет работников в команде.</div>';
    }
    document.getElementById('profile-week-total').textContent = Math.round(team.reduce((s, t) => s + t.hours, 0) * 10) / 10 + ' ч';
  } else if (stats.period === 'week' || !pd) {
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

  // Work-speed — только для worker: считается из личных check-in фото-сессий, у owner их
  // нет (он не делает check-in своей смены) — карточка "пока нет данных" была бессмысленной
  // заглушкой на его собственном профиле.
  const speedCard = document.getElementById('profile-speed-card');
  if (currentRole === 'owner') {
    speedCard.style.display = 'none';
  } else if (stats.work_speed || stats.avg_session_hours) {
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
    speedCard.innerHTML = `<div style="font-size:0.85rem;color:var(--text-light)">
      ⚡ Работа по фото: пока нет данных — сделайте первый check-in смены с фото на объекте.</div>`;
  }

  // История объектов
  const objList = document.getElementById('profile-objects-list');
  const objects = stats.objects || [];
  objList.innerHTML = objects.length
    ? objects.map(o => `
        <div class="profile-object-row">
          <div class="profile-object-name">${o.object_name}</div>
          <div class="profile-object-meta">
            ${o.sessions ? `${o.sessions} смен · ${o.total_hours} ч` : ''}
            ${o.assigned_stages && o.assigned_stages.length ? ` · назначен: ${o.assigned_stages.join(', ')}` : ''}
            ${o.last_date ? ` · ${o.last_date}` : ''}
          </div>
        </div>`).join('')
    : '<div style="font-size:0.85rem;color:var(--text-light)">Пока нет ни смен, ни назначений на объекты.</div>';

  // Навыки
  const chips = document.getElementById('profile-skills-chips');
  chips.innerHTML = (stats.skills || []).length
    ? stats.skills.map(s => `<span class="profile-skill-chip">${s}</span>`).join('')
    : '<div style="font-size:0.85rem;color:var(--text-light)">Навыки не указаны.</div>';

  // Имя — предзаполняем только если оно реальное (не совпадает с user_id, значит
  // не fallback после _sanitize_display_name на бэкенде).
  const nameInput = document.getElementById('profile-name-input');
  if (nameInput) nameInput.value = (stats.name && stats.name !== String(stats.user_id)) ? stats.name : '';

  // Размеры
  document.getElementById('profile-size-pants').value = stats.sizes?.pants || '';
  document.getElementById('profile-size-shirt').value = stats.sizes?.shirt || '';
  document.getElementById('profile-size-shoe').value = stats.sizes?.shoe || '';

  // Чужой профиль (owner-просмотр): навыки/размеры менять нельзя
  const isOther = !!_profileStatsUserId;
  document.getElementById('profile-skills-edit-btn').style.display = isOther ? 'none' : 'block';
  document.getElementById('profile-sizes-save-btn').style.display = isOther ? 'none' : 'block';
}

async function _renderWorkerPicker() {
  const slot = document.getElementById('profile-worker-picker-slot');
  if (!slot) return;
  try {
    const data = await api('/api/workers');
    const workers = (data.workers || []);
    if (workers.length < 2) return;
    slot.innerHTML = `
      <select id="profile-worker-select" class="mangel-select" style="margin:0 0 0.75rem">
        <option value="">Мой профиль</option>
        ${workers.map(w => `<option value="${esc(w.user_id)}">${esc(w.name)} (${esc(w.role)})</option>`).join('')}
      </select>
      <button class="submit-btn profile-inline-btn" id="profile-assign-object-btn" type="button" style="display:none;margin-bottom:0.75rem">📌 Назначить на объект</button>`;
    const select = document.getElementById('profile-worker-select');
    const assignBtn = document.getElementById('profile-assign-object-btn');
    select.value = _profileStatsUserId || '';
    assignBtn.style.display = _profileStatsUserId ? 'block' : 'none';
    select.addEventListener('change', e => {
      _profileStatsUserId = e.target.value;
      assignBtn.style.display = _profileStatsUserId ? 'block' : 'none';
      _loadProfileStats();
    });
    assignBtn.addEventListener('click', () => {
      const worker = workers.find(w => String(w.user_id) === String(_profileStatsUserId));
      if (worker && typeof openAssignFromProfile === 'function') openAssignFromProfile(worker.user_id, worker.name);
    });
  } catch (e) {}
}

let _skillsEditOpen = false;

async function _toggleSkillsEdit() {
  const editEl = document.getElementById('profile-skills-edit');
  const btn = document.getElementById('profile-skills-edit-btn');
  const chips = document.getElementById('profile-skills-chips');

  if (_skillsEditOpen) {
    // Сохранить
    const selected = Array.from(editEl.querySelectorAll('input[type=checkbox]:checked')).map(c => c.value);
    try {
      await api('/api/profile/me', { method: 'PATCH', body: JSON.stringify({ skills: selected }) });
      hapticImpact('light');
    } catch (e) {
      showToast('Ошибка сохранения: ' + e.message, 'error');
      return;
    }
    _skillsEditOpen = false;
    editEl.style.display = 'none';
    chips.style.display = 'flex';
    btn.textContent = 'Изменить навыки';
    _loadProfileStats();
    return;
  }

  // Открыть редактор
  try {
    const me = await api('/api/profile/me');
    const mySkills = new Set(me.skills || []);
    editEl.innerHTML = (me.skill_options || []).map(opt => `
      <label class="profile-skill-check">
        <input type="checkbox" value="${opt}" ${mySkills.has(opt) ? 'checked' : ''}> ${opt}
      </label>`).join('');
    editEl.style.display = 'block';
    chips.style.display = 'none';
    btn.textContent = '💾 Сохранить навыки';
    _skillsEditOpen = true;
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

async function _saveName() {
  const input = document.getElementById('profile-name-input');
  const statusEl = document.getElementById('profile-name-status');
  const name = input.value.trim();
  if (!name) {
    statusEl.textContent = 'Введи имя';
    statusEl.style.color = 'var(--red)';
    return;
  }
  try {
    await api('/api/profile/me', {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
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
