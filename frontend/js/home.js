// Home Dashboard: KPI bar, quick-actions (2-уровневые), Dynamic Island погода, ring-прогресс объектов.

let _homeLoaded = false;

async function initHomeView() {
  const slot = document.getElementById('home-dashboard-slot');
  if (!slot) return;

  if (currentRole === 'worker') {
    // 24.07: worker-дашборд лёгкий (иконки + 2 API-вызова) — перерисовываем на каждый
    // заход, иначе статус смены/счётчики ("Смена не начата" после реального старта
    // смены в объекте) остаются устаревшими до перезагрузки всего приложения.
    initWorkerHomeView(slot);
    return;
  }

  if (_homeLoaded) return;
  _homeLoaded = true;

  // 30.07 v2 (откат вкладок): Dashboard снова одна цельная лента, не 3 таба.
  // Главный оперативный блок "Команда" объединяет: Требует внимания / Смены и
  // назначения (4 группы) / Часы команды -- вместо разрозненных секций как раньше.
  slot.innerHTML = `
    <div id="home-kpi-bar" class="home-kpi-bar">
      <div class="kpi-tile" id="kpi-objects" onclick="switchView('objects')"><span class="kpi-num">—</span><span class="kpi-label">Объекты</span></div>
      <div class="kpi-tile" id="kpi-working" onclick="switchView('working-objects')">
        <span class="kpi-num" id="kpi-working-count">—</span><span class="kpi-label">Команда</span>
      </div>
    </div>

    <div id="home-kpi-bar-2" class="home-kpi-bar">
      <div class="kpi-tile" id="kpi-tasks" onclick="switchView('tasks')">
        <span class="kpi-num" id="kpi-tasks-count">—</span><span class="kpi-label">Потребности</span>
      </div>
      <div class="kpi-tile kpi-alert" id="kpi-alerts" onclick="openAlertsView()">
        <span class="kpi-num" id="kpi-alerts-count">—</span><span class="kpi-label">Алерты</span>
        <span class="quick-primary-badge" id="alerts-badge" style="display:none">0</span>
      </div>
    </div>

    <div id="home-radio-player-mount"></div>

    <div id="home-messages-wide" class="quick-primary-item home-messages-wide" onclick="switchView('chat')">
      <div class="quick-primary-icon-wrap qp-icon qp-icon-chat"><div class="qp-icon-sphere"></div><div class="qp-icon-bubble"></div></div>
      <div class="quick-primary-text">
        <div class="quick-primary-title">Сообщения</div>
        <div class="quick-primary-sub" id="home-chat-quick-sub">Командный чат</div>
      </div>
      <span class="quick-primary-badge" id="home-chat-badge" style="display:none">0</span>
    </div>

    <div id="home-stack-wide" class="home-stack-wide">
      <div class="quick-primary-item" onclick="switchView('abwesenheit')">
        <div class="quick-primary-icon-wrap qp-icon qp-icon-calendar"><div class="qp-icon-sphere"></div><div class="qp-icon-grid"><span></span><span></span><span></span><span></span></div></div>
        <div class="quick-primary-text">
          <div class="quick-primary-title">Календарь</div>
          <div class="quick-primary-sub" id="abwesenheit-quick-sub">Календарь недоступностей</div>
        </div>
      </div>
      <div class="quick-primary-item" onclick="switchView('tools')">
        <div class="quick-primary-icon-wrap qp-icon qp-icon-tools-wide"><div class="qp-icon-sphere"></div><div class="qp-icon-wrench"></div></div>
        <div class="quick-primary-text"><div class="quick-primary-title">Инструменты</div></div>
      </div>
      <div class="quick-primary-item" onclick="switchView('documents')">
        <div class="quick-primary-icon-wrap qp-icon qp-icon-docs-wide"><div class="qp-icon-sphere"></div><div class="qp-icon-lines-wide"><span></span><span></span><span></span></div></div>
        <div class="quick-primary-text"><div class="quick-primary-title">Документы</div></div>
      </div>
      <div class="quick-primary-item" onclick="switchView('ai')">
        <div class="quick-primary-icon-wrap qp-icon qp-icon-ai-wide"><div class="qp-icon-sphere"></div><div class="qp-icon-spark-wide"></div></div>
        <div class="quick-primary-text"><div class="quick-primary-title">ИИ-ассистент</div></div>
      </div>
    </div>

    <div id="home-rings-section" class="home-rings-section">
      <div class="home-section-header">
        <span class="home-section-title">Объекты</span>
        <span class="home-section-action" onclick="switchView('objects')">Все ▸</span>
      </div>
      <div id="home-rings-grid" class="home-rings-grid">
        <div style="color:var(--text-light);font-size:0.85rem;padding:0.5rem 0">Загрузка...</div>
      </div>
    </div>

    <div id="home-weather-card" class="weather-card">
      <div class="weather-card-loading">Загрузка погоды...</div>
    </div>
  `;

  _loadHomeData();
  initFeedTabs(); // суб-табы Инфо/Фото/Новости под dashboard (feed.js)
  if (typeof renderHomeRadioPlayer === 'function') renderHomeRadioPlayer();
}

async function _loadHomeData() {
  _loadHomeWeather();
  _loadHomeObjectsRings();
  _loadHomeAlerts();
  _loadHomeAbwesenheitSummary();
  _loadHomeChatSummary();
}

// 10.11: Abwesenheit-плашка на Home — сводка вместо мелкой строки в Profile→Ещё.
async function _loadHomeAbwesenheitSummary() {
  const sub = document.getElementById('abwesenheit-quick-sub');
  if (!sub) return;
  try {
    const data = currentRole === 'owner'
      ? await api('/api/abwesenheit/all')
      : await api('/api/abwesenheit');
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const upcoming = (data.entries || [])
      .filter(e => new Date(e.date_from) >= now)
      .sort((a, b) => new Date(a.date_from) - new Date(b.date_from));
    if (upcoming.length === 0) {
      sub.textContent = 'Нет ближайших событий';
      return;
    }
    const next = upcoming[0];
    const d = new Date(next.date_from);
    const dateLabel = d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    const who = currentRole === 'owner' && next.name ? `${next.name}: ` : '';
    sub.textContent = `${who}${next.reason || 'Отсутствие'} · ${dateLabel}`;
  } catch (e) {
    sub.textContent = 'Календарь недоступностей';
  }
}

async function _loadHomeChatSummary() {
  const sub = document.getElementById('home-chat-quick-sub');
  if (!sub) return;
  try {
    const data = await api('/api/chat/my_threads');
    const threads = data.threads || [];
    if (threads.length === 0) {
      sub.textContent = 'Командный чат';
      return;
    }
    const last = threads[0]; // already sorted by last_ts desc (backend)
    const title = last.title ? `${last.title}: ` : '';
    const preview = (last.last_preview || '').slice(0, 40);
    sub.textContent = preview ? `${title}${preview}` : 'Командный чат';
  } catch (e) {
    sub.textContent = 'Командный чат';
  }
}

const WEATHER_DAY_NAMES = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

function _weatherKind(dayWave, risks) {
  const riskText = (risks || []).join(' ').toLowerCase();
  if (riskText.includes('гроза') || riskText.includes('молни')) return 'storm';
  if (riskText.includes('снег') || riskText.includes('заморозки')) return 'snow';
  if ((dayWave && dayWave.precip_prob >= 60) || riskText.includes('дождь')) return 'rain';
  if ((dayWave && dayWave.wind >= 30) || riskText.includes('ветер')) return 'wind';
  if (dayWave && dayWave.precip_prob >= 30) return 'cloudy';
  return 'sunny';
}

