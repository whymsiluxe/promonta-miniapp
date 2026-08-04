"""Раунд 4 (Задача 3): backend _stage_summary через list_objects().

Проверяет поля stage_summary для карточки объекта:
- 3/7 с текущим этапом -> current + next (следующий за текущим)
- ничего не начато -> next = первый незавершённый (для "Следующий: Демонтаж")
- всё готово -> completed_count == total, next = None
- нет этапов -> stage_summary = None

Стиль как tests/test_worker_object_privacy.py: list_objects() вызывается напрямую
с owner-ролью, Google Sheets/JSON I/O мокаются через patch.object.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_stage_summary.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
OBJ_HEADER = ['ID объекта', 'Объект', 'Адрес', 'Статус']
OBJ_ROW = ['OBJ-1', 'Дом', 'Hauptstr. 1', 'В работе']


def _stage(name, status):
    return {'Название этапа': name, 'Статус': status}


def _summary_for(stages):
    fake_lib = MagicMock()
    # ключ группировки -- oid.upper() ('OBJ-1')
    fake_lib.all_stages_grouped.return_value = {'OBJ-1': stages}
    ctxs = [
        patch.object(backend, '_cached_get_used_range', return_value=[OBJ_HEADER, OBJ_ROW]),
        patch.object(backend, '_load_assignments', return_value={}),
        patch.object(backend, '_load_worker_profiles', return_value={}),
        patch.object(backend, '_load_object_images', return_value={}),
        patch.object(backend, '_load_repo_objekte_lib', return_value=fake_lib),
    ]
    for c in ctxs:
        c.start()
    try:
        result = backend.list_objects(user=OWNER, role='owner')
    finally:
        for c in ctxs:
            c.stop()
    return result['objects'][0].get('stage_summary')


class StageSummaryTests(unittest.TestCase):
    def test_in_progress_gives_current_and_next(self):
        stages = [
            _stage('Демонтаж', 'готово'),
            _stage('Штукатурка', 'в процессе'),
            _stage('Шпаклёвка', 'предстоит'),
        ]
        s = _summary_for(stages)
        self.assertEqual(s['total'], 3)
        self.assertEqual(s['completed_count'], 1)
        self.assertEqual(s['current'], 'Штукатурка')
        self.assertEqual(s['next'], 'Шпаклёвка')

    def test_nothing_started_next_is_first_pending(self):
        stages = [
            _stage('Демонтаж', 'предстоит'),
            _stage('Штукатурка', 'предстоит'),
        ]
        s = _summary_for(stages)
        self.assertEqual(s['completed_count'], 0)
        self.assertIsNone(s['current'])
        self.assertEqual(s['next'], 'Демонтаж')

    def test_all_done_next_none(self):
        stages = [
            _stage('Демонтаж', 'готово'),
            _stage('Штукатурка', 'готово'),
        ]
        s = _summary_for(stages)
        self.assertEqual(s['completed_count'], 2)
        self.assertEqual(s['total'], 2)
        self.assertIsNone(s['current'])
        self.assertIsNone(s['next'])

    def test_no_stages_summary_none(self):
        s = _summary_for([])
        self.assertIsNone(s)


if __name__ == '__main__':
    unittest.main()
