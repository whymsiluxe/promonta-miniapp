"""Business-timezone (Europe/Berlin) leaf helper — Phase A extraction from main.py.

Only business_now() lives here: it's the one true leaf with zero main.py coupling.
business_today()/business_today_str()/_today_berlin_str() stay in main.py because
they call business_now() by module-local name, and tests monkeypatch
`patch.object(backend, 'business_now', ...)` — moving those wrappers here too
would make them resolve core.time's own business_now instead of the patched one.

Technical timestamps (created_at/updated_at/audit/expiry) deliberately stay in
UTC (datetime.utcnow()) — only "what date/time does the owner/worker see on
their clock in Chemnitz" goes through business_now().
"""
from datetime import datetime


def business_now():
    """Единая точка для ТЕКУЩЕГО момента по бизнес-таймзоне (Europe/Berlin) —
    в отличие от datetime.utcnow()/technical timestamps, которые ОСТАЮТСЯ в UTC
    намеренно (не business-date). Используется везде, где "сегодня"/"сейчас"
    должно совпадать с тем, что видит владелец/работник на часах в Chemnitz,
    не с UTC-датой сервера."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/Berlin'))