const WEATHER_KIND_LABEL = {
  storm: 'Гроза', rain: 'Дождь', snow: 'Снег', wind: 'Ветрено', cloudy: 'Облачно', sunny: 'Ясно',
};

function _weatherIllustration(kind) {
  if (kind === 'storm') {
    return `<div class="wx-illust wx-illust-storm">
      <div class="wx-cloud wx-cloud-storm"><div class="wx-cloud-lobe3"></div><div class="wx-cloud-storm-glow"></div></div>
      <div class="wx-bolt"></div>
    </div>`;
  }
  if (kind === 'rain') {
    return `<div class="wx-illust wx-illust-rain">
      <div class="wx-cloud wx-cloud-rain"><div class="wx-cloud-lobe3"></div></div>
      <div class="wx-drops"><span></span><span></span><span></span><span></span><span></span></div>
    </div>`;
  }
  if (kind === 'snow') {
    return `<div class="wx-illust wx-illust-snow">
      <div class="wx-cloud wx-cloud-snow"><div class="wx-cloud-lobe3"></div></div>
      <div class="wx-flakes"><span></span><span></span><span></span><span></span></div>
    </div>`;
  }
  if (kind === 'wind') {
    return `<div class="wx-illust wx-illust-wind">
      <div class="wx-cloud wx-cloud-wind"><div class="wx-cloud-lobe3"></div></div>
      <div class="wx-wind-lines"><span></span><span></span><span></span></div>
    </div>`;
  }
  if (kind === 'cloudy') {
    return `<div class="wx-illust wx-illust-cloudy">
      <div class="wx-sun wx-sun-behind"></div>
      <div class="wx-cloud wx-cloud-main"><div class="wx-cloud-lobe3"></div></div>
    </div>`;
  }
  return `<div class="wx-illust wx-illust-sunny">
    <div class="wx-sun"><div class="wx-sun-core"></div><div class="wx-sun-rays"></div></div>
  </div>`;
}

function _extractCity(address) {
  if (!address) return '';
  const lastPart = address.split(',').pop().trim();
  return lastPart.split(/\s+/).filter(w => !/^\d+$/.test(w)).join(' ') || lastPart;
}

let _weatherFeed = [];
let _weatherActiveIdx = 0;

async function _loadHomeWeather() {
  const card = document.getElementById('home-weather-card');
  if (!card) return;
  try {
    const data = await api('/api/feed/weather');
    const rawFeed = data.feed || [];
    const latestByObject = new Map();
    for (const entry of rawFeed) {
      const existing = latestByObject.get(entry.object);
      if (!existing || entry.created > existing.created) latestByObject.set(entry.object, entry);
    }
    _weatherFeed = Array.from(latestByObject.values());
    if (!_weatherFeed.length) {
      card.innerHTML = '<div class="weather-card-loading">Нет данных о погоде</div>';
      return;
    }
    if (_weatherActiveIdx >= _weatherFeed.length) _weatherActiveIdx = 0;
    _renderWeatherCard();
  } catch (e) {
    card.innerHTML = '<div class="weather-card-loading">Ошибка загрузки погоды</div>';
  }
}

function _renderWeatherCard() {
  const card = document.getElementById('home-weather-card');
  if (!card || !_weatherFeed.length) return;
  const active = _weatherFeed[_weatherActiveIdx];
  const wave = active.wave || [];
  const forecast = active.forecast || [];
  const today = wave[0] || {};
  const todayRisks = (forecast[0] && forecast[0].risks) || [];
  const kind = _weatherKind(today, todayRisks);
  const dayName = WEATHER_DAY_NAMES[new Date().getDay()];
  const tmax = today.tmax !== undefined ? Math.round(today.tmax) : '—';
  const tmin = today.tmin !== undefined ? Math.round(today.tmin) : '—';

  const objectTabs = _weatherFeed.map((f, i) => `
    <div class="wx-object-tab${i === _weatherActiveIdx ? ' active' : ''}" data-idx="${i}">${esc(f.object || 'Объект')}</div>
  `).join('');

  const stripDays = wave.slice(0, 4).map((w, i) => {
    const risks = (forecast[i] && forecast[i].risks) || [];
    const dayKind = _weatherKind(w, risks);
    const d = new Date(w.date);
    const shortDay = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'][d.getDay()];
    return `<div class="wx-strip-day" data-day-idx="${i}">
      <div class="wx-strip-label">${i === 0 ? 'Сегодня' : shortDay}</div>
      <div class="wx-strip-icon">${_weatherMiniIcon(dayKind)}</div>
      <div class="wx-strip-temp">${Math.round(w.tmax)}°</div>
    </div>`;
  }).join('');

  const cityName = _extractCity(active.address);

  card.innerHTML = `
    <div class="wx-object-tabs">${objectTabs}</div>
    <div class="weather-card-top">
      <div class="weather-card-city">${esc(cityName)}</div>
    </div>
    ${_weatherIllustration(kind)}
    <div class="weather-card-temp">${tmax}°</div>
    <div class="weather-card-minmax">↓${tmin}° &nbsp; ↑${tmax}°</div>
    <div class="weather-card-status wx-status-${kind}">${dayName}: ${WEATHER_KIND_LABEL[kind]}</div>
    <div class="wx-strip">${stripDays}</div>
  `;

  card.querySelectorAll('.wx-object-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      _weatherActiveIdx = Number(tab.dataset.idx);
      _renderWeatherCard();
    });
  });
  card.querySelectorAll('.wx-strip-day').forEach(dayEl => {
    dayEl.addEventListener('click', () => _openHourlyWeather(Number(dayEl.dataset.dayIdx)));
  });
}

function _weatherMiniIcon(kind) {
  const map = { storm: '⛈️', rain: '🌧️', snow: '🌨️', wind: '💨', cloudy: '⛅', sunny: '☀️' };
  return map[kind] || '☀️';
}

function _openHourlyWeather(dayIdx) {
  const active = _weatherFeed[_weatherActiveIdx];
  if (!active) return;
  const wave = active.wave || [];
  const day = wave[dayIdx];
  if (!day || !day.hourly || !day.hourly.length) return;

  const d = new Date(day.date);
  const dayLabel = dayIdx === 0 ? 'Сегодня' : WEATHER_DAY_NAMES[d.getDay()];

  const rows = day.hourly.map(h => {
    const kind = _weatherCodeToKind(h.weather_code);
    return `<div class="wx-hourly-row">
      <div class="wx-hourly-time">${String(h.hour).padStart(2, '0')}:00</div>
      <div class="wx-hourly-icon">${_weatherMiniIcon(kind)}</div>
      <div class="wx-hourly-temp">${Math.round(h.temp)}°</div>
      <div class="wx-hourly-precip">${h.precip_prob}% 💧</div>
    </div>`;
  }).join('');

  const sheet = document.createElement('div');
  sheet.id = 'wx-hourly-sheet';
  sheet.innerHTML = `
    <div class="wx-hourly-inner">
      <div class="wx-hourly-header">
        <span class="wx-hourly-title">${dayLabel}, ${day.date}</span>
        <button class="wx-hourly-close" onclick="document.getElementById('wx-hourly-sheet').remove()">✕</button>
      </div>
      <div class="wx-hourly-list">${rows}</div>
    </div>
  `;
  document.body.appendChild(sheet);
  sheet.addEventListener('click', e => { if (e.target === sheet) sheet.remove(); });
}

