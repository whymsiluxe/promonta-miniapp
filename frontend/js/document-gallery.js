// Global object-document gallery for the Documents view.
// Reuses the existing per-object document endpoints and authenticated viewer.

let _docGalleryObjects = [];
let _docGalleryDocs = [];
let _docGalleryFilter = 'all';
let _docGalleryThumbUrls = [];

function _docGalleryObjectId(obj) {
  return obj?.['ID объекта'] || obj?.['Объект'] || '';
}

function _docGalleryWhen(ts) {
  if (!ts) return '';
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function _docGalleryKind(contentType) {
  if ((contentType || '').startsWith('image/')) return 'Фото';
  if (contentType === 'application/pdf') return 'PDF';
  return 'Файл';
}

function _docGalleryRevokeThumbs() {
  _docGalleryThumbUrls.forEach(url => {
    try { URL.revokeObjectURL(url); } catch (e) {}
  });
  _docGalleryThumbUrls = [];
}

function _docGalleryFilteredDocs() {
  if (_docGalleryFilter === 'all') return _docGalleryDocs;
  return _docGalleryDocs.filter(doc => doc.object_id === _docGalleryFilter);
}

function _renderDocumentGalleryFilters() {
  const filters = document.getElementById('document-gallery-filters');
  if (!filters) return;
  const counts = new Map();
  _docGalleryDocs.forEach(doc => counts.set(doc.object_id, (counts.get(doc.object_id) || 0) + 1));
  const objectChips = _docGalleryObjects
    .filter(obj => counts.has(_docGalleryObjectId(obj)))
    .map(obj => {
      const id = _docGalleryObjectId(obj);
      return `<button type="button" class="doc-gallery-filter ios-chip${_docGalleryFilter === id ? ' active' : ''}" data-doc-gallery-filter="${esc(id)}">
        <span>${esc(obj['Объект'] || id)}</span><b>${counts.get(id) || 0}</b>
      </button>`;
    }).join('');
  filters.innerHTML = `
    <button type="button" class="doc-gallery-filter ios-chip${_docGalleryFilter === 'all' ? ' active' : ''}" data-doc-gallery-filter="all">
      <span>Все</span><b>${_docGalleryDocs.length}</b>
    </button>
    ${objectChips || '<span class="doc-gallery-filter-empty">Нет объектов с документами</span>'}
  `;
}

function _documentGalleryIcon(doc) {
  if ((doc.content_type || '').startsWith('image/')) {
    return `<div class="doc-gallery-thumb doc-gallery-thumb-image" data-doc-gallery-thumb-path="/api/objects/${encodeURIComponent(doc.object_id)}/documents/${encodeURIComponent(doc.file)}/file">
      <span>Фото</span>
    </div>`;
  }
  return `<div class="doc-gallery-thumb doc-gallery-thumb-pdf">
    <svg viewBox="0 0 24 24" width="30" height="30" fill="none" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M14 2v6h6" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
    <span>PDF</span>
  </div>`;
}

function _documentGalleryCard(doc) {
  const canDelete = currentRole === 'owner';
  return `
    <article class="doc-gallery-card" data-doc-gallery-id="${esc(doc.id)}" data-doc-gallery-object="${esc(doc.object_id)}">
      ${_documentGalleryIcon(doc)}
      <div class="doc-gallery-card-body">
        <div class="doc-gallery-name">${esc(doc.name || doc.file || 'Документ')}</div>
        <div class="doc-gallery-meta">${esc(doc.object_name || doc.object_id)} · ${esc(_docGalleryKind(doc.content_type))}${_docGalleryWhen(doc.uploaded_at) ? ' · ' + esc(_docGalleryWhen(doc.uploaded_at)) : ''}</div>
      </div>
      <div class="doc-gallery-actions">
        <button type="button" class="doc-gallery-action ios-action-button" data-doc-gallery-preview="${esc(doc.id)}">Открыть</button>
        <button type="button" class="doc-gallery-icon-action ios-icon-button" data-doc-gallery-object-open="${esc(doc.object_id)}" aria-label="Объект" title="Объект">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M4 21V7l8-4 8 4v14M9 21v-8h6v8" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
        </button>
        ${canDelete ? `<button type="button" class="doc-gallery-icon-action doc-gallery-delete ios-icon-button" data-doc-gallery-delete="${esc(doc.id)}" aria-label="Удалить" title="Удалить">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>` : ''}
      </div>
    </article>`;
}

async function _hydrateDocumentGalleryThumbs() {
  const thumbs = Array.from(document.querySelectorAll('[data-doc-gallery-thumb-path]'));
  await Promise.all(thumbs.map(async el => {
    try {
      const url = await authImageUrl(el.dataset.docGalleryThumbPath);
      _docGalleryThumbUrls.push(url);
      el.style.backgroundImage = `url("${url}")`;
      el.classList.add('loaded');
      el.innerHTML = '';
    } catch (e) {
      el.classList.add('failed');
    }
  }));
}

function _renderDocumentGallery() {
  _renderDocumentGalleryFilters();
  const grid = document.getElementById('document-gallery-grid');
  if (!grid) return;
  const docs = _docGalleryFilteredDocs();
  if (!docs.length) {
    grid.innerHTML = `<div class="doc-gallery-empty ios-empty-state">
      <strong>${_docGalleryDocs.length ? 'В этом объекте документов нет' : 'Документы ещё не прикреплены'}</strong>
      <span>Файлы, загруженные в объекте, появятся здесь автоматически.</span>
    </div>`;
    return;
  }
  grid.innerHTML = docs.map(_documentGalleryCard).join('');
  _attachDocumentGalleryCardHandlers(grid);
  _hydrateDocumentGalleryThumbs();
}

function _attachDocumentGalleryCardHandlers(grid) {
  grid.querySelectorAll('[data-doc-gallery-preview]').forEach(btn => {
    btn.addEventListener('click', () => {
      const doc = _docGalleryDocs.find(d => d.id === btn.dataset.docGalleryPreview);
      if (!doc) return;
      if (typeof _openObjInfoDocViewer === 'function') {
        _openObjInfoDocViewer(doc.object_id, doc.file, doc.content_type, doc.name);
      }
    });
  });
  grid.querySelectorAll('[data-doc-gallery-object-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const obj = _docGalleryObjects.find(o => _docGalleryObjectId(o) === btn.dataset.docGalleryObjectOpen);
      if (typeof openObjectDetail === 'function') {
        openObjectDetail(btn.dataset.docGalleryObjectOpen, obj?.['Объект'] || btn.dataset.docGalleryObjectOpen, 'info', obj?.['Статус'] || '');
      }
    });
  });
  grid.querySelectorAll('[data-doc-gallery-delete]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const doc = _docGalleryDocs.find(d => d.id === btn.dataset.docGalleryDelete);
      if (!doc || !confirm(`Удалить документ «${doc.name || doc.file}»?`)) return;
      btn.disabled = true;
      try {
        await api(`/api/objects/${encodeURIComponent(doc.object_id)}/documents/${encodeURIComponent(doc.id)}`, { method: 'DELETE' });
        hapticImpact('light');
        await loadDocumentGallery();
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
        btn.disabled = false;
      }
    });
  });
}

