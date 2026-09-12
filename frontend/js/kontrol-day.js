// Контроль дня: owner overview for daily plans and worker execution state.

let _kdFilter = 'all';
let _kdRows = [];
let _kdLoaded = false;

async function initKontrolDayView() {
  _kdLoaded = false;
  _kdFilter = 'all';
  document.querySelectorAll('.kd-filter-chip').forEach(c => c.classList.toggle('active', c.dataset.kdFilter === 'all'));
  document.getElementById('kd-rows-list').innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-light)">Загрузка…</div>';

  const filtersEl = document.getElementById('kd-filters');
  if (filtersEl && !filtersEl.dataset.wired) {
    filtersEl.dataset.wired = '1';
    filtersEl.addEventListener('click', e => {
      const chip = e.target.closest('.kd-filter-chip');
      if (!chip) return;
      _kdFilter = chip.dataset.kdFilter;
      document.querySelectorAll('.kd-filter-chip').forEach(c => c.classList.toggle('active', c === chip));
      _renderKdRows();
    });
  }

  document.getElementById('kd-detail-close').onclick = () => {
    closeKdDetail();
  };
  document.getElementById('kd-detail-overlay').onclick = e => {
    if (e.target === document.getElementById('kd-detail-overlay')) {
      closeKdDetail();
    }
  };

  try {
    const data = await api('/api/daily-plan/owner/today');
    _kdRows = data.rows || [];
    const s = data.summary || {};
    _renderKdKpi(s, data.date);
    _renderKdRows();
    _kdLoaded = true;
  } catch (e) {
    document.getElementById('kd-rows-list').innerHTML = `<div style="padding:2rem;text-align:center;color:var(--red)">Ошибка загрузки: ${esc(e.message)}<br><button class="submit-btn" style="margin-top:1rem" onclick="initKontrolDayView()">Повторить</button></div>`;
  }
}

function _renderKdKpi(summary, date) {
  const strip = document.getElementById('kd-kpi-strip');
  if (!strip) return;
  const d = date ? new Date(date).toLocaleDateString('ru', { day: 'numeric', month: 'long' }) : '';
  document.getElementById('kd-header-title').textContent = `Контроль дня · ${d}`;
  const chips = [
    { key: 'all', num: summary.total_plans || 0, label: 'Планы' },
    { key: 'not_accepted', num: (summary.total_plans || 0) - (summary.accepted || 0), label: 'Не приняли' },
    { key: 'working', num: summary.working || 0, label: 'Работают' },
    { key: 'finished', num: summary.finished || 0, label: 'Завершили' },
    { key: 'carryover', num: summary.has_carryovers || 0, label: 'Переносы' },
  ];
  strip.innerHTML = chips.map(c =>
    `<div class="kd-kpi-chip" data-kd-kpi="${esc(c.key)}"><span class="kd-kpi-num">${c.num}</span><span class="kd-kpi-label">${esc(c.label)}</span></div>`
  ).join('');
  strip.querySelectorAll('.kd-kpi-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      _kdFilter = chip.dataset.kdKpi;
      document.querySelectorAll('.kd-filter-chip').forEach(c => c.classList.toggle('active', c.dataset.kdFilter === _kdFilter));
      _renderKdRows();
    });
  });
}

function _renderKdRows() {
  const list = document.getElementById('kd-rows-list');
  if (!list) return;
  const filtered = _kdRows.filter(row => {
    if (_kdFilter === 'all') return true;
    if (_kdFilter === 'not_accepted') return !row.acceptance;
    if (_kdFilter === 'working') return row.shift_status === 'working';
    if (_kdFilter === 'finished') return row.shift_status === 'finished';
    if (_kdFilter === 'carryover') return row.carryover_count > 0;
    if (_kdFilter === 'risk') return row.risk_level === 'orange' || row.risk_level === 'red';
    return true;
  });

  if (!filtered.length) {
    list.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-light)">Нет записей для выбранного фильтра</div>';
    return;
  }

  list.innerHTML = filtered.map(row => {
    const riskBadge = { green: 'kd-badge-green', yellow: 'kd-badge-yellow', orange: 'kd-badge-orange', red: 'kd-badge-red' }[row.risk_level] || 'kd-badge-neutral';
    const shiftLabels = { not_started: 'Не начата', working: 'Работает', paused: 'Пауза', finished: 'Завершена' };
    const planLabels = { NOT_ACCEPTED: 'Ожидает принятия', ACCEPTED: 'Принят', DRAFT: 'Черновик', AMENDMENT_PENDING: 'Изм. не подтверждены', COMPLETED: 'Завершён' };

    return `<div class="kd-row" data-kd-plan-id="${esc(row.plan_id)}" data-kd-worker-id="${esc(row.worker_id)}">
      <div class="kd-row-top">
        <div>
          <div class="kd-row-worker">${esc(row.worker_id)}</div>
          <div class="kd-row-object">${esc(row.object_id)} · ${esc(row.plan_summary?.stage_key || '')}</div>
        </div>
        <span class="kd-badge ${riskBadge}">${row.risk_level === 'orange' ? '⚠' : row.risk_level === 'red' ? '🔴' : row.risk_level === 'yellow' ? '!' : '✓'}</span>
      </div>
      <div class="kd-row-meta">
        <span class="kd-badge ${row.acceptance ? 'kd-badge-green' : 'kd-badge-yellow'}">${esc(planLabels[row.plan_status_label] || row.plan_status_label)}</span>
        <span class="kd-badge kd-badge-neutral">${esc(shiftLabels[row.shift_status] || row.shift_status)}</span>
        ${row.carryover_count ? `<span class="kd-badge kd-badge-yellow">↩ ${row.carryover_count} переноса</span>` : ''}
        ${row.execution_summary ? `<span class="kd-badge kd-badge-green">✓ ${row.execution_summary.done}/${row.execution_summary.total}</span>` : ''}
      </div>
    </div>`;
  }).join('');

  list.querySelectorAll('.kd-row').forEach(el => {
    el.addEventListener('click', () => _showKdDetail(el.dataset.kdPlanId, el.dataset.kdWorkerId));
  });
}

