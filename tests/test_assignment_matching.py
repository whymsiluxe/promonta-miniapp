"""01.08: подбор кандидатов (backend/assignment_matching.py) -- полный matching по
ВСЕМ навыкам каталога (не только 8 из 19, как было со старым SKILL_STAGE_MAP),
сортировка по verified+level, availability по пересечениям/абсенсу/занятости.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_assignment_matching.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import assignment_matching as amatch  # noqa: E402
import work_types as wt  # noqa: E402


def _worker(uid, name, skill_id=None, level='independent', verified=False):
    profile = {'skills_v2': [{'skill_id': skill_id, 'level': level, 'verified': verified}]} if skill_id else {'skills_v2': []}
    return {'user_id': uid, 'name': name, 'has_avatar': False, 'profile': profile}


class MatchingCoversAllCatalogSkillsTests(unittest.TestCase):
    """Спека: 'Все навыки каталога должны участвовать одинаково' -- раньше
    SKILL_STAGE_MAP покрывал только 8 из 19. Проверяем репрезентативный набор,
    включая явно названные в спеке: Fermacell, кладка, стяжка, сборка мебели,
    сварка, окна и двери, леса, ламинат, гидроизоляция."""

    def _assert_matches(self, skill_id):
        worker = _worker('1', 'Worker', skill_id=skill_id)
        result = amatch.build_candidates(skill_id, 'OBJ-1', '2026-08-05', '2026-08-16', [worker], {}, [], [])
        ids = [c['user_id'] for c in result['recommended']]
        self.assertIn('1', ids, f"{skill_id} не попал в recommended")

    def test_fermacell(self):
        self._assert_matches('fermacell_dry_floor')

    def test_masonry(self):
        self._assert_matches('masonry')

    def test_screed(self):
        self._assert_matches('screed_concrete')

    def test_furniture_assembly(self):
        self._assert_matches('furniture_assembly')

    def test_welding(self):
        self._assert_matches('welding')

    def test_windows_doors(self):
        self._assert_matches('windows_doors_installation')

    def test_scaffolding(self):
        self._assert_matches('scaffolding')

    def test_laminate(self):
        self._assert_matches('laminate_vinyl')

    def test_waterproofing(self):
        self._assert_matches('waterproofing')

    def test_all_44_catalog_items_are_matchable(self):
        for w in wt.WORK_TYPES:
            if not w['active']:
                continue
            self._assert_matches(w['id'])


class SortingOrderTests(unittest.TestCase):
    def test_verified_master_beats_unverified_master_beats_verified_independent_beats_helper(self):
        workers = [
            _worker('1', 'UnverifiedMaster', 'tile_work', 'master', False),
            _worker('2', 'VerifiedMaster', 'tile_work', 'master', True),
            _worker('3', 'VerifiedIndependent', 'tile_work', 'independent', True),
            _worker('4', 'Helper', 'tile_work', 'helper', False),
        ]
        result = amatch.build_candidates('tile_work', 'OBJ-1', '2026-08-05', '2026-08-16', workers, {}, [], [])
        names = [c['name'] for c in result['recommended']]
        self.assertEqual(names, ['VerifiedMaster', 'UnverifiedMaster', 'VerifiedIndependent', 'Helper'])

    def test_stable_sort_by_name_within_same_rank(self):
        workers = [
            _worker('1', 'Zed', 'tile_work', 'master', True),
            _worker('2', 'Anna', 'tile_work', 'master', True),
        ]
        result = amatch.build_candidates('tile_work', 'OBJ-1', '2026-08-05', '2026-08-16', workers, {}, [], [])
        names = [c['name'] for c in result['recommended']]
        self.assertEqual(names, ['Anna', 'Zed'])

    def test_worker_without_skill_goes_to_available_not_recommended(self):
        workers = [_worker('1', 'NoSkill')]
        result = amatch.build_candidates('tile_work', 'OBJ-1', '2026-08-05', '2026-08-16', workers, {}, [], [])
        self.assertEqual(result['recommended'], [])
        self.assertEqual(len(result['available']), 1)


class AvailabilityTests(unittest.TestCase):
    def test_overlapping_assignment_blocks(self):
        assignments = {'OBJ-1': [{'user_id': '1', 'status': 'accepted', 'date_from': '2026-08-06', 'date_to': '2026-08-09'}]}
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', assignments, [], [])
        self.assertEqual(avail, 'unavailable')

    def test_non_overlapping_assignment_does_not_block(self):
        assignments = {'OBJ-1': [{'user_id': '1', 'status': 'accepted', 'date_from': '2026-01-01', 'date_to': '2026-01-05'}]}
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', assignments, [], [])
        self.assertEqual(avail, 'available')

    def test_approved_absence_blocks(self):
        abwesenheit = [{'user_id': '1', 'status': 'approved', 'date_from': '2026-08-01', 'date_to': '2026-08-07', 'reason': 'Krankheit'}]
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', {}, abwesenheit, [])
        self.assertEqual(avail, 'unavailable')
        self.assertEqual(reason, 'Отсутствует')  # owner-safe, без деталей причины

    def test_pending_assignment_blocks(self):
        assignments = {'OBJ-2': [{'user_id': '1', 'status': 'pending', 'date_from': '2026-08-06', 'date_to': '2026-08-09'}]}
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', assignments, [], [])
        self.assertEqual(avail, 'unavailable')

    def test_declined_assignment_does_not_block(self):
        assignments = {'OBJ-2': [{'user_id': '1', 'status': 'declined', 'date_from': '2026-08-06', 'date_to': '2026-08-09'}]}
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', assignments, [], [])
        self.assertEqual(avail, 'available')

    def test_multi_day_period_overlap_detected(self):
        assignments = {'OBJ-1': [{'user_id': '1', 'status': 'accepted', 'date_from': '2026-08-16', 'date_to': '2026-08-20'}]}
        avail, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-16', 'OBJ-1', assignments, [], [])
        self.assertEqual(avail, 'unavailable')  # 16-е -- общая граничная дата

    def test_no_private_absence_reason_leaked(self):
        abwesenheit = [{'user_id': '1', 'status': 'approved', 'date_from': '2026-08-01', 'date_to': '2026-08-07',
                         'reason': 'Krankheit', 'note': 'операция на колене -- приватно'}]
        _, reason = amatch.availability_for_worker('1', '2026-08-05', '2026-08-10', 'OBJ-1', {}, abwesenheit, [])
        self.assertNotIn('операция', reason)
        self.assertNotIn('Krankheit', reason)


if __name__ == '__main__':
    unittest.main()