async function loadDocumentGallery() {
  const grid = document.getElementById('document-gallery-grid');
  if (!grid) return;
  _docGalleryRevokeThumbs();
  grid.innerHTML = '<div class="doc-gallery-loading">Загрузка документов...</div>';
  try {
    const objectsData = await api('/api/objects');
    _docGalleryObjects = (objectsData.objects || []).filter(obj => _docGalleryObjectId(obj));
    const batches = await Promise.all(_docGalleryObjects.map(async obj => {
      const objectId = _docGalleryObjectId(obj);
      try {
        const data = await api(`/api/objects/${encodeURIComponent(objectId)}/documents`);
        return (data.documents || []).map(doc => ({
          ...doc,
          object_id: objectId,
          object_name: obj['Объект'] || objectId,
        }));
      } catch (e) {
        return [];
      }
    }));
    _docGalleryDocs = batches.flat().sort((a, b) => (b.uploaded_at || 0) - (a.uploaded_at || 0));
    if (_docGalleryFilter !== 'all' && !_docGalleryDocs.some(doc => doc.object_id === _docGalleryFilter)) {
      _docGalleryFilter = 'all';
    }
    _renderDocumentGallery();
  } catch (e) {
    grid.innerHTML = `<div class="doc-gallery-empty ios-empty-state"><strong>Документы недоступны</strong><span>${esc(e.message)}</span><button type="button" class="ios-action-button" id="document-gallery-retry">Повторить</button></div>`;
    document.getElementById('document-gallery-retry')?.addEventListener('click', loadDocumentGallery);
  }
}

function initDocumentGallery() {
  const root = document.getElementById('document-gallery');
  if (!root) return;
  if (!root.dataset.wired) {
    root.dataset.wired = '1';
    document.getElementById('document-gallery-refresh')?.addEventListener('click', () => loadDocumentGallery());
    document.getElementById('document-gallery-filters')?.addEventListener('click', e => {
      const chip = e.target.closest('[data-doc-gallery-filter]');
      if (!chip) return;
      _docGalleryFilter = chip.dataset.docGalleryFilter;
      hapticImpact('light');
      _renderDocumentGallery();
    });
  }
  loadDocumentGallery();
}
