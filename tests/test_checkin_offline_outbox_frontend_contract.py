from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
FINISH_WIZARD_JS = ROOT / "frontend" / "js" / "finish-wizard.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_indexeddb_outbox_persists_binary_records():
    src = _source(SHARED_JS)

    assert "const PROMONTA_OUTBOX_DB = 'promonta-offline-outbox';" in src
    assert "const PROMONTA_OUTBOX_STORE = 'records';" in src
    assert "indexedDB.open(PROMONTA_OUTBOX_DB, PROMONTA_OUTBOX_VERSION)" in src
    assert "db.createObjectStore(PROMONTA_OUTBOX_STORE, { keyPath: 'id' })" in src
    assert "store.createIndex('kind', 'kind', { unique: false })" in src
    assert "async function promontaOutboxPut(record)" in src
    assert "async function promontaOutboxPatch(id, updates)" in src
    assert "async function promontaOutboxDelete(id)" in src
    assert "async function promontaOutboxList(kind)" in src


def test_start_checkin_queues_files_geo_fields_and_idempotency_key():
    src = _source(CHECKIN_JS)

    assert "const CHECKIN_OUTBOX_KIND_START = 'checkin-start';" in src
    assert "function _checkinStartOutboxId(idempotencyKey)" in src
    assert "async function _queueCheckinStartOutbox(files, extraFields, idempotencyKey)" in src
    assert "files: Array.from(files)" in src
    assert "extraFields: { ...(extraFields || {}) }" in src
    assert "geo," in src
    assert "idempotencyKey," in src
    assert "await _queueCheckinStartOutbox(_checkinPreviewFiles, startFieldsOrNull, _checkinIdempotencyKey)" in src
    assert "Старт сохранён в офлайн-очередь" in src


def test_start_checkin_retries_outbox_on_reconnect():
    src = _source(CHECKIN_JS)

    assert "async function _retryCheckinOutbox()" in src
    assert "promontaOutboxList(CHECKIN_OUTBOX_KIND_START)" in src
    assert "await _sendCheckinStartOutboxRecord(record)" in src
    assert "await promontaOutboxPatch(record.id, {" in src
    assert "await promontaOutboxDelete(record.id)" in src
    assert "window.addEventListener('online', _retryCheckinOutbox)" in src
    assert "setTimeout(_retryCheckinOutbox, 1500)" in src


def test_finish_wizard_queues_finish_payload_and_files():
    src = _source(FINISH_WIZARD_JS)

    assert "const CHECKIN_OUTBOX_KIND_FINISH = 'checkin-finish';" in src
    assert "function _fwFinishOutboxId(idempotencyKey)" in src
    assert "function _fwBuildFinishOutboxRecord()" in src
    assert "files: Array.from(_fwPhotos)" in src
    assert "fields.daily_plan_report = JSON.stringify" in src
    assert "idempotencyKey: _fwIdempotencyKey" in src
    assert "async function _fwQueueFinishOutbox(record)" in src
    assert "await _fwQueueFinishOutbox(finishRecord)" in src
    assert "Финиш сохранён в офлайн-очередь" in src


def test_finish_wizard_replays_finish_outbox_with_same_idempotency_key():
    src = _source(FINISH_WIZARD_JS)

    assert "async function _retryFinishOutboxRecords()" in src
    assert "promontaOutboxList(CHECKIN_OUTBOX_KIND_FINISH)" in src
    assert "async function _fwSendFinishOutboxRecord(record, { fromOutbox = false } = {})" in src
    assert "'Idempotency-Key': record.idempotencyKey" in src
    assert "body: _fwAppendFinishRecordFormData(record)" in src
    assert "if (fromOutbox) await promontaOutboxDelete(record.id)" in src
    assert "window.addEventListener('online', _retryFinishOutboxRecords)" in src
    assert "setTimeout(_retryFinishOutboxRecords, 1800)" in src
