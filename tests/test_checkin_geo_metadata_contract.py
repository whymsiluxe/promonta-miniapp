from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# 26.09 (checkin/execution router split): checkin_start/checkin_finish moved
# from backend/main.py into backend/routes/checkin.py -- same source-level
# contract, new location.
BACKEND_CHECKIN_ROUTES = ROOT / "backend" / "routes" / "checkin.py"


def _source() -> str:
    return BACKEND_CHECKIN_ROUTES.read_text(encoding="utf-8")


def test_checkin_start_accepts_and_persists_geo_metadata():
    src = _source()
    start = src.index("async def checkin_start(")
    end = src.index("@router.post(\"/api/checkin/{session_id}/pause\")", start)
    body = src[start:end]

    assert "accuracy: str = Form('')" in body
    assert "geo_timestamp: str = Form('')" in body
    assert "occurred_at: str = Form('')" in body
    assert "accuracy_clean = accuracy.strip()[:50] if isinstance(accuracy, str) else ''" in body
    assert "geo_timestamp_clean = geo_timestamp.strip()[:50] if isinstance(geo_timestamp, str) else ''" in body
    assert "start_event_at = _parse_checkin_occurred_at(occurred_at_clean, 'occurred_at', start_received_at)" in body
    assert '"start_at": start_event_at' in body
    assert '"start_received_at": start_received_at' in body
    assert '"start_accuracy": accuracy_clean or None' in body
    assert '"start_geo_timestamp": geo_timestamp_clean or None' in body


def test_checkin_finish_accepts_and_persists_geo_metadata():
    src = _source()
    start = src.index("async def checkin_finish(")
    end = src.index("@router.get(\"/api/checkin/stundenzettel\")", start)
    body = src[start:end]

    assert "accuracy: str = Form('')" in body
    assert "geo_timestamp: str = Form('')" in body
    assert "occurred_at: str = Form('')" in body
    assert "accuracy_clean = accuracy.strip()[:50] if isinstance(accuracy, str) else ''" in body
    assert "geo_timestamp_clean = geo_timestamp.strip()[:50] if isinstance(geo_timestamp, str) else ''" in body
    assert "finish_event_at = _parse_checkin_occurred_at(occurred_at_clean, 'occurred_at', finish_received_at)" in body
    assert "session['finish_at'] = finish_event_at" in body
    assert "session['finish_received_at'] = finish_received_at" in body
    assert "session['finish_accuracy'] = accuracy_clean or None" in body
    assert "session['finish_geo_timestamp'] = geo_timestamp_clean or None" in body
