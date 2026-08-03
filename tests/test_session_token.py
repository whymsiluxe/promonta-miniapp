"""03.08 (ТЗ Задача 1): backend session token (12ч) поверх Telegram initData (1ч TTL).
Тот же стиль, что tests/test_access_control.py -- route handlers/helpers вызываются
напрямую, genuine HMAC-signed initData строится тем же способом, что реальный клиент.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_session_token.py -v
"""
import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


def _build_init_data(user_id=111, first_name='Test', auth_date=None):
    if auth_date is None:
        auth_date = int(time.time())
    user_json = json.dumps({'id': user_id, 'first_name': first_name}, separators=(',', ':'))
    params = {'auth_date': str(auth_date), 'user': user_json, 'query_id': 'AAAtest'}
    data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(params.items()))
    computed_hash = hmac.new(backend._secret_key(), data_check_string.encode(), hashlib.sha256).hexdigest()
    parts = [f'{k}={quote(v, safe="")}' for k, v in params.items()]
    parts.append(f'hash={computed_hash}')
    return '&'.join(parts)


ROLES = {'111': 'worker', '1': 'owner'}


class SessionTokenCreationTests(unittest.TestCase):
    """1. валидный initData -> создаётся session token."""

    def test_valid_init_data_creates_session_token(self):
        init_data = _build_init_data(user_id=111)
        with patch.object(backend, '_load_roles', return_value=ROLES), \
             patch.object(backend, '_notify_owner_new_user'):
            result = backend.create_session(x_telegram_init_data=init_data)
        self.assertIn('token', result)
        self.assertEqual(result['user_id'], 111)
        self.assertEqual(result['expires_in'], backend.SESSION_TOKEN_MAX_AGE)

    def test_non_whitelisted_user_cannot_create_token(self):
        init_data = _build_init_data(user_id=999)
        with patch.object(backend, '_load_roles', return_value=ROLES), \
             patch.object(backend, '_notify_owner_new_user'):
            with self.assertRaises(HTTPException) as ctx:
                backend.create_session(x_telegram_init_data=init_data)
        self.assertEqual(ctx.exception.status_code, 403)


class SessionTokenOutlivesInitDataTests(unittest.TestCase):
    """2. token работает даже когда исходный initData уже старше часа -- это весь
    смысл фичи: initData использовался ТОЛЬКО чтобы получить token один раз, сам
    token живёт по собственному 12-часовому таймеру, не связанному с initData TTL."""

    def test_token_valid_after_init_data_would_be_expired(self):
        old_auth_date = int(time.time()) - 7200  # 2 часа назад -- initData уже мёртв
        init_data = _build_init_data(user_id=111, auth_date=old_auth_date)
        with self.assertRaises(HTTPException):
            backend.validate_init_data(init_data)  # подтверждаем, что initData САМ по себе уже 401

        token = backend.create_session_token('111')  # token создаётся независимо от initData age
        with patch.object(backend, '_load_roles', return_value=ROLES):
            user = backend.get_current_user(authorization=f'Bearer {token}', x_telegram_init_data=None)
        self.assertEqual(user['id'], 111)