function _weatherCodeToKind(code) {
  // WMO weather_code (Open-Meteo) -> наши 6 категорий иллюстраций
  if ([95, 96, 99].includes(code)) return 'storm';
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
  if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'rain';
  if ([45, 48].includes(code)) return 'cloudy';
  if ([1, 2, 3].includes(code)) return 'cloudy';
  return 'sunny';
}

function _ringSvg(pct, color) {
  return `
    <svg class="ring-progress" viewBox="0 0 44 44" width="52" height="52">
      <circle cx="22" cy="22" r="18" fill="none" stroke="var(--border-color)" stroke-width="4"/>
      <circle cx="22" cy="22" r="18" fill="none" stroke="${color}" stroke-width="4"
        stroke-dasharray="${(pct / 100 * 113.1).toFixed(1)} 113.1"
        stroke-linecap="round" transform="rotate(-90 22 22)" style="transition:stroke-dasharray 0.6s ease"/>
    </svg>`;
}

async function _fetchObjectProgress(oid) {
  try {
    const data = await api(`/api/objects/${oid}/stages`);
    const stages = data.stages || [];
    if (!stages.length) return null;
    const done = stages.filter(s => s['Статус'] === 'готово').length;
    return Math.round((done / stages.length) * 100);
  } catch (e) {
    return null;
  }
}

function _ringCard(progressPct, progressColor, name, shortName, objectId, budgetPct, budgetColor) {
  const budgetChip = currentRole === 'owner'
    ? `<div class="home-ring-budget-chip" style="color:${budgetColor}">${budgetPct}% бюджет</div>` : '';
  return `
    <div class="home-ring-item" data-object-id="${esc(objectId)}" data-object-name="${esc(name)}" title="${esc(name)}">
      <div class="home-ring-sub">${_ringSvg(progressPct, progressColor)}<div class="home-ring-pct" style="color:${progressColor}">${progressPct}%</div></div>
      <div class="home-ring-label">${esc(shortName)}</div>
      ${budgetChip}
    </div>`;
}

function _attachHomeRingHandlers(container) {
  container.querySelectorAll('.home-ring-item').forEach(el => {
    el.addEventListener('click', () => {
      switchView('objects');
      const oid = el.dataset.objectId;
      if (oid) setTimeout(() => openStagesView(oid, el.dataset.objectName), 0);
    });
  });
}

async function _loadHomeObjectsRings() {
  const grid = document.getElementById('home-rings-grid');
  const kpiEl = document.getElementById('kpi-objects');
  try {
    const data = await api('/api/objects');
    const active = (data.objects || []).filter(o => o['Статус'] === 'В работе');
    const kpiNum = kpiEl.querySelector('.kpi-num');
    if (kpiNum) kpiNum.textContent = active.length;

    // 30.07 v4 (спек): KPI "Команда" -- реально работающих ПРЯМО СЕЙЧАС (working_now.length
    // из существующего /api/dashboard/shifts-today, тот же источник что и экран "Команда"),
    // не "назначен хоть на один объект" как раньше. Только счётчик, без рендера списка --
    // полный список живёт на отдельном экране working-objects.
    const workingCountEl = document.getElementById('kpi-working-count');
    if (workingCountEl && currentRole === 'owner') {
      try {
        const shifts = await api('/api/dashboard/shifts-today');
        workingCountEl.textContent = (shifts.working_now || []).length;
      } catch (e) {
        const uniqueWorkers = new Set();
        (data.objects || []).forEach(o => (o.assigned_users || []).forEach(u => uniqueWorkers.add(u.user_id)));
        workingCountEl.textContent = uniqueWorkers.size;
      }
    }

    if (!active.length) {
      grid.innerHTML = '<div style="color:var(--text-light);font-size:0.85rem;padding:0.5rem 0">Нет активных объектов</div>';
      return;
    }
    const shown = active.slice(0, 6);
    const progressList = await Promise.all(shown.map(obj => _fetchObjectProgress(obj['ID объекта'])));

    grid.innerHTML = shown.map((obj, i) => {
      const name = obj['Объект'] || '';
      const shortName = name.length > 18 ? name.slice(0, 17) + '…' : name;
      const budgetPct = Math.round(parseFloat(obj['потрачено в % от бюджета']) || 0);
      const budgetColor = budgetPct >= 90 ? 'var(--red)' : budgetPct >= 60 ? 'var(--warning)' : 'var(--accent)';
      const progressPct = progressList[i];
      if (progressPct === null) return _ringCard(0, 'var(--text-light)', name, shortName, obj['ID объекта'], budgetPct, budgetColor);
      return _ringCard(progressPct, 'var(--accent-gold)', name, shortName, obj['ID объекта'], budgetPct, budgetColor);
    }).join('');

    _attachHomeRingHandlers(grid);
  } catch (e) {
    grid.innerHTML = '<div style="color:var(--text-light);font-size:0.85rem">Ошибка загрузки объектов</div>';
  }
}

async function _loadHomeAlerts() {
  const badge = document.getElementById('alerts-badge');
  const kpiAlerts = document.getElementById('kpi-alerts-count');
  try {
    const data = await api('/api/alerts');
    const count = data.count || 0;
    if (kpiAlerts) kpiAlerts.textContent = count;
    if (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? 'flex' : 'none';
    }
  } catch (e) {}

  const kpiTasks = document.getElementById('kpi-tasks-count');
  if (kpiTasks) {
    try {
      const data = await api('/api/tasks');
      const open = (data.tasks || []).filter(t => t.status !== 'закрыто').length;
      kpiTasks.textContent = open;
    } catch (e) {}
  }
}

// Alerts view/modal — открывается из Home
let _alertsViewOpen = false;

async function openAlertsView() {
  if (_alertsViewOpen) return;
  _alertsViewOpen = true;

  const modal = document.createElement('div');
  modal.id = 'alerts-modal';
  modal.innerHTML = `
    <div class="alerts-modal-inner">
      <div class="alerts-modal-header">
        <span class="alerts-modal-title">🔔 Алерты</span>
        <button class="alerts-modal-close" onclick="_closeAlertsView()">✕</button>
      </div>
      <div class="alerts-filter-tabs">
        <div class="alerts-tab active" data-filter="all" onclick="_filterAlerts(this,'all')">Все</div>
        <div class="alerts-tab" data-filter="red" onclick="_filterAlerts(this,'red')">Важное</div>
        <div class="alerts-tab" data-filter="yellow" onclick="_filterAlerts(this,'yellow')">Задачи</div>
      </div>
      <div id="alerts-list" class="alerts-list">
        <div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка...</div>
      </div>
      <button class="alerts-close-btn" onclick="_closeAlertsView()">Закрыть</button>
    </div>
  `;
  document.body.appendChild(modal);

  try {
    const data = await api('/api/alerts');
    window._allAlerts = data.alerts || [];
    _renderAlerts(window._allAlerts);
  } catch (e) {
    document.getElementById('alerts-list').innerHTML =
      '<div style="padding:1rem;color:var(--red);text-align:center">Ошибка загрузки</div>';
  }
}

