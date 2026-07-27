// Таб "Rechnung": форма создания счёта (PDF).

let rechnungPositions = [{ titel: '', beschreibung: '', menge: 1, einheit: 'm²', preis: 0 }];

function calcRechnungTotals() {
  const mwstSatz = parseFloat(document.getElementById('rMwstSatz')?.value) || 19;
  const netto = rechnungPositions.reduce((s, p) => s + (p.menge * p.preis || 0), 0);
  const mwst = netto * mwstSatz / 100;
  const brutto = netto + mwst;
  return { netto, mwst, mwstSatz, brutto };
}

function renderRechnungPositions() {
  return rechnungPositions.map((p, i) => `
    <div class="position-card" data-idx="${i}">
      ${rechnungPositions.length > 1 ? `<button class="remove-pos" data-remove="${i}">×</button>` : ''}
      <div class="field">
        <label>Название работы</label>
        <input type="text" data-field="titel" data-idx="${i}" value="${esc(p.titel)}" placeholder="напр. Beräumung">
      </div>
      <div class="field">
        <label>Описание (опционально)</label>
        <input type="text" data-field="beschreibung" data-idx="${i}" value="${esc(p.beschreibung)}" placeholder="напр. Leistungszeitraum: 12.05 – 30.05">
      </div>
      <div class="row-2">
        <div class="field">
          <label>Кол-во</label>
          <input type="number" step="0.01" data-field="menge" data-idx="${i}" value="${p.menge}">
        </div>
        <div class="field">
          <label>Ед.изм.</label>
          <select data-field="einheit" data-idx="${i}">
            ${['m²', 'Stk', 'Lfm', 'Std.', 'pauschal'].map(u => `<option value="${u}" ${p.einheit === u ? 'selected' : ''}>${u}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <label>Цена/ед €</label>
          <input type="number" step="0.01" data-field="preis" data-idx="${i}" value="${p.preis}">
        </div>
      </div>
      <div class="position-sum">Сумма: <b>${fmtEuro((p.menge || 0) * (p.preis || 0))}</b></div>
    </div>
  `).join('');
}

function renderRechnungTotals() {
  const t = calcRechnungTotals();
  return `
    <div class="totals">
      <div class="row"><span>Summe (netto)</span><span>${fmtEuro(t.netto)}</span></div>
      <div class="row"><span>${t.mwstSatz}% Ust.</span><span>${fmtEuro(t.mwst)}</span></div>
      <div class="row grand"><span>Endbetrag (brutto)</span><span>${fmtEuro(t.brutto)}</span></div>
    </div>`;
}

function renderRechnungForm() {
  document.getElementById('rechnung-content').innerHTML = `
    <div class="section">
      <div class="section-title">Rechnung-Nr.</div>
      <div class="field">
        <label>Номер счёта</label>
        <input type="text" id="rNummer" placeholder="напр. RE-2026-042">
      </div>
    </div>

    <div class="section">
      <div class="section-title">Kunde</div>
      <div class="field">
        <label>Тип клиента</label>
        <select id="rKundeTyp">
          <option value="privat">Privatperson</option>
          <option value="firma">Firma</option>
        </select>
      </div>
      <div id="r-kunde-privat-fields" class="row-2">
        <div class="field" style="flex:0 0 90px">
          <label>Anrede</label>
          <select id="rAnrede">
            <option value="Herr">Herr</option>
            <option value="Frau">Frau</option>
          </select>
        </div>
        <div class="field">
          <label>Имя</label>
          <input type="text" id="rKundeName" placeholder="Max Mustermann">
        </div>
      </div>
      <div id="r-kunde-firma-fields" style="display:none">
        <div class="field">
          <label>Название фирмы</label>
          <input type="text" id="rFirmaName" placeholder="Hans Fries GmbH">
        </div>
        <div class="field">
          <label>Контактное лицо (опционально)</label>
          <input type="text" id="rFirmaKontakt" placeholder="Hr. Fries">
        </div>
        <div class="field">
          <label>Ust-ID клиента (опционально)</label>
          <input type="text" id="rFirmaUstId" placeholder="DE123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес клиента</label>
        <input type="text" id="rKundeAdresse" placeholder="Straße, PLZ Ort">
      </div>
    </div>

    <div class="section">
      <div class="section-title">Projekt</div>
      <div class="field">
        <label>Название проекта (опционально)</label>
        <input type="text" id="rProjekt" placeholder="напр. Beräumung, Hermannsdorf">
      </div>
    </div>

    <div class="section">
      <div class="section-title">Positionen</div>
      <div id="rechnung-positions">${renderRechnungPositions()}</div>
      <button class="add-position-btn" id="r-add-position">+ Позиция</button>
    </div>

    <div class="section">
      <div class="section-title">Условия</div>
      <div class="row-2">
        <div class="field">
          <label>MwSt %</label>
          <input type="number" id="rMwstSatz" value="19">
        </div>
        <div class="field">
          <label>Zahlungsfrist, дней</label>
          <input type="number" id="rZahlungsfrist" value="14">
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Итого</div>
      <div id="rechnung-totals">${renderRechnungTotals()}</div>
    </div>

    <div id="rechnung-error-container"></div>
  `;

  attachRechnungFormHandlers();
}

function attachRechnungFormHandlers() {
  document.querySelectorAll('#rechnung-positions [data-field]').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      const field = e.target.dataset.field;
      let val = e.target.value;
      if (field === 'menge' || field === 'preis') val = parseFloat(val) || 0;
      rechnungPositions[idx][field] = val;
      document.getElementById('rechnung-positions').innerHTML = renderRechnungPositions();
      document.getElementById('rechnung-totals').innerHTML = renderRechnungTotals();
      attachRechnungFormHandlers();
    });
  });

  document.querySelectorAll('#rechnung-positions [data-remove]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      rechnungPositions.splice(parseInt(e.target.dataset.remove, 10), 1);
      document.getElementById('rechnung-positions').innerHTML = renderRechnungPositions();
      document.getElementById('rechnung-totals').innerHTML = renderRechnungTotals();
      attachRechnungFormHandlers();
    });
  });

  document.getElementById('r-add-position').addEventListener('click', () => {
    rechnungPositions.push({ titel: '', beschreibung: '', menge: 1, einheit: 'm²', preis: 0 });
    document.getElementById('rechnung-positions').innerHTML = renderRechnungPositions();
    attachRechnungFormHandlers();
  });

  document.getElementById('rMwstSatz').addEventListener('input', () => {
    document.getElementById('rechnung-totals').innerHTML = renderRechnungTotals();
  });

  document.getElementById('rKundeTyp').addEventListener('change', (e) => {
    const isFirma = e.target.value === 'firma';
    document.getElementById('r-kunde-privat-fields').style.display = isFirma ? 'none' : 'flex';
    document.getElementById('r-kunde-firma-fields').style.display = isFirma ? 'block' : 'none';
  });
}

async function submitRechnung() {
  const errorContainer = document.getElementById('rechnung-error-container');
  errorContainer.innerHTML = '';

  const nummer = document.getElementById('rNummer').value.trim();
  if (!nummer) {
    errorContainer.innerHTML = '<div class="error-banner">Укажи номер счёта.</div>';
    return;
  }

  const isFirma = document.getElementById('rKundeTyp').value === 'firma';
  let kunde;
  let displayName;

  if (isFirma) {
    const firmaName = document.getElementById('rFirmaName').value.trim();
    if (!firmaName) {
      errorContainer.innerHTML = '<div class="error-banner">Укажи название фирмы.</div>';
      return;
    }
    displayName = firmaName;
    kunde = {
      typ: 'firma',
      name: firmaName,
      kontakt: document.getElementById('rFirmaKontakt').value.trim(),
      ustId: document.getElementById('rFirmaUstId').value.trim(),
      adresse: document.getElementById('rKundeAdresse').value.trim(),
    };
  } else {
    const kundeName = document.getElementById('rKundeName').value.trim();
    if (!kundeName) {
      errorContainer.innerHTML = '<div class="error-banner">Укажи имя клиента.</div>';
      return;
    }
    displayName = kundeName;
    kunde = {
      typ: 'privat',
      anrede: document.getElementById('rAnrede').value,
      name: kundeName,
      adresse: document.getElementById('rKundeAdresse').value.trim(),
    };
  }

  const validPositions = rechnungPositions.filter(p => p.titel.trim() && p.menge > 0 && p.preis >= 0);
  if (!validPositions.length) {
    errorContainer.innerHTML = '<div class="error-banner">Добавь хотя бы одну позицию с названием, кол-вом и ценой.</div>';
    return;
  }

  const body = {
    nummer,
    kunde,
    projekt: document.getElementById('rProjekt').value.trim(),
    positionen: validPositions,
    mwstSatz: parseFloat(document.getElementById('rMwstSatz').value) || 19,
    zahlungsfristTage: parseInt(document.getElementById('rZahlungsfrist').value, 10) || 14,
  };

  // Фаза 7: подпись опциональна — openSignaturePad() резолвится в null если пропущена/пустая.
  if (typeof openSignaturePad === 'function') {
    const signature = await openSignaturePad(`Подпись — ${kunde.name}`);
    if (signature) body.signatureBase64 = signature;
  }

  const btn = document.getElementById('rechnung-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Генерация PDF...';

  try {
    const res = await fetch(API_BASE + '/api/rechnung', {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Rechnung_${displayName.replace(/\s+/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    errorContainer.innerHTML = `<div class="error-banner">Ошибка: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Создать Rechnung (PDF)';
  }
}

function initRechnungView() {
  const contentEl = document.getElementById('rechnung-content');

  if (currentRole !== 'owner' && currentRole !== 'manager') {
    contentEl.innerHTML = '<div class="no-access">Раздел доступен только владельцу и менеджерам.</div>';
    return;
  }

  renderRechnungForm();
  const submitBar = document.getElementById('rechnung-submit-bar');
  submitBar.style.display = 'block';
  document.getElementById('rechnung-submit-btn').addEventListener('click', submitRechnung);
}