async function _showKdDetail(planId, workerId) {
  const overlay = document.getElementById('kd-detail-overlay');
  const body = document.getElementById('kd-detail-body');
  const title = document.getElementById('kd-detail-title');
  if (!overlay || !body) return;

  overlay.style.display = 'flex';
  body.innerHTML = '<div style="text-align:center;color:var(--text-light);padding:1rem">Загрузка…</div>';
  title.textContent = 'Детали';

  const row = _kdRows.find(r => r.plan_id === planId && r.worker_id === workerId);
  if (!row) { body.innerHTML = '<div style="color:var(--red)">Не найдено</div>'; return; }

  title.textContent = `${row.worker_id} · ${row.date}`;

  let planDetail = null;
  try {
    planDetail = await api(`/api/daily-plan/${encodeURIComponent(planId)}`);
  } catch (_) {}

  const plan = planDetail?.plan || {};
  const items = plan.items || [];
  const acc = planDetail?.acceptance;
  const exec = row.execution_summary;

  const itemsHtml = items.map((item, i) => {
    const res = planDetail?.execution?.item_results?.find?.(r => r.item_id === item.id);
    return `<div class="wc-today-item" style="margin-bottom:0.4rem">
      <span class="wc-today-item-num">${i + 1}</span>
      <div class="wc-today-item-body">
        <div class="wc-today-item-title">${esc(item.title)}</div>
        ${item.planned_quantity != null ? `<div class="wc-today-item-meta">${item.planned_quantity} ${esc(item.unit || '')}</div>` : ''}
        ${res ? `<div class="kd-badge ${res.status === 'done' ? 'kd-badge-green' : res.status === 'blocked' ? 'kd-badge-orange' : 'kd-badge-yellow'}" style="display:inline-block;margin-top:0.2rem">${{ done: 'Выполнено', partial: 'Частично', not_done: 'Не выполнено', blocked: 'Заблокировано' }[res.status] || res.status}</div>` : ''}
      </div>
    </div>`;
  }).join('') || '<div style="color:var(--text-light);font-size:0.85rem">Нет позиций плана</div>';

  body.innerHTML = `
    <div style="font-size:0.8rem;color:var(--text-light);margin-bottom:0.75rem">${esc(row.object_id)} · ${esc(row.plan_summary?.stage_key || '')} · v${row.plan_summary?.version || 1}</div>
    ${acc ? `<div style="font-size:0.8rem;margin-bottom:0.75rem">Принят в ${new Date(acc.accepted_at * 1000).toLocaleTimeString('ru', {hour:'2-digit',minute:'2-digit'})}</div>` : ''}
    ${exec ? `<div class="kd-badge kd-badge-green" style="display:inline-block;margin-bottom:0.75rem">✓ ${exec.done} из ${exec.total} выполнено</div>` : ''}
    ${row.carryover_count ? `<div class="kd-badge kd-badge-yellow" style="display:inline-block;margin-bottom:0.75rem">↩ ${row.carryover_count} перенос(а)</div>` : ''}
    <div style="font-weight:600;margin-bottom:0.4rem">Позиции плана</div>
    ${itemsHtml}
    <button type="button" class="submit-btn" style="width:100%;margin-top:1rem" onclick="closeKdDetail();openWorkerCard('${workerId}',{initialTab:'today'})">Открыть карточку сотрудника</button>
  `;
}

function closeKdDetail() {
  const overlay = document.getElementById('kd-detail-overlay');
  if (overlay) overlay.style.display = 'none';
}
