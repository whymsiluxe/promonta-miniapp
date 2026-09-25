"""Auth core — Phase A step 6: session tokens + initData validation.

Extraction ordered last in Phase A per the dependency map's R4 finding: this
is the deepest chain (get_current_user -> _notify_owner_new_user ->
send_telegram_message), needing core/telegram.py extracted first (already
done) to avoid a main.py <-> core.permissions cycle.

Scope decision, narrower than originally planned: get_current_user(),
get_role(), require_owner(), _load_roles()/_save_roles(),
_notify_owner_new_user(), _load_notified_users()/_save_notified_users(),
has_active_object_access()/can_access_object()/require_object_access() ALL
STAY in main.py, not here. Investigated moving them and found 15 test files
do `patch.object(backend, '_load_roles', return_value=...)` and then call
`backend.get_role(user=user)` directly (e.g. test_session_token.py) --
exactly the business_now()/business_today() trap already documented at
main.py's business_today(): if get_role() lived here and called this
module's own _load_roles by module-local name, patch.object(backend,
'_load_roles', ...) would silently not reach it (patches the main.py
attribute, not core.permissions's), and the test would get a real role
instead of the patched one without erroring. Moving _load_roles here too
doesn't fix it either -- get_current_user() itself is directly called as
backend.get_current_user(...) in test_session_token.py while
backend._load_roles is patched, so get_current_user must stay wherever
_load_roles's patchable name lives, i.e. main.py, until/unless a future
pass rewrites those tests to patch core.permissions._load_roles instead
(out of scope for a behavior-preserving extraction).

What's safe to move now: validate_init_data()/session-token functions are
never patched by name in any test (grepped `patch.object(backend,
'validate_init_data'|'verify_session_token'|'create_session_token'`) --
zero matches -- so no test can depend on which module's copy runs.
"""
import base64
import hashlib
import hmac
import time

from fastapi import HTTPException

try:
    from .limits import INIT_DATA_MAX_AGE, SESSION_TOKEN_MAX_AGE
    from .telegram import BOT_TOKEN
except ImportError:
    from limits import INIT_DATA_MAX_AGE, SESSION_TOKEN_MAX_AGE  # noqa: E402
    from telegram import BOT_TOKEN  # noqa: E402

from urllib.parse import parse_qsl
import json


def _secret_key() -> bytes:
    return hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()


def validate_init_data(init_data: str) -> dict:
    """HMAC-валидация Telegram WebApp initData.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise HTTPException(401, "initData: malformed")
    received_hash = parsed.pop('hash', None)
    if not received_hash:
        raise HTTPException(401, "initData: no hash")

    auth_date = parsed.get('auth_date')
    try:
        if not auth_date:
            raise HTTPException(401, "initData: expired")
        age = time.time() - int(auth_date)
        if age > INIT_DATA_MAX_AGE or age < -60:
            raise HTTPException(401, "initData: expired")
    except ValueError:
        raise HTTPException(401, "initData: malformed auth_date")

    data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(parsed.items()))
    computed_hash = hmac.new(_secret_key(), data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(401, "initData: invalid signature")

    try:
        return json.loads(parsed['user'])
    except (KeyError, json.JSONDecodeError):
        raise HTTPException(401, "initData: no user")


def _session_secret() -> bytes:
    """Домен-разделённый от _secret_key() (initData HMAC) -- разный "usage" в HMAC над
    тем же BOT_TOKEN, так что компрометация одного не равна компрометации другого."""
    return hmac.new(b"SessionToken", BOT_TOKEN.encode(), hashlib.sha256).digest()


def create_session_token(user_id) -> str:
    """Token = base64url(user_id.exp).hex(hmac). Полезная нагрузка содержит ТОЛЬКО
    user_id и unix-время истечения -- никаких паролей/ключей/ролей внутри, роль каждый
    раз проверяется заново по актуальному roles.json (см. get_current_user)."""
    exp = int(time.time()) + SESSION_TOKEN_MAX_AGE
    payload = f"{user_id}.{exp}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    sig = hmac.new(_session_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str) -> str:
    """Возвращает user_id (str) при валидной подписи и не истёкшем токене, иначе 401.
    hmac.compare_digest -- constant-time сравнение, не `==` (timing-attack защита)."""
    try:
        payload_b64, sig = token.rsplit('.', 1)
    except ValueError:
        raise HTTPException(401, "session token: malformed")

    expected_sig = hmac.new(_session_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(401, "session token: invalid signature")

    try:
        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        user_id_str, exp_str = payload.split('.', 1)
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(401, "session token: malformed payload")

    if time.time() > exp:
        raise HTTPException(401, "session token: expired")

    return user_id_str
