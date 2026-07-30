"""Backend tests for the Инструменты checkout/return cleanup (30.07): Worker no longer
types their own name at checkout -- backend derives holder_name from the authorized
Telegram user and ignores any client-supplied holder. Also covers the real /return
endpoint (vs. the old checkout-with-empty-fields bug) and the isolated repo-tracked
tools_lib import path (backend._load_repo_tools_lib(), loaded via importlib.util
from an exact file path -- does NOT depend on global sys.path order, unlike the
previous `import tools_lib as tl` approach that briefly broke roadmap_lib resolution).

Same plain stdlib unittest approach as tests/test_chat_backend.py (no test framework
installed, see docs/TESTING.md) -- route handlers are called directly with explicit
kwargs. The repo tools module's network-hitting functions (get_tool/checkout_tool/
return_tool/update_tool_status) are patched on the EXACT module instance returned by
backend._load_repo_tools_lib() -- not on a separately-imported `tools_lib`, which
would be a different module object and silently fail to intercept calls.

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


def run(coro):
    return asyncio.run(coro) if asyncio.iscoroutine(coro) else coro


def _repo_tools_lib():
    """Возвращает РЕАЛЬНО используемый route-handler'ами tools-модуль -- тот же
    экземпляр, что backend.checkout_tool()/return_tool()/etc. получают через
    tl = _load_repo_tools_lib() внутри себя. Не зависит от порядка запуска других
    тестов и от того, что уже могло попасть в sys.modules['tools_lib'] -- модуль
    загружен под собственным внутренним именем (promonta_repo_tools_lib)."""
    return backend._load_repo_tools_lib()


FREE_TOOL = {
    'Серийный #': 'T-014', 'Название Инструмента': 'Bosch GBH 2-28', 'Категория': 'Перфоратор',
    'Кто взял': '', 'У кого взял': '', 'Дата возврата': '', 'Статус': '', 'Обьект/Адрес': '',
    'ID держателя': '',
}
IN_USE_TOOL = {**FREE_TOOL, 'Кто взял': 'Иван Петров', 'Статус': 'На объекте',
               'Обьект/Адрес': 'Квартира Weber', 'ID держателя': '555'}


class RepoTrackedToolsLibImportTests(unittest.TestCase):
    """Гарантия импорта версии из репозитория (п.9 спека): backend/tools_lib.py
    существует и это тот же модуль, что реально использует backend.checkout_tool()
    и остальные tools-endpoints -- проверено через сам loader, а не через независимый
    `import tools_lib`, который зависел бы от глобального sys.path и мог смотреть
    на другой файл (тот класс бага, что уже случался с /home/promonta/agent/tools_lib.py)."""

    def test_tools_lib_py_exists_in_backend_dir(self):
        self.assertTrue(os.path.isfile(backend.TOOLS_LIB_PATH))
        self.assertEqual(os.path.dirname(backend.TOOLS_LIB_PATH), backend.BACKEND_DIR)

    def test_loader_returns_module_from_exact_backend_path(self):
        module = _repo_tools_lib()
        self.assertEqual(os.path.abspath(module.__file__), os.path.abspath(backend.TOOLS_LIB_PATH))

    def test_loader_caches_single_instance(self):
        # Не должен загружаться заново при каждом вызове -- один и тот же объект.
        self.assertIs(_repo_tools_lib(), _repo_tools_lib())

    def test_loaded_module_has_expected_functions(self):
        module = _repo_tools_lib()
        for name in ('get_tool', 'checkout_tool', 'return_tool', 'update_tool_status',
                     'list_tools', 'tool_history', 'add_tool', 'mapped_status'):
            self.assertTrue(hasattr(module, name), f'tools_lib отсутствует {name}')

    def test_main_py_restores_original_global_sys_path_insert(self):
        # main.py сам должен вставлять РОВНО '/home/promonta/agent' единственным
        # sys.path.insert верхнего уровня -- как было до commit effe2c5 (тот коммит
        # временно менял это на insert(0, backend_dir) + insert(1, agent_dir), что
        # глобально сдвинуло разрешение всех shared-модулей, включая roadmap_lib,
        # и сломало 2 roadmap-теста). Проверяем сам исходник main.py, а не текущий
        # sys.path теста -- этот тестовый файл сам делает свой insert(0, backend/)
        # выше, так что live sys.path[0] в момент теста не показал бы регрессию.
        with open(os.path.join(backend.BACKEND_DIR, 'main.py'), encoding='utf-8') as f:
            source = f.read()
        insert_lines = [line.strip() for line in source.splitlines() if 'sys.path.insert' in line]
        self.assertEqual(insert_lines, ["sys.path.insert(0, '/home/promonta/agent')"])


class CheckoutHolderNameTests(unittest.TestCase):
    """Имя держателя определяется backend'ом из авторизованного Telegram user,
    клиентский holder полностью игнорируется (реальный найденный баг: Worker мог
    вписать чужое имя)."""

    def test_checkout_with_only_object_name_succeeds(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tl, 'checkout_tool') as mock_checkout:
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
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tl, 'checkout_tool') as mock_checkout:
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
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(FREE_TOOL)), \
             patch.object(tl, 'checkout_tool') as mock_checkout:
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
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(IN_USE_TOOL)):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.CheckoutBody(object_name='Другой объект')
                run(backend.checkout_tool(serial='T-014', body=body, user={'id': 1, 'first_name': 'X'}))
            self.assertEqual(ctx.exception.status_code, 409)

    def test_nonexistent_tool_rejected(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.CheckoutBody(object_name='Объект')
                run(backend.checkout_tool(serial='T-999', body=body, user={'id': 1, 'first_name': 'X'}))
            self.assertEqual(ctx.exception.status_code, 404)


class ReturnToolTests(unittest.TestCase):
    """Настоящий /return -- НЕ /checkout с пустыми полями (тот всё равно писал бы
    holder_id текущего юзера на свободный инструмент)."""

    def test_current_holder_can_return(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(IN_USE_TOOL)), \
             patch.object(tl, 'return_tool') as mock_return:
            result = run(backend.return_tool(serial='T-014', user={'id': 555, 'first_name': 'Иван'}, role='worker'))
            self.assertEqual(result, {"status": "ok"})
            mock_return.assert_called_once()

    def test_owner_can_return_anyones_tool(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(IN_USE_TOOL)), \
             patch.object(tl, 'return_tool') as mock_return:
            run(backend.return_tool(serial='T-014', user={'id': 1, 'first_name': 'Owner'}, role='owner'))
            mock_return.assert_called_once()

    def test_other_worker_cannot_return(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'get_tool', return_value=dict(IN_USE_TOOL)):
            with self.assertRaises(HTTPException) as ctx:
                run(backend.return_tool(serial='T-014', user={'id': 999, 'first_name': 'Другой'}, role='worker'))
            self.assertEqual(ctx.exception.status_code, 403)


class OwnerManageStillWorksTests(unittest.TestCase):
    """Owner-управление через PATCH /api/tools/{serial} продолжает работать (holder_id
    optional поле не сломало существующий путь)."""

    def test_owner_update_with_holder_id(self):
        tl = _repo_tools_lib()
        with patch.object(tl, 'update_tool_status') as mock_update:
            body = backend.ToolUpdateBody(status='На объекте', holder='Пётр Сидоров',
                                           object_name='Дом Мюллер', holder_id='321')
            result = run(backend.update_tool(serial='T-014', body=body, user={'id': 1, 'first_name': 'Owner'}))
            self.assertEqual(result, {"status": "ok"})
            mock_update.assert_called_once()
            _, kwargs = mock_update.call_args
            self.assertEqual(kwargs.get('holder_id'), '321')


if __name__ == '__main__':
    unittest.main()