function _closeAlertsView() {
  const modal = document.getElementById('alerts-modal');
  if (modal) modal.remove();
  _alertsViewOpen = false;
  // 25.07: закрытие модалки = "прочитал" -- derived-алерты (бюджет/инструмент/назначение)
  // не имеют ack как persisted critical alerts, отмечаем dismiss явно, счётчик на Home
  // перезагружаем сразу, не жду следующий обычный poll.
  const ids = (window._allAlerts || []).filter(a => !a.critical_alert_id).map(a => a.id);
  if (ids.length) {
    api('/api/alerts/dismiss', { method: 'POST', body: JSON.stringify({ alert_ids: ids }) })
      .then(() => _loadHomeAlerts())
      .catch(() => {});
  }
}

function _filterAlerts(tabEl, filter) {
  document.querySelectorAll('.alerts-tab').forEach(t => t.classList.remove('active'));
  tabEl.classList.add('active');
  const all = window._allAlerts || [];
  const filtered = filter === 'all' ? all : all.filter(a => a.type === filter);
  _renderAlerts(filtered);
}

function _renderAlerts(alerts) {
  const list = document.getElementById('alerts-list');
  if (!list) return;
  if (!alerts.length) {
    list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Нет алертов</div>';
    return;
  }
  list.innerHTML = alerts.map(a => {
    const color = a.type === 'red' ? 'var(--red)' : a.type === 'yellow' ? 'var(--warning)' : 'var(--accent)';
    const timeStr = a.at ? new Date(a.at).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '';
    const clickable = a.id && a.id.startsWith('abw-pending-');
    return `
      <div class="alert-item${clickable ? ' alert-item-clickable' : ''}" ${clickable ? `data-abw-id="${esc(a.id.replace('abw-pending-', ''))}"` : ''}>
        <div class="alert-item-border" style="background:${color}"></div>
        <div class="alert-item-icon" style="background:${color}22;color:${color}">
          ${a.type === 'red' ? '🔴' : a.type === 'yellow' ? '🟡' : '🟢'}
        </div>
        <div class="alert-item-body">
          <div class="alert-item-title">${esc(a.title)}</div>
          <div class="alert-item-sub">${esc(a.subtitle || '')}</div>
        </div>
        ${timeStr ? `<div class="alert-item-time">${timeStr}</div>` : ''}
        ${clickable ? `<span class="alert-item-arrow">›</span>` : ''}
      </div>`;
  }).join('');

  list.querySelectorAll('.alert-item-clickable').forEach(el => {
    el.addEventListener('click', () => {
      const abwId = el.dataset.abwId;
      _closeAlertsView();
      _pendingAbwesenheitFocusId = abwId;
      const alreadyLoaded = typeof loadedViews !== 'undefined' && loadedViews.has('abwesenheit');
      switchView('abwesenheit');
      // switchView() инициализирует вкладку только при первом заходе (loadedViews-кэш) —
      // при повторном заходе initAbwesenheitView() не вызовется, дёргаем loadAbwesenheit()
      // сами, чтобы подсветка диапазона/скролл к записи сработали и во второй раз.
      if (alreadyLoaded && typeof loadAbwesenheit === 'function') loadAbwesenheit();
    });
  });
}


// ═══════════ Worker Dashboard (Фаза 10.14) — 4-карточная плитка вместо owner-версии ═══════════

async function initWorkerHomeView(slot) {
  slot.innerHTML = `
    <div id="worker-shift-cta" class="worker-shift-cta" style="display:none"></div>
    <div id="home-radio-player-mount"></div>
    <div class="worker-tile-grid">
      <div class="worker-tile" id="worker-tile-messages" onclick="switchView('chat')">
        <span class="worker-tile-badge" id="worker-tile-messages-badge" style="display:none">0</span>
        <div class="wt-icon wt-icon-messages"><div class="wt-icon-sphere"></div><div class="wt-icon-tail"></div></div>
        <div class="worker-tile-label">Сообщения</div>
      </div>
      <div class="worker-tile" id="worker-tile-tasks" onclick="switchView('my-tasks')">
        <span class="worker-tile-badge" id="worker-tile-tasks-badge" style="display:none">0</span>
        <div class="wt-icon wt-icon-tasks"><div class="wt-icon-sphere"></div><div class="wt-icon-check"></div></div>
        <div class="worker-tile-label">Задачи</div>
      </div>
      <div class="worker-tile" id="worker-tile-important" onclick="_openWorkerAlerts('yellow')">
        <span class="worker-tile-badge" id="worker-tile-important-badge" style="display:none">0</span>
        <div class="wt-icon wt-icon-important"><div class="wt-icon-triangle"></div><div class="wt-icon-bang"></div></div>
        <div class="worker-tile-label">Алерты важно</div>
      </div>
      <div class="worker-tile" id="worker-tile-critical" onclick="_openWorkerAlerts('red')">
        <span class="worker-tile-badge" id="worker-tile-critical-badge" style="display:none">0</span>
        <div class="wt-icon wt-icon-critical"><div class="wt-icon-sphere"></div><div class="wt-icon-bang"></div></div>
        <div class="worker-tile-label">Алерты критично</div>
      </div>
    </div>

    <div class="worker-tile-wide" id="worker-tile-needs" onclick="switchView('tasks')">
      <div class="wt-icon wt-icon-tasks"><div class="wt-icon-sphere"></div><div class="wt-icon-check"></div></div>
      <div class="worker-tile-label">Потребности</div>
      <span class="worker-tile-wide-arrow">›</span>
    </div>
    <div class="worker-tile-wide" id="worker-tile-objects" onclick="switchView('objects')">
      <div class="wt-icon wt-icon-objects"><div class="wt-icon-sphere"></div><div class="wt-icon-blocks"><span></span><span></span><span></span></div></div>
      <div class="worker-tile-label">Объекты</div>
      <span class="worker-tile-wide-arrow">›</span>
    </div>
    <div class="worker-tile-wide" id="worker-tile-tools" onclick="switchView('tools')">
      <div class="wt-icon qs-icon-tools"><div class="qs-icon-sphere"></div><div class="qs-icon-wrench"></div></div>
      <div class="worker-tile-label">Инструменты</div>
      <span class="worker-tile-wide-arrow">›</span>
    </div>

    <div id="home-weather-card" class="weather-card weather-card-compact">
      <div class="weather-card-loading">Загрузка погоды...</div>
    </div>
  `;

  _loadHomeWeather();
  _loadWorkerTileCounts();
  _loadWorkerShiftCta();
  initFeedTabs();
  if (typeof renderHomeRadioPlayer === 'function') renderHomeRadioPlayer();
}

