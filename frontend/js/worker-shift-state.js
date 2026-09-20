// One resolver for every worker shift entry point: Today, FAB, Object and Stages.
// Outbox is checked first so an offline Start/Finish cannot be repeated while it
// is still waiting for sync.

const WORKER_SHIFT_STATE = {
  NO_SHIFT: 'NO_SHIFT',
  START_PENDING_SYNC: 'START_PENDING_SYNC',
  ACTIVE: 'ACTIVE',
  PAUSED: 'PAUSED',
  FINISH_PENDING_SYNC: 'FINISH_PENDING_SYNC',
  FINISHED: 'FINISHED',
  SYNC_ERROR: 'SYNC_ERROR',
};

const WORKER_SHIFT_OUTBOX_KIND_START = 'checkin-start';
const WORKER_SHIFT_OUTBOX_KIND_FINISH = 'checkin-finish';

function _workerShiftRecordTime(record) {
  return Number(record?.updatedAt || record?.createdAt || 0);
}

function _workerShiftNewest(records) {
  return (records || []).slice().sort((a, b) => _workerShiftRecordTime(b) - _workerShiftRecordTime(a))[0] || null;
}

function _workerShiftIsPendingOutboxRecord(record) {
  return record && record.state !== 'dead_letter';
}

async function _findPendingCheckinOutboxRecord(objectId, kind) {
  if (typeof promontaOutboxList !== 'function') return null;
  const kinds = kind ? [kind] : [WORKER_SHIFT_OUTBOX_KIND_FINISH, WORKER_SHIFT_OUTBOX_KIND_START];
  const all = [];
  for (const k of kinds) {
    const records = await promontaOutboxList(k).catch(() => []);
    all.push(...records);
  }
  return _workerShiftNewest(all.filter(record => {
    if (!_workerShiftIsPendingOutboxRecord(record)) return false;
    if (objectId && String(record.objectId) !== String(objectId)) return false;
    return true;
  }));
}

async function _resolveWorkerShiftOutboxState(objectId) {
  if (typeof promontaOutboxList !== 'function') return null;
  const [finishRecords, startRecords] = await Promise.all([
    promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_FINISH).catch(() => []),
    promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_START).catch(() => []),
  ]);

  const filterByObject = record => !objectId || String(record.objectId) === String(objectId);
  const finishPending = _workerShiftNewest(finishRecords.filter(record => filterByObject(record) && _workerShiftIsPendingOutboxRecord(record)));
  if (finishPending) {
    return {
      state: WORKER_SHIFT_STATE.FINISH_PENDING_SYNC,
      source: 'outbox',
      objectId: finishPending.objectId || null,
      sessionId: finishPending.sessionId || null,
      outboxRecord: finishPending,
    };
  }

  const startPending = _workerShiftNewest(startRecords.filter(record => filterByObject(record) && _workerShiftIsPendingOutboxRecord(record)));
  if (startPending) {
    return {
      state: WORKER_SHIFT_STATE.START_PENDING_SYNC,
      source: 'outbox',
      objectId: startPending.objectId || null,
      outboxRecord: startPending,
    };
  }

  const finishDead = _workerShiftNewest(finishRecords.filter(record => filterByObject(record) && record.state === 'dead_letter'));
  if (finishDead) {
    return {
      state: WORKER_SHIFT_STATE.SYNC_ERROR,
      pendingState: WORKER_SHIFT_STATE.FINISH_PENDING_SYNC,
      source: 'outbox',
      objectId: finishDead.objectId || null,
      sessionId: finishDead.sessionId || null,
      outboxRecord: finishDead,
      error: finishDead.lastError || '',
    };
  }

  const startDead = _workerShiftNewest(startRecords.filter(record => filterByObject(record) && record.state === 'dead_letter'));
  if (startDead) {
    return {
      state: WORKER_SHIFT_STATE.SYNC_ERROR,
      pendingState: WORKER_SHIFT_STATE.START_PENDING_SYNC,
      source: 'outbox',
      objectId: startDead.objectId || null,
      outboxRecord: startDead,
      error: startDead.lastError || '',
    };
  }

  return null;
}

