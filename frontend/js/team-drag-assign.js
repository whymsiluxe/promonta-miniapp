// P2 continuation: drag a free worker onto an object and reuse the full Assignment Sheet.
//
// 17.09 (audit finding, P1): decorateDropZones() used to look objects up by their
// DISPLAY NAME (Map<label, obj>, first match wins on a collision) instead of using
// the real object_id already present in the row data -- two objects sharing a
// display name (duplicate address, renamed object, etc.) would silently make every
// drag-drop assignment land on whichever object happened to load first. Fixed by
// reading object_id directly from a data-object-id attribute that home.js now
// writes into both block templates (.wo-object-block / .wo-plan-object-block) at
// render time -- no more reconstructing identity from rendered text, no more API
// call or cache needed here at all.
(function () {
  let activeDrag = null;
  let enhanceTimer = null;

  const HANDLE_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M8 5h.01M8 12h.01M8 19h.01M16 5h.01M16 12h.01M16 19h.01"/></svg>';

  function scheduleEnhance() {
    clearTimeout(enhanceTimer);
    enhanceTimer = setTimeout(enhanceTeamDragAssign, 80);
  }

  function workerNameFromRow(row) {
    return row.querySelector('.wo-worker-name')?.textContent?.trim() || row.dataset.name || '';
  }

  function objectNameFromBlock(block) {
    return block.querySelector('.wo-object-name, .wo-plan-object-name')?.textContent?.trim() || '';
  }

  function decorateDropZones() {
    document.querySelectorAll('#view-working-objects .wo-object-block[data-object-id], #view-working-objects .wo-plan-object-block[data-object-id]').forEach(block => {
      const objectId = block.dataset.objectId;
      if (!objectId) return;
      block.classList.add('wo-object-dropzone');
      block.dataset.dragObjectId = objectId;
      block.dataset.dragObjectName = objectNameFromBlock(block);
    });
  }

  function decorateWorkers() {
    document.querySelectorAll('#wo-anchor-without-object .wo-worker-row[data-uid]').forEach(row => {
      if (row.dataset.dragAssignReady === '1') return;
      row.dataset.dragAssignReady = '1';
      row.dataset.dragUserId = row.dataset.uid;
      row.dataset.dragUserName = workerNameFromRow(row);
      row.classList.add('wo-drag-worker-row');
      row.insertAdjacentHTML('afterbegin', `<button type="button" class="wo-drag-handle" aria-label="Перетащить к объекту">${HANDLE_SVG}</button>`);
      row.querySelector('.wo-drag-handle')?.addEventListener('pointerdown', event => startDrag(event, row));
    });
  }

  function enhanceTeamDragAssign() {
    const root = document.getElementById('view-working-objects');
    if (!root || root.style.display === 'none') return;
    decorateWorkers();
    decorateDropZones();
  }

  function makeGhost(row) {
    const ghost = document.createElement('div');
    ghost.className = 'wo-drag-ghost';
    ghost.textContent = row.dataset.dragUserName || workerNameFromRow(row) || 'Работник';
    document.body.appendChild(ghost);
    return ghost;
  }

  function setGhostPosition(event) {
    if (!activeDrag?.ghost) return;
    activeDrag.ghost.style.transform = `translate3d(${event.clientX + 12}px, ${event.clientY + 12}px, 0)`;
  }

  function currentDropZone(event) {
    const elements = document.elementsFromPoint(event.clientX, event.clientY);
    return elements.find(el => el.classList?.contains('wo-object-dropzone') && el.dataset.dragObjectId) || null;
  }

  function updateDropTarget(target) {
    document.querySelectorAll('.wo-object-dropzone.wo-drop-active').forEach(el => {
      if (el !== target) el.classList.remove('wo-drop-active');
    });
    if (target) target.classList.add('wo-drop-active');
  }

  function startDrag(event, row) {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    activeDrag = {
      pointerId: event.pointerId,
      row,
      userId: row.dataset.dragUserId,
      userName: row.dataset.dragUserName || workerNameFromRow(row),
      ghost: makeGhost(row),
    };
    row.classList.add('wo-dragging');
    row.querySelector('.wo-drag-handle')?.setPointerCapture?.(event.pointerId);
    setGhostPosition(event);
    document.addEventListener('pointermove', moveDrag, { passive: false });
    document.addEventListener('pointerup', finishDrag, { once: true });
    document.addEventListener('pointercancel', cancelDrag, { once: true });
  }

  function moveDrag(event) {
    if (!activeDrag || event.pointerId !== activeDrag.pointerId) return;
    event.preventDefault();
    setGhostPosition(event);
    updateDropTarget(currentDropZone(event));
  }

  function cleanupDrag() {
    document.removeEventListener('pointermove', moveDrag);
    document.querySelectorAll('.wo-object-dropzone.wo-drop-active').forEach(el => el.classList.remove('wo-drop-active'));
    activeDrag?.row?.classList.remove('wo-dragging');
    activeDrag?.ghost?.remove();
    activeDrag = null;
  }

  function finishDrag(event) {
    if (!activeDrag || event.pointerId !== activeDrag.pointerId) return;
    const drag = activeDrag;
    const target = currentDropZone(event);
    cleanupDrag();
    if (!target) return;
    if (typeof openAssignmentSheet !== 'function') {
      showToast('Форма назначения недоступна', 'error');
      return;
    }
    openAssignmentSheet({
      userId: drag.userId,
      userName: drag.userName,
      objectId: target.dataset.dragObjectId,
      objectName: target.dataset.dragObjectName,
    });
  }

  function cancelDrag(event) {
    if (!activeDrag || event.pointerId !== activeDrag.pointerId) return;
    cleanupDrag();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('view-working-objects');
    if (root) {
      new MutationObserver(scheduleEnhance).observe(root, { childList: true, subtree: true });
    }
    scheduleEnhance();
  });
  window.enhanceTeamDragAssign = enhanceTeamDragAssign;
})();