// 23.07: Start/Pause/Finish смены жил только внутри конкретного объекта (отчёт: "worker должен
// выполнять основную работу с одного экрана"). Не дублируем checkin.js-логику (завязана на
// конкретные #checkin-start-btn/#checkin-finish-btn внутри object-view) — вместо этого показываем
// статус смены на Home и одним тапом ведём в нужный объект, где реальная кнопка уже на месте.
async function _loadWorkerShiftCta() {
  const cta = document.getElementById('worker-shift-cta');
  if (!cta) return;
  try {
    const [checkinData, objData] = await Promise.all([
      api('/api/checkin'),
      api('/api/objects'),
    ]);
    const openSession = (checkinData.sessions || []).find(s => s.finish_at === null || s.finish_at === undefined);
    if (openSession) {
      const obj = (objData.objects || []).find(o => String(o['ID объекта']) === String(openSession.object_id));
      cta.style.display = 'flex';
      cta.className = 'worker-shift-cta worker-shift-cta-active';
      cta.innerHTML = `
        <div class="worker-shift-cta-text">
          <div class="worker-shift-cta-status">🟢 Смена идёт</div>
          <div class="worker-shift-cta-object">${esc(obj ? obj['Объект'] : openSession.object_id)}</div>
        </div>
        <span class="worker-shift-cta-arrow">Завершить ›</span>
      `;
      cta.onclick = () => _openObjectForShift(openSession.object_id, obj ? obj['Объект'] : '');
      return;
    }

    // нет активной смены — предложить начать на первом назначенном сегодня объекте
    const myObjects = (objData.objects || []).filter(o =>
      (o.assigned_users || []).some(u => String(u.user_id) === String(currentUserId)) && o['Статус'] === 'В работе'
    );
    if (myObjects.length) {
      const obj = myObjects[0];
      cta.style.display = 'flex';
      cta.className = 'worker-shift-cta worker-shift-cta-idle';
      cta.innerHTML = `
        <div class="worker-shift-cta-text">
          <div class="worker-shift-cta-status">⚪ Смена не начата</div>
          <div class="worker-shift-cta-object">${esc(obj['Объект'])}</div>
        </div>
        <span class="worker-shift-cta-arrow">Начать ›</span>
      `;
      cta.onclick = () => _openObjectForShift(obj['ID объекта'], obj['Объект']);
    }
  } catch (e) {}
}

function _openObjectForShift(objectId, objectName) {
  // openStagesView (objects.js) — экран с реальными Start/Pause/Finish-кнопками смены,
  // не сама карточка объекта (та лишь разворачивает детали, не открывает check-in).
  // 24.07: убран искусственный setTimeout(150) — он давал заметное мигание (список
  // Объекты на долю секунды показывался пустым/грузящимся, потом резко перекрывался
  // Этапами объекта). openStagesView сам ждёт свои данные через await, а его DOM-цели
  // (#objects-list-view, #stages-view) статичны в разметке — не нужно ждать
  // initObjectsView()/loadObjects() до вызова.
  switchView('objects');
  if (typeof openStagesView === 'function') openStagesView(objectId, objectName || '');
}

function _openWorkerAlerts(presetFilter) {
  openAlertsView().then(() => {
    const tab = document.querySelector(`.alerts-tab[data-filter="${presetFilter}"]`);
    if (tab) tab.click();
  });
}

async function _loadWorkerTileCounts() {
  try {
    const chatData = await api('/api/chat/unread_count');
    _setWorkerBadge('worker-tile-messages-badge', chatData.unread || 0);
  } catch (e) {}

  try {
    const objData = await api('/api/objects');
    const myTasks = (objData.objects || []).filter(o =>
      (o.assigned_users || []).some(u => String(u.user_id) === String(currentUserId))
    ).length;
    _setWorkerBadge('worker-tile-tasks-badge', myTasks);
  } catch (e) {}

  try {
    const alertsData = await api('/api/alerts');
    const alerts = alertsData.alerts || [];
    _setWorkerBadge('worker-tile-important-badge', alerts.filter(a => a.type === 'yellow').length);
    _setWorkerBadge('worker-tile-critical-badge', alerts.filter(a => a.type === 'red').length);
  } catch (e) {}
}

function _setWorkerBadge(elId, count) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = count;
  el.style.display = count > 0 ? 'flex' : 'none';
}


// ═══════════ "Команда" (23.07 "Объекты рабочие" → 30.07 v3 переименовано и расширено
// по спеку): оперативный owner-экран, две внутренние вкладки -- "Сводка" (Требует внимания /
// Активные смены / Часы команды / без объекта / отсутствуют / по объектам) и "План"
// (кто запланирован на дату, по объектам). Данные из существующих /api/workers,
// /api/objects, /api/abwesenheit/all, /api/dashboard/shifts-today, /api/profile/stats,
// /api/dashboard/active-blockers + новый read-only /api/dashboard/team-plan.

let _woMode = 'summary';

function _initWorkingObjectsModeSwitch() {
  const sw = document.getElementById('wo-mode-switch');
  if (!sw || sw.dataset.bound) return;
  sw.dataset.bound = '1';
  sw.querySelectorAll('[data-wo-mode]').forEach(opt => {
    opt.addEventListener('click', () => {
      const mode = opt.dataset.woMode;
      if (mode === _woMode) return;
      _woMode = mode;
      sw.querySelectorAll('[data-wo-mode]').forEach(o => o.classList.toggle('active', o === opt));
      document.getElementById('working-objects-slot').style.display = mode === 'summary' ? '' : 'none';
      document.getElementById('working-objects-plan-slot').style.display = mode === 'plan' ? '' : 'none';
      if (mode === 'plan' && !_woPlanLoaded) {
        _woPlanLoaded = true;
        _initWorkingObjectsPlanTab();
      }
    });
  });
}

