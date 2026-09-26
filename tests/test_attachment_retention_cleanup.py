"""cleanup_old_attachments.cleanup_dir() -- retention-by-age безопасность
(hardening Этап 0.5, п.4 "voice cleanup").

Контекст (аудит этой сессии): изначальный план ожидал "временный voice-файл,
удаляемый сразу после транскрипции". Реальная архитектура другая и это
осознанное продуктовое решение, задокументированное в
docs/plan-phases/02-product-flows-worker.md:37 -- owner explicit correction:
"транскрибация может быть хуёвой", голосовые (transcribe_audio/ и
chat_attachments/) хранятся ПОСТОЯННО, не как temp-файлы, юзер должен мочь
переслушать оригинал. Поэтому тестировать "хендлер не оставляет файл" было
бы тестом неверной предпосылки.

Единственная реальная страховка от бесконечного роста этих папок --
периодический cleanup_old_attachments.py по возрасту (RETENTION_DAYS=90).
Этот файл тестирует именно его.

НАЙДЕННЫЙ ПРИ АУДИТЕ ПРОБЕЛ (задокументирован, не тихо исправлен -- см.
CLAUDE.md репозитория "No silent security fixes"): DIRS в
cleanup_old_attachments.py покрывает chat_attachments/critical_alert_photos/
checkin_photos, но НЕ transcribe_audio/ -- при том что
docs/DATA_RETENTION_POLICY.md:31 заявляет 90-дневный retention и для
voice/transcription audio. test_transcribe_audio_dir_not_yet_covered_by_cleanup
ниже фиксирует ЭТОТ текущий (неполный) охват как явный факт, а не молчаливое
допущение -- если кто-то добавит transcribe_audio/ в DIRS, тест нужно
обновить осознанно, не будет падать незаметно.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m unittest tests.test_attachment_retention_cleanup -v
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import cleanup_old_attachments as cleanup  # noqa: E402

DAY = 86400


class CleanupDirTests(unittest.TestCase):
    def test_file_older_than_cutoff_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, 'old.jpg')
            with open(fpath, 'wb') as f:
                f.write(b'x')
            old_time = cleanup.CUTOFF - DAY
            os.utime(fpath, (old_time, old_time))

            removed = cleanup.cleanup_dir(tmp)

            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(fpath))

    def test_file_younger_than_cutoff_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, 'fresh.jpg')
            with open(fpath, 'wb') as f:
                f.write(b'x')
            # mtime = now, well inside retention window

            removed = cleanup.cleanup_dir(tmp)

            self.assertEqual(removed, 0)
            self.assertTrue(os.path.exists(fpath))

    def test_nonexistent_directory_is_a_noop(self):
        removed = cleanup.cleanup_dir('/no/such/grandmont-group/dir')
        self.assertEqual(removed, 0)

    def test_unremovable_file_does_not_abort_the_whole_pass(self):
        # OSError on one file (e.g. permission, race with another deleter)
        # must not stop cleanup of the rest of the directory.
        with tempfile.TemporaryDirectory() as tmp:
            old_time = cleanup.CUTOFF - DAY
            paths = []
            for name in ('a.jpg', 'b.jpg'):
                fpath = os.path.join(tmp, name)
                with open(fpath, 'wb') as f:
                    f.write(b'x')
                os.utime(fpath, (old_time, old_time))
                paths.append(fpath)

            real_remove = os.remove

            def flaky_remove(path):
                if path.endswith('a.jpg'):
                    raise OSError('simulated permission error')
                return real_remove(path)

            with patch.object(cleanup.os, 'remove', side_effect=flaky_remove):
                removed = cleanup.cleanup_dir(tmp)

            self.assertEqual(removed, 1)  # only b.jpg counted
            self.assertTrue(os.path.exists(paths[0]))  # a.jpg survived the error
            self.assertFalse(os.path.exists(paths[1]))  # b.jpg still removed


class RetentionCoverageGapTests(unittest.TestCase):
    def test_transcribe_audio_dir_not_yet_covered_by_cleanup(self):
        """Документирует текущий (неполный) охват DIRS -- см. docstring файла.

        Если это когда-нибудь станет False (transcribe_audio/ добавлена в
        DIRS), тест начнёт падать -- это ЖЕЛАТЕЛЬНО: значит кто-то осознанно
        закрыл retention-пробел и должен обновить этот тест, а не наоборот
        (пробел тихо остаётся закрытым в docs, но не в коде)."""
        covered_basenames = {os.path.basename(d.rstrip('/')) for d in cleanup.DIRS}
        self.assertNotIn(
            'transcribe_audio', covered_basenames,
            "transcribe_audio/ теперь покрыта cleanup_old_attachments.DIRS -- "
            "отлично, но тогда обнови docs/DATA_RETENTION_POLICY.md и удали "
            "этот guard-тест, он больше не нужен."
        )


if __name__ == '__main__':
    unittest.main()
