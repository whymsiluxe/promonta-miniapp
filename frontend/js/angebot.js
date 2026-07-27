// Таб "Angebot": форма создания коммерческого предложения (PDF).

let angebotPositions = [{ titel: '', beschreibung: '', menge: 1, einheit: 'm²', preis: 0 }];

function calcAngebotTotals() {
  const mwstSatz = parseFloat(document.getElementById('mwstSatz')?.value) || 19;
  const anzahlungPct = parseFloat(document.getElementById('anzahlungPct')?.value) || 40;
  const netto = angebotPositions.reduce((s, p) => s + (p.menge * p.preis || 0), 0);
  const mwst = netto * mwstSatz / 100;
  const brutto = netto + mwst;
  const anzahlung = brutto * anzahlungPct / 100;
  return { netto, mwst, mwstSatz, brutto, anzahlung, rest: brutto - anzahlung };
}

function fmtEuro(v) {
  return v.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
}

function renderAngebotPositions() {
  return angebotPositions.map((p, i) => `
    <div class="position-card" data-idx="${i}">
      ${angebotPositions.length > 1 ? `<button class="remove-pos" data-remove="${i}">×</button>` : ''}
      <div class="field">
        <label>Название работы</label>
        <input type="text" data-field="titel" data-idx="${i}" value="${esc(p.titel)}" placeholder="напр. Trockenbau Wandverkleidung">
      </div>
      <div class="field">
        <label>Описание (опционально)</label>
        <input type="text" data-field="beschreibung" data-idx="${i}" value="${esc(p.beschreibung)}" placeholder="Детали работы">
      </div>
      <div class="row-2">
        <div class="field">
          <label>Кол-во</label>
          <input type="number" step="0.01" data-field="menge" data-idx="${i}" value="${p.menge}">
        </div>
        <div class="field">
          <label>Ед.изм.</label>
          <select data-field="einheit" data-idx="${i}">
            ${['m²', 'Stk', 'Lfm', 'h', 'pauschal'].map(u => `<option value="${u}" ${p.einheit === u ? 'selected' : ''}>${u}</option>`).join('')}
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

function renderAngebotTotals() {
  const t = calcAngebotTotals();
  return `
    <div class="totals">
      <div class="row"><span>Summe netto</span><span>${fmtEuro(t.netto)}</span></div>
      <div class="row"><span>MwSt ${t.mwstSatz}%</span><span>${fmtEuro(t.mwst)}</span></div>
      <div class="row grand"><span>Gesamt brutto</span><span>${fmtEuro(t.brutto)}</span></div>
      <div class="row"><span>Anzahlung</span><span>${fmtEuro(t.anzahlung)}</span></div>
      <div class="row"><span>Restzahlung</span><span>${fmtEuro(t.rest)}</span></div>
    </div>`;
}

function renderAngebotForm() {
  document.getElementById('angebot-content').innerHTML = `
    <div class="section">
      <div class="section-title">Kunde</div>
      <div class="field">
        <label>Тип клиента</label>
        <select id="kundeTyp">
          <option value="privat">Privatperson</option>
          <option value="firma">Firma</option>
        </select>
      </div>
      <div id="kunde-privat-fields" class="row-2">
        <div class="field" style="flex:0 0 90px">
          <label>Anrede</label>
          <select id="anrede">
            <option value="Herr">Herr</option>
            <option value="Frau">Frau</option>
          </select>
        </div>
        <div class="field">
          <label>Имя</label>
          <input type="text" id="kundeName" placeholder="Max Mustermann">
        </div>
      </div>
      <div id="kunde-firma-fields" style="display:none">
        <div class="field">
          <label>Название фирмы</label>
          <input type="text" id="firmaName" placeholder="Hans Fries GmbH">
        </div>
        <div class="field">
          <label>Контактное лицо (опционально)</label>
          <input type="text" id="firmaKontakt" placeholder="Hr. Fries">
        </div>
        <div class="field">
          <label>Ust-ID клиента (опционально)</label>
          <input type="text" id="firmaUstId" placeholder="DE123456789">
        </div>
      </div>
      <div class="field">
        <label>Адрес клиента</label>
        <input type="text" id="kundeAdresse" placeholder="Straße, PLZ Ort">
      </div>
      <div class="field">
        <label>Email</label>
        <input type="email" id="kundeEmail" placeholder="email@beispiel.de">
      </div>
    </div>

    <div class="section">
      <div class="section-title">Objekt</div>
      <div class="field">
        <label>Адрес объекта</label>
        <input type="text" id="objektAdresse" placeholder="Если отличается от адреса клиента">
      </div>
    </div>

    <div class="section">
      <div class="section-title">Positionen</div>
      <div id="angebot-positions">${renderAngebotPositions()}</div>
      <button class="add-position-btn" id="add-position">+ Позиция</button>
    </div>

    <div class="section">
      <div class="section-title">Условия</div>
      <div class="row-2">
        <div class="field">
          <label>MwSt %</label>
          <input type="number" id="mwstSatz" value="19">
        </div>
        <div class="field">
          <label>Anzahlung %</label>
          <input type="number" id="anzahlungPct" value="40">
        </div>
        <div class="field">
          <label>Gültig, дней</label>
          <input type="number" id="gueltigTage" value="14">
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Итого</div>
      <div id="angebot-totals">${renderAngebotTotals()}</div>
    </div>

    <div id="angebot-error-container"></div>
  `;

  attachAngebotFormHandlers();
}

function attachAngebotFormHandlers() {
  document.querySelectorAll('#angebot-positions [data-field]').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      const field = e.target.dataset.field;
      let val = e.target.value;
      if (field === 'menge' || field === 'preis') val = parseFloat(val) || 0;
      angebotPositions[idx][field] = val;
      document.getElementById('angebot-positions').innerHTML = renderAngebotPositions();
      document.getElementById('angebot-totals').innerHTML = renderAngebotTotals();
      attachAngebotFormHandlers();
    });
  });

  document.querySelectorAll('#angebot-positions [data-remove]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      angebotPositions.splice(parseInt(e.target.dataset.remove, 10), 1);
      document.getElementById('angebot-positions').innerHTML = renderAngebotPositions();
      document.getElementById('angebot-totals').innerHTML = renderAngebotTotals();
      attachAngebotFormHandlers();
    });
  });

  document.getElementById('add-position').addEventListener('click', () => {
    angebotPositions.push({ titel: '', beschreibung: '', menge: 1, einheit: 'm²', preis: 0 });
    document.getElementById('angebot-positions').innerHTML = renderAngebotPositions();
    attachAngebotFormHandlers();
  });

  ['mwstSatz', 'anzahlungPct'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      document.getElementById('angebot-totals').innerHTML = renderAngebotTotals();
    });
  });

  document.getElementById('kundeTyp').addEventListener('change', (e) => {
    const isFirma = e.target.value === 'firma';
    document.getElementById('kunde-privat-fields').style.display = isFirma ? 'none' : 'flex';
    document.getElementById('kunde-firma-fields').style.display = isFirma ? 'block' : 'none';
  });
}

async function submitAngebot() {
  const errorContainer = document.getElementById('angebot-error-container');
  errorContainer.innerHTML = '';

  const isFirma = document.getElementById('kundeTyp').value === 'firma';
  let kunde;
  let displayName;

  if (isFirma) {
    const firmaName = document.getElementById('firmaName').value.trim();
    if (!firmaName) {
      errorContainer.innerHTML = '<div class="error-banner">Укажи название фирмы.</div>';
      return;
    }
    displayName = firmaName;
    kunde = {
      typ: 'firma',
      name: firmaName,
      kontakt: document.getElementById('firmaKontakt').value.trim(),
      ustId: document.getElementById('firmaUstId').value.trim(),
      adresse: document.getElementById('kundeAdresse').value.trim(),
      email: document.getElementById('kundeEmail').value.trim(),
    };
  } else {
    const kundeName = document.getElementById('kundeName').value.trim();
    if (!kundeName) {
      errorContainer.innerHTML = '<div class="error-banner">Укажи имя клиента.</div>';
      return;
    }
    displayName = kundeName;
    kunde = {
      typ: 'privat',
      anrede: document.getElementById('anrede').value,
      name: kundeName,
      adresse: document.getElementById('kundeAdresse').value.trim(),
      email: document.getElementById('kundeEmail').value.trim(),
    };
  }

  const validPositions = angebotPositions.filter(p => p.titel.trim() && p.menge > 0 && p.preis >= 0);
  if (!validPositions.length) {
    errorContainer.innerHTML = '<div class="error-banner">Добавь хотя бы одну позицию с названием, кол-вом и ценой.</div>';
    return;
  }

  const body = {
    kunde,
    objektAdresse: document.getElementById('objektAdresse').value.trim(),
    positionen: validPositions,
    mwstSatz: parseFloat(document.getElementById('mwstSatz').value) || 19,
    anzahlungPct: parseFloat(document.getElementById('anzahlungPct').value) || 40,
    gueltigTage: parseInt(document.getElementById('gueltigTage').value, 10) || 14,
  };

  // Фаза 7: подпись опциональна — openSignaturePad() резолвится в null если пропущена/пустая.
  if (typeof openSignaturePad === 'function') {
    const signature = await openSignaturePad(`Подпись — ${displayName}`);
    if (signature) body.signatureBase64 = signature;
  }

  const btn = document.getElementById('angebot-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Генерация PDF...';

  try {
    const res = await fetch(API_BASE + '/api/angebot', {
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
    a.download = `Angebot_${displayName.replace(/\s+/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    errorContainer.innerHTML = `<div class="error-banner">Ошибка: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Создать Angebot (PDF)';
  }
}

function initAngebotView() {
  const contentEl = document.getElementById('angebot-content');

  if (currentRole !== 'owner' && currentRole !== 'manager') {
    contentEl.innerHTML = '<div class="no-access">Раздел доступен только владельцу и менеджерам.</div>';
    return;
  }

  renderAngebotForm();
  const submitBar = document.getElementById('angebot-submit-bar');
  submitBar.style.display = 'block';
  document.getElementById('angebot-submit-btn').addEventListener('click', submitAngebot);
}