async function initWorkingObjectsView() {
  _initWorkingObjectsModeSwitch();
  const slot = document.getElementById('working-objects-slot');
  if (!slot) return;
  slot.innerHTML = '<div style="padding:1rem;color:var(--text-light)">Загрузка…</div>';

  try {
    const [workersData, objectsData, absenceData, shifts, stats, blockersData] = await Promise.all([
      api('/api/workers'),
      api('/api/objects'),
      api('/api/abwesenheit/all').catch(() => ({ entries: [] })),
      api('/api/dashboard/shifts-today').catch(() => null),
      api('/api/profile/stats').catch(() => null),
      api('/api/dashboard/active-blockers').catch(() => ({ blockers: [] })),
    ]);

    const workers = (workersData.workers || []).filter(w => w.role === 'worker');
    const objects = objectsData.objects || [];
    const today = new Date().toISOString().slice(0, 10);
    const absentToday = (absenceData.entries || []).filter(e =>
      e.status !== 'rejected' && e.status !== 'cancelled' && e.date_from <= today && e.date_to >= today
    );
    const absentIds = new Set(absentToday.map(e => String(e.user_id)));

    const assignedIds = new Set();
    objects.forEach(o => (o.assigned_users || []).forEach(u => assignedIds.add(String(u.user_id))));

    const withoutObject = workers.filter(w => !assignedIds.has(String(w.user_id)) && !absentIds.has(String(w.user_id)));
    const activeObjects = objects.filter(o => (o.assigned_users || []).length > 0);

    // 30.07 v4 (спек): карточка адаптируется под тип -- не впихиваем все поля разом.
    // "Не вышел"/"Ждёт" несут объект·этап/период/task_note; "Активная смена" несёт
    // объект·этап/начало+длительность (без периода/task_note -- спек явно просит
    // не перегружать); "Доступен" -- только специальность, без пустых полей.
    const notStartedCard = w => {
      const lines = [];
      const objStage = [w.object_name, w.stage_id].filter(Boolean).join(' · ');
      if (objStage) lines.push(esc(objStage));
      if (w.date_from || w.date_to) lines.push(`${esc(w.date_from || '')} — ${esc(w.date_to || '')}`);
      if (w.task_note) lines.push(esc(w.task_note));
      return `
      <div class="wo-team-card" data-uid="${esc(w.user_id)}">
        <div class="wo-team-card-name">${esc(w.worker_name)}</div>
        ${lines.length ? `<div class="wo-team-card-detail">${lines.join(' · ')}</div>` : ''}
        <div class="wo-team-card-status wo-status-idle">Назначен сегодня · смена не начата</div>
      </div>`;
    };
    const awaitingCard = w => {
      const lines = [];
      const objStage = [w.object_name, w.stage_id].filter(Boolean).join(' · ');
      if (objStage) lines.push(esc(objStage));
      if (w.date_from || w.date_to) lines.push(`${esc(w.date_from || '')} — ${esc(w.date_to || '')}`);
      if (w.task_note) lines.push(esc(w.task_note));
      return `
      <div class="wo-team-card" data-uid="${esc(w.user_id)}">
        <div class="wo-team-card-name">${esc(w.worker_name)}</div>
        ${lines.length ? `<div class="wo-team-card-detail">${lines.join(' · ')}</div>` : ''}
        <div class="wo-team-card-status wo-status-idle">Ожидает подтверждения</div>
      </div>`;
    };
    // 30.07 v5 (аудит): было stage_id||stage_name -- stage_id тут вид работ по
    // умолчанию (может быть пустым/техническим), stage_name -- реальное название
    // этапа объекта из чекина. Показываем нормальное название первым приоритетом.
    const activeCard = w => {
      const objStage = [w.object_name, w.stage_name || w.stage_id].filter(Boolean).join(' · ');
      const startLabel = w.start_at ? new Date(w.start_at * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
      const mins = w.start_at ? Math.round((Date.now() / 1000 - w.start_at) / 60) : 0;
      const durationLabel = mins >= 60 ? `${Math.floor(mins / 60)} ч ${mins % 60} мин` : `${mins} мин`;
      return `
      <div class="wo-team-card" data-uid="${esc(w.user_id)}">
        <div class="wo-team-card-name">${esc(w.worker_name)}${w.specialty ? ` · ${esc(w.specialty)}` : ''}</div>
        ${objStage ? `<div class="wo-team-card-detail">${esc(objStage)}</div>` : ''}
        <div class="wo-team-card-detail">${startLabel ? `Начал в ${startLabel} · ` : ''}работает ${durationLabel}</div>
        <div class="wo-team-card-status wo-status-active">● Смена идёт</div>
      </div>`;
    };

    let teamHtml = '';
    if (shifts) {
      const working = shifts.working_now || [];
      const notStarted = shifts.not_started || [];
      const awaiting = shifts.awaiting_response || [];

      // Краткая сводка -- счётчики строго из API length, не DOM. Кликабельны --
      // плавная прокрутка к соответствующему блоку (спек: не отдельные фильтры/экраны).
      const summaryHtml = `
        <div class="wo-summary-bar">
          <div class="wo-summary-tile" data-scroll-target="wo-anchor-working"><span class="wo-summary-num">${working.length}</span><span class="wo-summary-label">работают</span></div>
          <div class="wo-summary-tile" data-scroll-target="${notStarted.length ? 'wo-anchor-not-started' : 'wo-anchor-attention'}"><span class="wo-summary-num">${notStarted.length}</span><span class="wo-summary-label">не вышли</span></div>
          <div class="wo-summary-tile" data-scroll-target="${awaiting.length ? 'wo-anchor-awaiting' : 'wo-anchor-attention'}"><span class="wo-summary-num">${awaiting.length}</span><span class="wo-summary-label">ждут</span></div>
          <div class="wo-summary-tile" data-scroll-target="wo-anchor-without-object"><span class="wo-summary-num">${withoutObject.length}</span><span class="wo-summary-label">без объекта</span></div>
        </div>`;

      // Требует внимания -- ЕДИНСТВЕННОЕ место, где рендерятся not_started/awaiting
      // карточками, + активные stage-blocker'ы ("Сообщил о проблеме").
      const blockers = (blockersData && blockersData.blockers) || [];
      const blockerCard = b => `
        <div class="wo-team-card wo-blocker-card" data-object="${esc(b.object_id)}" data-row="${esc(b.row_num)}">
          <div class="wo-team-card-name">${esc(b.reported_by_name)}</div>
          <div class="wo-team-card-detail">${esc(b.object_name)}${b.stage_name ? ' · ' + esc(b.stage_name) : ''}${b.reason ? ' · ' + esc(b.reason) : ''}</div>
          <div class="wo-team-card-status wo-status-problem">Сообщил о проблеме</div>
          <button type="button" class="wo-blocker-resolve-btn" data-object="${esc(b.object_id)}" data-row="${esc(b.row_num)}">Проблема решена</button>
        </div>`;
      const attentionCount = notStarted.length + awaiting.length + blockers.length;
      // Cleanup-commit (спек): счётчики "Не вышли"/"Ждут" должны прокручивать к СВОИМ
      // подразделам, не к общему началу блока -- отдельные якоря, заголовки только
      // при наличии записей. Blocker-карточки остаются в общем разделе без своего якоря.
      const attentionHtml = attentionCount
        ? `
          ${notStarted.length ? `<div id="wo-anchor-not-started"><div class="wo-team-block-title">Не вышли</div>${notStarted.map(notStartedCard).join('')}</div>` : ''}
          ${awaiting.length ? `<div id="wo-anchor-awaiting"><div class="wo-team-block-title">Ожидают подтверждения</div>${awaiting.map(awaitingCard).join('')}</div>` : ''}
          ${blockers.map(blockerCard).join('')}
        `
        : '<div class="wo-empty">Всё в порядке</div>';

      // Активные смены -- отдельный заметный блок.
      const workingHtml = working.length ? working.map(activeCard).join('') : '<div class="wo-empty">Сейчас никто не работает</div>';

      // Часы команды -- компактный список: максимум 5, ненулевые сначала, без ID
      // как главного имени. Cleanup-commit (спек п.6): backend team_hours[].name уже
      // проходит через _sanitize_display_name (Worker Profile), но fallback там --
      // числовой Telegram ID, который тоже "проходит" как непустая строка. Порядок
      // здесь: 1) backend name (Worker Profile) 2) имя из уже загруженного /api/workers
      // 3) backend name если не состоит только из цифр 4) "Сотрудник".
      const workersByUid = {};
      workers.forEach(w => { workersByUid[String(w.user_id)] = w.name; });
      const _isNumericOnly = s => /^\d+$/.test((s || '').trim());
      const _resolveHoursName = t => {
        const backendName = t.name || '';
        if (backendName && !_isNumericOnly(backendName)) return backendName;
        const workerName = workersByUid[String(t.user_id)];
        if (workerName && !_isNumericOnly(workerName)) return workerName;
        return 'Сотрудник';
      };
      const teamHours = (stats && stats.team_hours) || [];
      const weekTotal = teamHours.reduce((sum, t) => sum + (t.hours || 0), 0);
      const nonZeroHours = teamHours.filter(t => t.hours > 0).slice(0, 5);
      const hoursHtml = teamHours.length ? `
        <div class="wo-section">
          <div class="wo-section-title">Часы команды</div>
          <div class="wo-hours-tiles">
            <div class="wo-hours-tile"><span class="wo-hours-tile-num">${working.length}</span><span class="wo-hours-tile-label">работают сейчас</span></div>
            <div class="wo-hours-tile"><span class="wo-hours-tile-num">${(shifts.hours_today_total || 0).toFixed(1)}</span><span class="wo-hours-tile-label">часов сегодня</span></div>
            <div class="wo-hours-tile"><span class="wo-hours-tile-num">${weekTotal.toFixed(1)}</span><span class="wo-hours-tile-label">часов за неделю</span></div>
          </div>
          ${nonZeroHours.length ? nonZeroHours.map(t => `
            <div class="wo-hours-row">
              <span class="wo-hours-name">${esc(_resolveHoursName(t))}</span>
              <span class="wo-hours-value">${t.hours.toFixed(1)} ч</span>
            </div>`).join('') : '<div class="wo-empty">На этой неделе часов пока нет</div>'}
        </div>` : '';

      teamHtml = `
        ${summaryHtml}

        <div class="wo-section" id="wo-anchor-attention">
          <div class="wo-section-title">Требует внимания${attentionCount ? ` (${attentionCount})` : ''}</div>
          ${attentionHtml}
        </div>

        <div class="wo-section" id="wo-anchor-working">
          <div class="wo-section-title">Активные смены${working.length ? ` (${working.length})` : ''}</div>
          ${workingHtml}
        </div>

        ${hoursHtml}
      `;
    }

    slot.innerHTML = `
      ${teamHtml}

      <div class="wo-section" id="wo-anchor-without-object">
        <div class="wo-section-title">Без объекта${withoutObject.length ? ` (${withoutObject.length})` : ''}</div>
        ${withoutObject.length ? withoutObject.map(w => `
          <div class="wo-worker-row" data-uid="${esc(w.user_id)}">
            <span class="wo-worker-name">${esc(w.name)}</span>
            <button class="submit-btn wo-assign-btn" data-uid="${esc(w.user_id)}" data-name="${esc(w.name)}">Назначить</button>
          </div>`).join('') : '<div class="wo-empty">Все назначены на объекты</div>'}
      </div>

      <div class="wo-section">
        <div class="wo-collapsible-header" data-collapsible="absent">
          <div class="wo-section-title">Отсутствуют сегодня${absentToday.length ? ` · ${absentToday.length}` : ''}</div>
          <span class="wo-collapsible-chevron">▾</span>
        </div>
        <div class="wo-collapsible-body">
          ${absentToday.length ? absentToday.map(e => `
            <div class="wo-worker-row">
              <span class="wo-worker-name">${esc(e.name)}</span>
              <span class="wo-absence-reason">${esc(e.reason || '')}${e.date_from ? ` · ${esc(e.date_from)} — ${esc(e.date_to || '')}` : ''}</span>
            </div>`).join('') : '<div class="wo-empty">Все на месте</div>'}
        </div>
      </div>

      <div class="wo-section">
        <div class="wo-collapsible-header" data-collapsible="by-object">
          <div class="wo-section-title">Распределение по объектам</div>
          <span class="wo-collapsible-chevron">▾</span>
        </div>
        <div class="wo-collapsible-body">
          ${activeObjects.length ? activeObjects.map(o => `
            <div class="wo-object-block">
              <div class="wo-object-name">${esc(o['Объект'] || '')}</div>
              ${(o.assigned_users || []).map(u => `<div class="wo-worker-row wo-worker-row-nested"><span class="wo-worker-name">${esc(u.name)}</span></div>`).join('')}
            </div>`).join('') : '<div class="wo-empty">Нет назначений</div>'}
        </div>
      </div>
    `;

    slot.querySelectorAll('.wo-assign-btn').forEach(btn => {
      btn.addEventListener('click', () => _openWorkingObjectsAssignSheet(btn.dataset.uid, btn.dataset.name, objects));
    });
    // 30.07 v4 (спек п.8): tap по всей карточке -- существующая user-card, не объект.
    slot.querySelectorAll('.wo-team-card[data-uid]').forEach(card => {
      card.addEventListener('click', () => {
        if (typeof openUserCard === 'function') openUserCard(card.dataset.uid);
      });
    });
    slot.querySelectorAll('.wo-summary-tile[data-scroll-target]').forEach(tile => {
      tile.addEventListener('click', () => {
        document.getElementById(tile.dataset.scrollTarget)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
    slot.querySelectorAll('.wo-collapsible-header').forEach(header => {
      header.addEventListener('click', () => {
        header.parentElement.classList.toggle('wo-collapsible-open');
      });
    });
    slot.querySelectorAll('.wo-blocker-resolve-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        try {
          await api(`/api/objects/${btn.dataset.object}/stages/${btn.dataset.row}/blocker`, { method: 'DELETE' });
          hapticImpact('light');
          loadedViews.delete('working-objects');
          initWorkingObjectsView();
        } catch (err) {
          showToast('Ошибка: ' + err.message, 'error');
          btn.disabled = false;
        }
      });
    });
  } catch (e) {
    slot.innerHTML = '<div style="padding:1rem;color:var(--text-light)">Ошибка загрузки</div>';
  }
}

// Простой bottom-sheet выбора объекта для воркера без назначения —
// bubble-assign.js требует объект+этап заранее известными, тут наоборот (воркер известен, объект — нет).
function _openWorkingObjectsAssignSheet(userId, userName, objects) {
  const activeObjects = objects.filter(o => o['Статус'] === 'В работе');
  const existing = document.getElementById('wo-assign-sheet');
  if (existing) existing.remove();

  const sheet = document.createElement('div');
  sheet.id = 'wo-assign-sheet';
  sheet.className = 'wo-assign-sheet';
  sheet.innerHTML = `
    <div class="wo-assign-sheet-inner">
      <div class="wo-assign-sheet-title">Назначить ${esc(userName)}</div>
      ${activeObjects.length ? activeObjects.map(o => `
        <div class="wo-assign-sheet-opt" data-oid="${esc(o['ID объекта'])}">${esc(o['Объект'] || '')}</div>
      `).join('') : '<div class="wo-empty">Нет активных объектов</div>'}
      <button class="submit-btn wo-assign-sheet-cancel" type="button">Отмена</button>
    </div>
  `;
  document.body.appendChild(sheet);

  sheet.querySelector('.wo-assign-sheet-cancel').addEventListener('click', () => sheet.remove());
  sheet.querySelectorAll('.wo-assign-sheet-opt').forEach(opt => {
    opt.addEventListener('click', async () => {
      try {
        await api(`/api/objects/${opt.dataset.oid}/assign`, {
          method: 'POST',
          body: JSON.stringify({ user_id: userId }),
        });
        hapticImpact('medium');
        showToast('Назначено', 'success');
        sheet.remove();
        loadedViews.delete('working-objects');
        initWorkingObjectsView();
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  });
}

// ═══════════ "Команда" → вкладка "План" (30.07 v5, спек): отвечает только "кто
// запланирован на дату и на каком объекте" из существующих назначений. Источник --
// новый read-only GET /api/dashboard/team-plan?date=, "Добавить назначение" переиспользует
// существующий полный flow openAssignFromProfile (стадия/период/task_note уже там),
// добавлен только worker-picker шаг перед ним (там worker уже известен, тут — нет). ═══════════

let _woPlanLoaded = false;
let _woPlanDate = '';

// Локальная дата без ошибки UTC через toISOString() (тот сдвигает дату у пользователей
// восточнее UTC вечером/западнее UTC утром).
function _localISODate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function _woPlanDateOptions() {
  const labels = ['Сегодня', 'Завтра', 'Послезавтра'];
  const opts = [];
  for (let i = 0; i < 3; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    opts.push({ date: _localISODate(d), label: labels[i] });
  }
  for (let i = 3; i < 7; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    opts.push({ date: _localISODate(d), label: d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) });
  }
  return opts;
}

async function _initWorkingObjectsPlanTab() {
  _woPlanDate = _localISODate(new Date());
  const slot = document.getElementById('working-objects-plan-slot');
  if (!slot) return;

  const dateOpts = _woPlanDateOptions();
  slot.innerHTML = `
    <div class="wo-plan-dates" id="wo-plan-dates">
      ${dateOpts.map(o => `<div class="wo-plan-date-opt${o.date === _woPlanDate ? ' active' : ''}" data-date="${esc(o.date)}">${esc(o.label)}</div>`).join('')}
      <div class="wo-plan-date-opt" data-date-picker="1">📅</div>
    </div>
    <input type="date" id="wo-plan-date-input" style="position:absolute;opacity:0;pointer-events:none;width:1px;height:1px;">
    <button class="submit-btn wo-plan-add-btn" id="wo-plan-add-btn" type="button">Добавить назначение</button>
    <div id="wo-plan-content"></div>
  `;

  slot.querySelectorAll('.wo-plan-date-opt[data-date]').forEach(opt => {
    opt.addEventListener('click', () => _woPlanSelectDate(opt.dataset.date));
  });
  slot.querySelector('[data-date-picker]')?.addEventListener('click', () => {
    document.getElementById('wo-plan-date-input')?.showPicker?.() || document.getElementById('wo-plan-date-input').click();
  });
  document.getElementById('wo-plan-date-input')?.addEventListener('change', (e) => {
    if (e.target.value) _woPlanSelectDate(e.target.value, true);
  });
  document.getElementById('wo-plan-add-btn')?.addEventListener('click', () => _openWorkingObjectsPlanAddSheet());

  await _loadWorkingObjectsPlanContent();
}

function _woPlanSelectDate(date, isCustom) {
  _woPlanDate = date;
  const dateOpts = _woPlanDateOptions();
  const isKnown = dateOpts.some(o => o.date === date);
  const container = document.getElementById('wo-plan-dates');
  if (container) {
    if (isCustom && !isKnown) {
      container.innerHTML = dateOpts.map(o => `<div class="wo-plan-date-opt" data-date="${esc(o.date)}">${esc(o.label)}</div>`).join('')
        + `<div class="wo-plan-date-opt active" data-date="${esc(date)}">${esc(date)}</div>`
        + `<div class="wo-plan-date-opt" data-date-picker="1">📅</div>`;
      container.querySelectorAll('.wo-plan-date-opt[data-date]').forEach(opt => {
        opt.addEventListener('click', () => _woPlanSelectDate(opt.dataset.date));
      });
      container.querySelector('[data-date-picker]')?.addEventListener('click', () => {
        document.getElementById('wo-plan-date-input')?.showPicker?.() || document.getElementById('wo-plan-date-input').click();
      });
    } else {
      container.querySelectorAll('.wo-plan-date-opt[data-date]').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.date === date);
      });
    }
  }
  _loadWorkingObjectsPlanContent();
}

