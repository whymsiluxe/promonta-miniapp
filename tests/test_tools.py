"""Backend tests for the Инструменты checkout/return cleanup (30.07): Worker no longer
types their own name at checkout -- backend derives holder_name from the authorized
Telegram user and ignores any client-supplied holder. Also covers the real /return
endpoint (vs. the old checkout-with-empty-fields bug) and the repo-tracked tools_lib
import path.

Same plain stdlib unittest approach as tests/test_chat_backend.py (no test framework
installed, see docs/TESTING.md) -- route handlers are called directly with explicit
kwargs, `tools_lib`'s network-hitting functions (get_tool/checkout_tool/return_tool)
are patched via unittest.mock so these tests don't need real Google Sheets credentials
or network access.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_tools -v
(same environment requirements as test_chat_backend.py: BOT_TOKEN in env, run with
the miniapp .venv's python3, not bare system python3.)
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402
import tools_lib  # noqa: E402


def run(coro):
    return asyncio.run(coro) if asyncio.iscoroutine(coro) else coro


FREE_TOOL = {
    'Серийный #': 'T-014', 'Название Инструмента': 'Bosch GBH 2-28', 'Категория': 'Перфоратор',
    'Кто взял': '', 'У кого взял': '', 'Дата возврата': '', 'Статус': '', 'Обьект/Адрес': '',
    'ID держателя': '',
}
IN_USE_TOOL = {**FREE_TOOL, 'Кто взял': 'Иван Петров', 'Статус': 'На объекте',
               'Обьект/Адрес': 'Квартира Weber', 'ID держателя': '555'}


class RepoTrackedToolsLibImportTests(unittest.TestCase):
    """Гарантия импорта версии из репозитория (п.9): backend/tools_lib.py существует
    и это тот же модуль, что видит main.py через sys.path.insert(0, backend/) выше."""

    def test_tools_lib_importable_from_backend_dir(self):
        backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
        self.assertTrue(os.path.isfile(os.path.join(backend_dir, 'tools_lib.py')))

    def test_main_uses_repo_tools_lib_module(self):
        # tools_lib импортирован через sys.path[0] = backend/ -- модуль резолвится
        # именно отсюда, не через случайный /home/promonta/agent/tools_lib.py.
        self.assertIn(os.path.join(os.path.dirname(__file__), '..', 'backend'), sys.path)
        self.assertTrue(hasattr(tools_lib, 'return_tool'))
        self.assertTrue(hasattr(tools_lib, 'get_tool'))
        self.assertTrue(hasattr(tools_lib, 'mapped_status'))


class CheckoutHolderNameTests(unittest.TestCase):
    """Имя держателя определяется backend'ом из авторизованного Telegram user,
    клиентский holder полностью игнорируется (реальный найденный баг: Worker мог
    вписать чужое имя)."""

    def test_checkout_with_only_object_name_succeeds(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tools_lib, 'checkout_tool') as mock_checkout:
            body = backend.CheckoutBody(object_name='Квартира Weber')
            result = run(backend.checkout_tool(
                serial='T-014', body=body,
                user={'id': 777, 'first_name': 'Олег', 'last_name': 'Иванов'},
            ))
            self.assertEqual(result, {"status": "ok"})
            mock_checkout.assert_called_once()
            args, kwargs = mock_checkout.call_args
            self.assertEqual(args[1], 'Олег Иванов')  # holder_name
            self.assertEqual(kwargs.get('holder_id'), '777')

    def test_client_supplied_holder_is_ignored(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tools_lib, 'checkout_tool') as mock_checkout:
            # Клиент присылает поддельное чужое имя -- backend обязан его игнорировать.
            body = backend.CheckoutBody(object_name='Квартира Weber', holder='Чужое Имя')
            run(backend.checkout_tool(
                serial='T-014', body=body,
                user={'id': 888, 'first_name': 'Мария'},
            ))
            args, kwargs = mock_checkout.call_args
            self.assertEqual(args[1], 'Мария')
            self.assertNotEqual(args[1], 'Чужое Имя')

    def test_holder_id_of_current_user_saved(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tools_lib, 'checkout_tool') as mock_checkout:
            body = backend.CheckoutBody(object_name='Личное пользование')
            run(backend.checkout_tool(serial='T-014', body=body, user={'id': 999999, 'first_name': 'Тест'}))
            _, kwargs = mock_checkout.call_args
            self.assertEqual(kwargs.get('holder_id'), '999999')

    def test_holder_name_fallback_order(self):
        # first_name+last_name -> first_name -> username -> str(id)
        self.assertEqual(backend._holder_name_from_user({'id': 1, 'first_name': 'A', 'last_name': 'B'}), 'A B')
        self.assertEqual(backend._holder_name_from_user({'id': 1, 'first_name': 'A'}), 'A')
        self.assertEqual(backend._holder_name_from_user({'id': 1, 'username': 'someuser'}), 'someuser')
        self.assertEqual(backend._holder_name_from_user({'id': 42}), '42')


class CheckoutValidationTests(unittest.TestCase):
    def test_empty_object_name_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            body = backend.CheckoutBody(object_name='')
            run(backend.checkout_tool(serial='T-014', body=body, user={'id': 1, 'first_name': 'X'}))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_already_checked_out_tool_rejected(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(IN_USE_TOOL)):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.CheckoutBody(object_name='Другой объект')
                run(backend.checkout_tool(serial='T-014', body=body, user={'id': 1, 'first_name': 'X'}))
            self.assertEqual(ctx.exception.status_code, 409)

    def test_nonexistent_tool_rejected(self):
        with patch.object(tools_lib, 'get_tool', return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.CheckoutBody(object_name='Объект')
                run(backend.checkout_tool(serial='T-999', body=body, user={'id': 1, 'first_name': 'X'}))
            self.assertEqual(ctx.exception.status_code, 404)


class ReturnToolTests(unittest.TestCase):
    """Настоящий /return -- НЕ /checkout с пустыми полями (тот всё равно писал бы
    holder_id текущего юзера на свободный инструмент)."""

    def test_current_holder_can_return(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(IN_USE_TOOL)), \
             patch.object(tools_lib, 'return_tool') as mock_return:
            result = run(backend.return_tool(serial='T-014', user={'id': 555, 'first_name': 'Иван'}, role='worker'))
            self.assertEqual(result, {"status": "ok"})
            mock_return.assert_called_once()

    def test_owner_can_return_anyones_tool(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(IN_USE_TOOL)), \
             patch.object(tools_lib, 'return_tool') as mock_return:
            run(backend.return_tool(serial='T-014', user={'id': 1, 'first_name': 'Owner'}, role='owner'))
            mock_return.assert_called_once()

    def test_other_worker_cannot_return(self):
        with patch.object(tools_lib, 'get_tool', return_value=dict(IN_USE_TOOL)):
            with self.assertRaises(HTTPException) as ctx:
                run(backend.return_tool(serial='T-014', user={'id': 999, 'first_name': 'Другой'}, role='worker'))
            self.assertEqual(ctx.exception.status_code, 403)


class OwnerManageStillWorksTests(unittest.TestCase):
    """Owner-управление через PATCH /api/tools/{serial} продолжает работать (holder_id
    optional поле не сломало существующий путь)."""

    def test_owner_update_with_holder_id(self):
        with patch.object(tools_lib, 'update_tool_status') as mock_update:
            body = backend.ToolUpdateBody(status='На объекте', holder='Пётр Сидоров',
                                           object_name='Дом Мюллер', holder_id='321')
            result = run(backend.update_tool(serial='T-014', body=body, user={'id': 1, 'first_name': 'Owner'}))
            self.assertEqual(result, {"status": "ok"})
            mock_update.assert_called_once()
            _, kwargs = mock_update.call_args
            self.assertEqual(kwargs.get('holder_id'), '321')


if __name__ == '__main__':
    unittest.main()