class SessionTokenExpiryTests(unittest.TestCase):
    """3. просроченный (>12ч) token отклоняется."""

    def test_expired_token_rejected(self):
        token = backend.create_session_token('111')
        # Перематываем время вперёд за пределы 12ч, не дожидаясь реально.
        with patch.object(backend.time, 'time', return_value=time.time() + backend.SESSION_TOKEN_MAX_AGE + 60):
            with self.assertRaises(HTTPException) as ctx:
                backend.verify_session_token(token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_token_valid_just_before_expiry(self):
        token = backend.create_session_token('111')
        with patch.object(backend.time, 'time', return_value=time.time() + backend.SESSION_TOKEN_MAX_AGE - 60):
            user_id = backend.verify_session_token(token)
        self.assertEqual(user_id, '111')


class SessionTokenTamperTests(unittest.TestCase):
    """4. изменённый/подделанный token отклоняется."""

    def test_tampered_signature_rejected(self):
        token = backend.create_session_token('111')
        payload_b64, sig = token.rsplit('.', 1)
        bad_sig = ('0' if sig[0] != '0' else '1') + sig[1:]
        with self.assertRaises(HTTPException) as ctx:
            backend.verify_session_token(f'{payload_b64}.{bad_sig}')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_tampered_payload_rejected(self):
        # Меняем user_id в payload напрямую, не трогая сигнатуру -- HMAC должен не совпасть.
        token = backend.create_session_token('111')
        _, sig = token.rsplit('.', 1)
        # Берём чужой (999) payload + подпись из токена для 111 -- подпись не совпадёт
        # с новым payload без знания _session_secret().
        tampered_token = backend.create_session_token('999').rsplit('.', 1)[0] + '.' + sig
        with self.assertRaises(HTTPException) as ctx:
            backend.verify_session_token(tampered_token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_malformed_token_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.verify_session_token('not-a-valid-token-at-all')
        self.assertEqual(ctx.exception.status_code, 401)


class SessionTokenRevocationTests(unittest.TestCase):
    """5. пользователь, удалённый из whitelist/roles, теряет доступ даже с валидным token."""

    def test_removed_from_whitelist_loses_access_with_valid_token(self):
        token = backend.create_session_token('111')
        with patch.object(backend, '_load_roles', return_value=ROLES):
            user = backend.get_current_user(authorization=f'Bearer {token}', x_telegram_init_data=None)
        self.assertEqual(user['id'], 111)

        # Owner убрал 111 из roles.json -- тот же токен, тот же 12ч срок, но whitelist пуст.
        with patch.object(backend, '_load_roles', return_value={'1': 'owner'}):
            with self.assertRaises(HTTPException) as ctx:
                backend.get_current_user(authorization=f'Bearer {token}', x_telegram_init_data=None)
        self.assertEqual(ctx.exception.status_code, 403)


class SessionTokenRoleFreshnessTests(unittest.TestCase):
    """6. Owner/Worker роль определяется актуально на каждый запрос, не из токена
    (токен не содержит роль вообще -- см. create_session_token payload: только
    user_id + exp)."""

    def test_role_reflects_current_roles_json_not_token(self):
        token = backend.create_session_token('111')
        with patch.object(backend, '_load_roles', return_value={'111': 'worker'}):
            user = backend.get_current_user(authorization=f'Bearer {token}', x_telegram_init_data=None)
            role = backend.get_role(user=user)
        self.assertEqual(role, 'worker')

        # Owner повышает 111 до owner -- тот же токен, роль теперь другая, без переиздания token.
        with patch.object(backend, '_load_roles', return_value={'111': 'owner'}):
            user = backend.get_current_user(authorization=f'Bearer {token}', x_telegram_init_data=None)
            role = backend.get_role(user=user)
        self.assertEqual(role, 'owner')

    def test_token_payload_contains_no_role(self):
        token = backend.create_session_token('111')
        payload_b64 = token.rsplit('.', 1)[0]
        import base64
        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        self.assertNotIn('owner', payload)
        self.assertNotIn('worker', payload)
        self.assertNotIn('role', payload)


class BackwardCompatInitDataTests(unittest.TestCase):
    """7. старый путь через X-Telegram-Init-Data продолжает работать."""

    def test_old_header_path_still_works(self):
        init_data = _build_init_data(user_id=111)
        with patch.object(backend, '_load_roles', return_value=ROLES):
            user = backend.get_current_user(authorization=None, x_telegram_init_data=init_data)
        self.assertEqual(user['id'], 111)

    def test_neither_header_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.get_current_user(authorization=None, x_telegram_init_data=None)
        self.assertEqual(ctx.exception.status_code, 401)


class SessionTokenNoSecretsInPayloadTests(unittest.TestCase):
    def test_bot_token_not_leaked_in_token(self):
        token = backend.create_session_token('111')
        self.assertNotIn(backend.BOT_TOKEN, token)


if __name__ == '__main__':
    unittest.main()