const WO_PLAN_STATUS_LABEL = { accepted: 'Принято', pending: 'Ожидает подтверждения', declined: 'Отклонено' };
const WO_PLAN_SHIFT_LABEL = { active: 'Смена идёт', not_started: 'Смена не начата', finished: 'Смена завершена' };

async function _loadWorkingObjectsPlanContent() {
  const content = document.getElementById('wo-plan-content');
  if (!content) return;
  content.innerHTML = '<div style="padding:1rem;color:var(--text-light)">Загрузка…</div>';
  try {
    const data = await api(`/api/dashboard/team-plan?date=${encodeURIComponent(_woPlanDate)}`);
    const objects = data.objects || [];
    if (!objects.length) {
      content.innerHTML = '<div class="wo-empty" style="padding:0.75rem;">На эту дату назначений нет</div>';
      return;
    }
    content.innerHTML = objects.map(o => `
      <div class="wo-plan-object-block">
        <div class="wo-plan-object-name">${esc(o.object_name)}</div>
        ${o.assignments.map(a => `
          <div class="wo-plan-row" data-uid="${esc(a.user_id)}">
            <div class="wo-plan-row-top">
              <span class="wo-plan-row-name">${esc(a.worker_name)}${(a.stage_name || a.stage_id) ? ` — <span class="wo-plan-row-stage">${esc(a.stage_name || a.stage_id)}</span>` : ''}</span>
              <span class="wo-plan-status wo-plan-status-${a.assignment_status}">${esc(WO_PLAN_STATUS_LABEL[a.assignment_status] || a.assignment_status)}</span>
            </div>
            ${a.task_note ? `<div class="wo-plan-row-detail">${esc(a.task_note)}</div>` : ''}
            <div class="wo-plan-row-detail">${esc(a.date_from)} — ${esc(a.date_to)}</div>
            ${a.shift_state ? `<div class="wo-plan-status-shift">${esc(WO_PLAN_SHIFT_LABEL[a.shift_state] || a.shift_state)}</div>` : ''}
          </div>`).join('')}
      </div>`).join('');
    content.querySelectorAll('.wo-plan-row[data-uid]').forEach(row => {
      row.addEventListener('click', () => {
        if (typeof openUserCard === 'function') openUserCard(row.dataset.uid);
      });
    });
  } catch (e) {
    content.innerHTML = '<div class="js-error-state">Ошибка загрузки</div>';
  }
}

