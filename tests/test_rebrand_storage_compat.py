"""Grandmont Group rebrand (26.09): browser storage keys were renamed from the
pre-rebrand 'promonta' names. Each renamed key must keep a one-time legacy
fallback, otherwise the deploy would silently:
  - log out every open session (sessionStorage session token),
  - orphan queued-but-unsent check-in/finish evidence (IndexedDB outbox),
  - drop the offline plan cache and the user's custom object order.
These are static contract checks (same style as the other *_frontend_contract
tests); the migration behaviour itself was verified against fake-indexeddb when
the rename was made.
"""
from pathlib import Path

FRONTEND_JS = Path(__file__).resolve().parents[1] / "frontend" / "js"


def _read(name):
    return (FRONTEND_JS / name).read_text(encoding="utf-8")


def test_session_token_key_renamed_with_legacy_fallback():
    js = _read("shared.js")
    assert "const SESSION_TOKEN_KEY = 'grandmont_group_session_token';" in js
    assert "const LEGACY_SESSION_TOKEN_KEY = 'promonta_session_token';" in js
    assert "window.sessionStorage.getItem(LEGACY_SESSION_TOKEN_KEY)" in js
    assert "window.sessionStorage.setItem(SESSION_TOKEN_KEY, legacyToken)" in js
    # logout must clear both, or a stale legacy token would be re-migrated next start
    clear_body = js[js.index("function _clearSessionToken()"):]
    clear_body = clear_body[:clear_body.index("\n}\n")]
    assert "removeItem(LEGACY_SESSION_TOKEN_KEY)" in clear_body


def test_outbox_db_renamed_with_legacy_migration():
    js = _read("shared.js")
    assert "const APP_OUTBOX_DB = 'grandmont-group-offline-outbox';" in js
    assert "const LEGACY_APP_OUTBOX_DB = 'promonta-offline-outbox';" in js
    assert "_appMigrateLegacyOutbox(db)" in js
    # add(), never put(): a legacy copy must not clobber a newer record
    migrate = js[js.index("async function _appMigrateLegacyOutbox("):js.index("function _appOpenOutboxDb()")]
    assert "store.add(r)" in migrate
    assert "store.put(" not in migrate
    assert "indexedDB.deleteDatabase(LEGACY_APP_OUTBOX_DB)" in migrate


def test_today_plan_cache_renamed_with_legacy_fallback():
    js = _read("today-plan.js")
    assert "const _TP_DB_NAME = 'grandmont-group-today-plan';" in js
    assert "const _TP_LEGACY_DB_NAME = 'promonta-today-plan';" in js
    assert "_tpLegacyDbLoadAndMigrate()" in js


def test_objects_order_key_renamed_with_legacy_fallback():
    js = _read("objects.js")
    assert "const ORDER_KEY = 'grandmont_group_objects_order';" in js
    assert "const LEGACY_ORDER_KEY = 'promonta_objects_order';" in js
    assert "localStorage.getItem(LEGACY_ORDER_KEY)" in js
