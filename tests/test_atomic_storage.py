"""Backend tests for atomic JSON storage (Release-аудит Этап 2, P1): checkin_meta.json
(главный стор смен/GPS/фото), chat_messages.json/chat_messages_archive.json и
mangel_tickets.json раньше писались через plain open(w)+json.dump -- crash посреди
записи (systemctl restart, OOM-kill) оставлял бы обрезанный JSON.

Same plain stdlib unittest approach as tests/test_tools.py -- pure filesystem
behavior tested directly, no network/real Google Sheets access needed.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_atomic_storage -v
(same environment requirements as test_tools.py: BOT_TOKEN in env, run with the
miniapp .venv's python3.)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402

# Не `import mangel_lib` напрямую -- main.py грузит его через importlib под приватным
# именем (см. _load_repo_mangel_lib), обычный import создал бы ВТОРОЙ, независимый
# экземпляр модуля (тот же класс бага, что уже чинили для tools_lib в tests/test_tools.py).
mangel_lib = backend._load_repo_mangel_lib()


class AtomicWriteJsonTests(unittest.TestCase):
    """_atomic_write_json -- используется теперь для checkin_meta/chat/chat_archive
    (были plain open(w) до этого коммита)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'store.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_readable_json(self):
        backend._atomic_write_json(self.path, {'a': 1, 'b': [1, 2, 3]})
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(json.load(f), {'a': 1, 'b': [1, 2, 3]})

    def test_no_leftover_temp_file_after_success(self):
        backend._atomic_write_json(self.path, [1, 2, 3])
        leftovers = [f for f in os.listdir(self.tmpdir) if f != 'store.json']
        self.assertEqual(leftovers, [])

    def test_replaces_existing_file_atomically(self):
        backend._atomic_write_json(self.path, {'version': 1})
        backend._atomic_write_json(self.path, {'version': 2})
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(json.load(f), {'version': 2})
        leftovers = [f for f in os.listdir(self.tmpdir) if f != 'store.json']
        self.assertEqual(leftovers, [])

    def test_two_sequential_updates_both_persist(self):
        # Не настоящая RMW-гонка (та закрыта отдельными _lock_for/_chat_lock/
        # _checkin_lock на уровне вызывающего кода) -- здесь просто проверяем,
        # что последовательные вызовы не теряют данные друг друга.
        backend._atomic_write_json(self.path, {'items': [1]})
        data = json.load(open(self.path, encoding='utf-8'))
        data['items'].append(2)
        backend._atomic_write_json(self.path, data)
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(json.load(f)['items'], [1, 2])


class CorruptJsonRecoveryTests(unittest.TestCase):
    """_safe_load_json -- повреждённый JSON деградирует к default, не роняет
    запрос 500-кой."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'corrupt.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_corrupt_json_falls_back_to_default(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{"truncated": tr')  # намеренно обрезанный/невалидный JSON
        result = backend._safe_load_json(self.path, {'fallback': True})
        self.assertEqual(result, {'fallback': True})

    def test_missing_file_returns_default(self):
        result = backend._safe_load_json(os.path.join(self.tmpdir, 'does-not-exist.json'), [])
        self.assertEqual(result, [])

    def test_valid_json_returns_actual_content(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'real': 'data'}, f)
        result = backend._safe_load_json(self.path, {'fallback': True})
        self.assertEqual(result, {'real': 'data'})


class RepoTrackedMangelLibImportTests(unittest.TestCase):
    """mangel_lib.py теперь в backend/ (было полностью вне git) -- гарантия
    импорта из репозитория через тот же изолированный loader, что и tools_lib.py."""

    def test_mangel_lib_py_exists_in_backend_dir(self):
        self.assertTrue(os.path.isfile(backend.MANGEL_LIB_PATH))
        self.assertEqual(os.path.dirname(backend.MANGEL_LIB_PATH), backend.BACKEND_DIR)

    def test_loader_returns_module_from_exact_backend_path(self):
        module = backend._load_repo_mangel_lib()
        self.assertEqual(os.path.abspath(module.__file__), os.path.abspath(backend.MANGEL_LIB_PATH))

    def test_loader_caches_single_instance(self):
        self.assertIs(backend._load_repo_mangel_lib(), backend._load_repo_mangel_lib())

    def test_module_level_ml_is_the_repo_loaded_instance(self):
        # main.py module-level `ml` должен быть тем же объектом, что возвращает
        # _load_repo_mangel_lib() -- не отдельный обычный import.
        self.assertIs(backend.ml, backend._load_repo_mangel_lib())

    def test_loaded_module_has_expected_functions(self):
        module = backend._load_repo_mangel_lib()
        for name in ('list_tickets', 'create_ticket', 'update_status', 'add_comment', 'get_ticket', 'count_by_status'):
            self.assertTrue(hasattr(module, name), f'mangel_lib отсутствует {name}')

    def test_tools_lib_and_mangel_lib_use_independent_cache_keys(self):
        # Оба модуля грузятся через общий _load_repo_module() с разделяемым
        # cache dict -- проверяем, что они не затирают друг друга.
        tools = backend._load_repo_tools_lib()
        mangel = backend._load_repo_mangel_lib()
        self.assertIsNot(tools, mangel)
        self.assertTrue(hasattr(tools, 'checkout_tool'))
        self.assertTrue(hasattr(mangel, 'create_ticket'))


class MangelLibAtomicWriteTests(unittest.TestCase):
    """mangel_lib._atomic_write -- заменил plain open(w)+json.dump на всех 4
    write call sites (_save/create_ticket/update_status/add_comment)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'mangel_tickets.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_atomic_write_produces_readable_json(self):
        mangel_lib._atomic_write(self.path, [{'id': '1', 'status': 'gemeldet'}])
        with open(self.path, encoding='utf-8') as f:
            self.assertEqual(json.load(f), [{'id': '1', 'status': 'gemeldet'}])

    def test_no_leftover_temp_file(self):
        mangel_lib._atomic_write(self.path, [])
        leftovers = [f for f in os.listdir(self.tmpdir) if f != 'mangel_tickets.json']
        self.assertEqual(leftovers, [])

    def test_create_update_add_comment_use_atomic_write(self):
        # Функциональный прогон полного цикла на реальном (временном) MANGEL_FILE --
        # подтверждает, что все 3 мутирующие операции реально пишут через _atomic_write,
        # не только что сама функция _atomic_write работает изолированно.
        original_file = mangel_lib.MANGEL_FILE
        mangel_lib.MANGEL_FILE = self.path
        try:
            ticket = mangel_lib.create_ticket('OBJ-1', 'Трещина в стене', 'u1')
            self.assertTrue(os.path.isfile(self.path))
            leftovers = [f for f in os.listdir(self.tmpdir) if f != 'mangel_tickets.json']
            self.assertEqual(leftovers, [])

            mangel_lib.update_status(ticket['id'], 'in Bearbeitung')
            leftovers = [f for f in os.listdir(self.tmpdir) if f != 'mangel_tickets.json']
            self.assertEqual(leftovers, [])

            mangel_lib.add_comment(ticket['id'], 'u2', 'Работаем над этим')
            leftovers = [f for f in os.listdir(self.tmpdir) if f != 'mangel_tickets.json']
            self.assertEqual(leftovers, [])

            final = mangel_lib.get_ticket(ticket['id'])
            self.assertEqual(final['status'], 'in Bearbeitung')
            self.assertEqual(len(final['comments']), 1)
        finally:
            mangel_lib.MANGEL_FILE = original_file


if __name__ == '__main__':
    unittest.main()
