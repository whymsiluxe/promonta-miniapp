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

// 21.09 (P0, owner review finding): only the LIVE pending records are
// resolved here now -- dead_letter records are looked up separately by
// _findDeadLetterShiftRecord() and consulted by resolveWorkerShiftState()
// only as a last resort, AFTER the server has had a chance to answer. Before
// this split, a dead_letter from a completely different, already-finished
// shift (e.g. yesterday's Finish that permanently failed to sync) made this
// function return SYNC_ERROR unconditionally, before the server was ever
// asked -- so a worker with a perfectly normal ACTIVE shift on the server
// today would see "⚠️ Ошибка синхронизации" and have Start/Finish disabled,
// because of an unrelated stale error from a previous shift.
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

  return null;
}

// Separated from the pending check above -- a dead_letter record is a
// RECOVERY concern (needs a manual retry/dismiss), not proof that no shift
// can currently be resolved. Called only when neither a live pending record
// nor the server itself could answer.
async function _findDeadLetterShiftRecord(objectId) {
  if (typeof promontaOutboxList !== 'function') return null;
  const [finishRecords, startRecords] = await Promise.all([
    promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_FINISH).catch(() => []),
    promontaOutboxList(WORKER_SHIFT_OUTBOX_KIND_START).catch(() => []),
  ]);
  const filterByObject = record => !objectId || String(record.objectId) === String(objectId);

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
  // 21.09 (P0, owner review finding): live pending records only -- see
  // _resolveWorkerShiftOutboxState's comment. A dead_letter no longer short-
  // circuits this before the server is even asked.
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

  // 21.09 (P0, owner review finding round 3): when the server itself is
  // UNREACHABLE (serverError set), a valid local ACTIVE/PAUSED session must
  // be trusted BEFORE an unrelated dead_letter gets a chance to override it.
  // Without this ordering: worker is genuinely mid-shift on OBJECT-B
  // (localStorage has the real session), an old dead_letter from OBJECT-A's
  // unrelated failed Finish is still sitting in the outbox, and connectivity
  // drops -- the worker would see "⚠️ Ошибка синхронизации" and lose
  // Start/Finish on a shift that is, locally, perfectly fine. This is the
  // same class of bug the original P0 fixed (dead_letter must never override
  // a real session it doesn't belong to), just for the offline branch this
  // function's OTHER branch (server reachable) doesn't go through.
  if (serverError) {
    const localState = _resolveWorkerShiftLocalState(objectId, serverError);
    if (workerShiftStateHasActiveSession(localState)) {
      const deadLetterWhileOffline = await _findDeadLetterShiftRecord(objectId).catch(() => null);
      // Surfaced as a non-blocking warning alongside the real local state,
      // not as a state override -- the worker's actual ACTIVE/PAUSED shift
      // must still be usable (Pause/Finish enabled) while a stale recovery
      // notice is shown separately if the UI chooses to render it.
      return deadLetterWhileOffline ? { ...localState, syncWarning: deadLetterWhileOffline } : localState;
    }
  }

  // 21.09 (P0, owner review finding): dead_letter is consulted here when the
  // server WAS reachable and confirmed there is no open/finished session for
  // this object, or when the server failed AND there is no valid local
  // active session to protect -- a stale send failure is relevant recovery
  // information in both of those cases, not a false block on an otherwise-
  // normal session the server (or localStorage) would already have reported.
  const deadLetter = await _findDeadLetterShiftRecord(objectId).catch(() => null);
  if (deadLetter) return deadLetter;

  return _resolveWorkerShiftLocalState(objectId, serverError);
}

function workerShiftStateHasActiveSession(shiftState) {
  return shiftState?.state === WORKER_SHIFT_STATE.ACTIVE || shiftState?.state === WORKER_SHIFT_STATE.PAUSED;
}

function workerShiftStateIsPending(shiftState) {
  return shiftState?.state === WORKER_SHIFT_STATE.START_PENDING_SYNC
    || shiftState?.state === WORKER_SHIFT_STATE.FINISH_PENDING_SYNC;
}

