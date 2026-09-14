from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_MAIN = ROOT / "backend" / "main.py"


def _source() -> str:
    return BACKEND_MAIN.read_text(encoding="utf-8")


def test_checkin_start_accepts_and_persists_geo_metadata():
    src = _source()
    start = src.index("async def checkin_start(")
    end = src.index("@app.post(\"/api/checkin/{session_id}/pause\")", start)
    body = src[start:end]

    assert "accuracy: str = Form('')" in body
    assert "geo_timestamp: str = Form('')" in body
    assert "accuracy_clean = accuracy.strip()[:50] if isinstance(accuracy, str) else ''" in body
    assert "geo_timestamp_clean = geo_timestamp.strip()[:50] if isinstance(geo_timestamp, str) else ''" in body
    assert '"start_accuracy": accuracy_clean or None' in body
    assert '"start_geo_timestamp": geo_timestamp_clean or None' in body


def test_checkin_finish_accepts_and_persists_geo_metadata():
    src = _source()
    start = src.index("async def checkin_finish(")
    end = src.index("@app.get(\"/api/workers/{target_user_id}/calendar\")", start)
    body = src[start:end]

    assert "accuracy: str = Form('')" in body
    assert "geo_timestamp: str = Form('')" in body
    assert "accuracy_clean = accuracy.strip()[:50] if isinstance(accuracy, str) else ''" in body
    assert "geo_timestamp_clean = geo_timestamp.strip()[:50] if isinstance(geo_timestamp, str) else ''" in body
    assert "session['finish_accuracy'] = accuracy_clean or None" in body
    assert "session['finish_geo_timestamp'] = geo_timestamp_clean or None" in body