function _workerShiftSessionStateFromServer(openSession) {
  return openSession.pause_started_at
    ? WORKER_SHIFT_STATE.PAUSED
    : WORKER_SHIFT_STATE.ACTIVE;
}

function _workerShiftApplyServerSession(openSession) {
  if (!openSession?.object_id || typeof _setActiveCheckinSession !== 'function') return;
  _setActiveCheckinSession(openSession.object_id, {
    id: openSession.id,
    finished: false,
    startAt: openSession.start_at || null,
    pauseStartedAt: openSession.pause_started_at || null,
    pauseAccumulatedSeconds: openSession.pause_accumulated_seconds || 0,
    startAccuracy: openSession.start_accuracy != null ? Number(openSession.start_accuracy) : null,
  });
}

function _resolveWorkerShiftLocalState(objectId, serverError) {
  const localSessions = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key || !key.startsWith('checkin_session_')) continue;
    try {
      const session = JSON.parse(localStorage.getItem(key));
      const localObjectId = key.replace('checkin_session_', '');
      if (objectId && String(localObjectId) !== String(objectId)) continue;
      localSessions.push({ ...session, objectId: localObjectId });
    } catch (e) {}
  }

  const active = _workerShiftNewest(localSessions.filter(session => session && !session.finished));
  if (active) {
    return {
      state: active.pauseStartedAt ? WORKER_SHIFT_STATE.PAUSED : WORKER_SHIFT_STATE.ACTIVE,
      source: 'localStorage',
      objectId: active.objectId,
      session: active,
      serverError,
    };
  }

  const finished = _workerShiftNewest(localSessions.filter(session => session && session.finished));
  if (finished && objectId) {
    return {
      state: WORKER_SHIFT_STATE.FINISHED,
      source: 'localStorage',
      objectId: finished.objectId,
      session: finished,
      serverError,
    };
  }

  return {
    state: WORKER_SHIFT_STATE.NO_SHIFT,
    source: serverError ? 'server-error' : 'server',
    objectId: objectId || null,
    serverError,
  };
}

async function resolveWorkerShiftState(options = {}) {
  const objectId = options.objectId || null;
  const outboxState = await _resolveWorkerShiftOutboxState(objectId).catch(() => null);
  if (outboxState) return outboxState;

  let serverError = null;
  try {
    const path = objectId ? `/api/checkin?object_id=${encodeURIComponent(objectId)}` : '/api/checkin';
    const data = await api(path);
    const sessions = data.sessions || [];
    const openSession = sessions.find(s => s.finish_at === null || s.finish_at === undefined);
    if (openSession) {
      _workerShiftApplyServerSession(openSession);
      return {
        state: _workerShiftSessionStateFromServer(openSession),
        source: 'server',
        objectId: openSession.object_id,
        sessionId: openSession.id,
        session: openSession,
      };
    }

    if (objectId && sessions.length) {
      const latest = sessions[sessions.length - 1];
      if (typeof _setActiveCheckinSession === 'function') {
        _setActiveCheckinSession(objectId, { id: latest.id, finished: true });
      }
      return {
        state: WORKER_SHIFT_STATE.FINISHED,
        source: 'server',
        objectId,
        sessionId: latest.id,
        session: latest,
      };
    }
  } catch (e) {
    serverError = e;
  }

  return _resolveWorkerShiftLocalState(objectId, serverError);
}

function workerShiftStateHasActiveSession(shiftState) {
  return shiftState?.state === WORKER_SHIFT_STATE.ACTIVE || shiftState?.state === WORKER_SHIFT_STATE.PAUSED;
}

function workerShiftStateIsPending(shiftState) {
  return shiftState?.state === WORKER_SHIFT_STATE.START_PENDING_SYNC
    || shiftState?.state === WORKER_SHIFT_STATE.FINISH_PENDING_SYNC;
}

