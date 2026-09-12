// Contracts: owner review flow for Google Drive-ingested contract drafts.

async function initContractsView() {
  const list = document.getElementById('contracts-list');
  if (!list) return;
  list.innerHTML = '<div style="color:var(--text-light);text-align:center;padding:2rem">Загрузка…</div>';
  try {
    const data = await api('/api/contracts');
    if (!data.drive_configured) {
      list.innerHTML = `<div class="card" style="margin-bottom:0.75rem">
        <div style="font-weight:700;margin-bottom:0.5rem;color:var(--warning-text)">⚠ Drive не настроен</div>
        <div style="font-size:0.85rem;color:var(--text-light)">Договора загружаются из Google Drive. Необходимо настроить CONTRACTS_DRIVE_FOLDER_ID. Подробности в docs/OPEN_QUESTIONS.md (Q1).</div>
      </div>`;
      return;
    }
    if (!data.contracts.length) {
      list.innerHTML = '<div style="color:var(--text-light);text-align:center;padding:2rem">Нет загруженных договоров</div>';
      return;
    }
    const statusLabel = {
      pending: 'Ожидает', ingesting: 'Обрабатывается', ingested: 'Готов к проверке',
      extraction_failed: 'Ошибка', needs_manual_review: 'Нужна проверка',
      needs_ocr: 'Нужен OCR', approved: 'Утверждён', rejected: 'Отклонён',
    };
    const statusClass = {
      ingested: 'kd-badge-yellow', needs_manual_review: 'kd-badge-orange',
      approved: 'kd-badge-green', rejected: 'kd-badge-neutral',
      extraction_failed: 'kd-badge-red', needs_ocr: 'kd-badge-orange',
    };
    list.innerHTML = data.contracts.map(c => `
      <div class="card contract-card" style="margin-bottom:0.75rem;cursor:pointer" data-contract-id="${esc(c.id)}">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:0.5rem">
          <div style="font-weight:700;font-size:0.9rem">${esc(c.file_name)}</div>
          <span class="kd-badge ${statusClass[c.status] || 'kd-badge-neutral'}">${esc(statusLabel[c.status] || c.status)}</span>
        </div>
        ${c.error ? `<div style="font-size:0.75rem;color:var(--red);margin-top:0.2rem">${esc(c.error)}</div>` : ''}
        <div style="font-size:0.75rem;color:var(--text-light);margin-top:0.3rem">${c.ingested_at ? new Date(c.ingested_at * 1000).toLocaleDateString('ru') : ''}</div>
      </div>`).join('');
    list.querySelectorAll('.contract-card[data-contract-id]').forEach(card => {
      card.addEventListener('click', () => openContractDetail(card.dataset.contractId));
    });
  } catch (e) {
    list.innerHTML = `<div style="color:var(--red);text-align:center;padding:2rem">Ошибка: ${esc(e.message)}</div>`;
  }
}

async function openContractDetail(contractId) {
  let contract;
  try {
    contract = await api(`/api/contracts/${encodeURIComponent(contractId)}`);
  } catch (e) {
    showToast('Ошибка загрузки договора', 'error');
    return;
  }
  const overlay = document.createElement('div');
  overlay.className = 'kd-detail-overlay';
  overlay.style.display = 'flex';
  const facts = contract.extracted_facts || {};
  const draft = contract.project_plan_draft || {};
  const canApprove = ['ingested', 'needs_manual_review'].includes(contract.status) && draft.positions?.length;
  overlay.innerHTML = `
    <div class="kd-detail-sheet">
      <div class="kd-detail-header">
        <span class="kd-detail-title">${esc(contract.file_name)}</span>
        <button type="button" class="kd-detail-close" id="contract-detail-close">✕</button>
      </div>
      ${contract.text_preview ? `<div style="background:var(--bg-card);border-radius:var(--radius-md);padding:0.5rem;font-size:0.75rem;color:var(--text-light);margin-bottom:0.75rem;white-space:pre-wrap">${esc(contract.text_preview.slice(0, 300))}…</div>` : ''}
      ${facts.object_address ? `<div style="margin-bottom:0.4rem"><b>Объект:</b> ${esc(facts.object_address)}</div>` : ''}
      ${facts.contract_finish_date ? `<div style="margin-bottom:0.4rem"><b>Срок по договору:</b> ${esc(facts.contract_finish_date)}</div>` : ''}
      ${(facts.positions || []).length ? `
        <div style="font-weight:600;margin:0.75rem 0 0.4rem">Позиции</div>
        ${facts.positions.map(p => `<div class="wc-today-item" style="margin-bottom:0.3rem">
          <span class="wc-today-item-num">•</span>
          <div class="wc-today-item-body">
            <div class="wc-today-item-title">${esc(p.title)}</div>
            ${p.quantity != null ? `<div class="wc-today-item-meta">${p.quantity} ${esc(p.unit || '')}</div>` : '<div class="wc-today-item-meta" style="color:var(--warning-text)">Количество не указано</div>'}
          </div>
        </div>`).join('')}` : ''}
      ${canApprove ? `
        <div style="display:flex;gap:0.5rem;margin-top:1rem">
          <button type="button" class="submit-btn" style="flex:1;background:var(--accent)" id="contract-approve-btn">УТВЕРДИТЬ</button>
          <button type="button" class="submit-btn" style="flex:1;background:var(--bg-card-raised);color:var(--red);border:1px solid var(--red)" id="contract-reject-btn">ОТКЛОНИТЬ</button>
        </div>` : ''}
      ${contract.status === 'approved' ? '<div class="kd-badge kd-badge-green" style="display:inline-block;margin-top:0.75rem">✓ Утверждён</div>' : ''}
      ${contract.status === 'rejected' ? '<div class="kd-badge kd-badge-neutral" style="display:inline-block;margin-top:0.75rem">Отклонён</div>' : ''}
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#contract-detail-close').onclick = () => overlay.remove();
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  overlay.querySelector('#contract-approve-btn')?.addEventListener('click', async () => {
    try {
      await api(`/api/contracts/${encodeURIComponent(contractId)}/approve`, { method: 'POST' });
      showToast('Договор утверждён', 'success');
      overlay.remove();
      initContractsView();
    } catch (e) { showToast('Ошибка: ' + e.message, 'error'); }
  });
  overlay.querySelector('#contract-reject-btn')?.addEventListener('click', async () => {
    try {
      await api(`/api/contracts/${encodeURIComponent(contractId)}/reject`, { method: 'POST' });
      showToast('Договор отклонён', 'info');
      overlay.remove();
      initContractsView();
    } catch (e) { showToast('Ошибка: ' + e.message, 'error'); }
  });
}