// Worker-picker перед существующим openAssignFromProfile -- там воркер уже известен,
// тут его сначала нужно выбрать. Выбранная в "Плане" дата подставляется как
// date_from/date_to (юзер может поменять внутри самого openAssignFromProfile popup).
async function _openWorkingObjectsPlanAddSheet() {
  let workers = [];
  try {
    const data = await api('/api/workers');
    workers = (data.workers || []).filter(w => w.role === 'worker');
  } catch (e) {
    showToast('Не удалось загрузить работников: ' + e.message, 'error');
    return;
  }
  const existing = document.getElementById('wo-assign-sheet');
  if (existing) existing.remove();

  const sheet = document.createElement('div');
  sheet.id = 'wo-assign-sheet';
  sheet.className = 'wo-assign-sheet';
  sheet.innerHTML = `
    <div class="wo-assign-sheet-inner">
      <div class="wo-assign-sheet-title">Выберите работника</div>
      ${workers.length ? workers.map(w => `
        <div class="wo-assign-sheet-opt" data-uid="${esc(w.user_id)}" data-name="${esc(w.name)}">${esc(w.name)}</div>
      `).join('') : '<div class="wo-empty">Нет работников</div>'}
      <button class="submit-btn wo-assign-sheet-cancel" type="button">Отмена</button>
    </div>
  `;
  document.body.appendChild(sheet);
  sheet.querySelector('.wo-assign-sheet-cancel').addEventListener('click', () => sheet.remove());
  sheet.querySelectorAll('.wo-assign-sheet-opt').forEach(opt => {
    opt.addEventListener('click', () => {
      sheet.remove();
      openAssignFromProfile(opt.dataset.uid, opt.dataset.name, _woPlanDate);
    });
  });
}
