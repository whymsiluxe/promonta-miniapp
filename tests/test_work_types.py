"""01.08: единый каталог видов работ (backend/work_types.py) + legacy-миграция
(profile_skills.py). Тестирует чистые функции напрямую, без FastAPI/HTTP-слоя --
тот же принцип, что tests/test_roadmap.py для roadmap_lib.py.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_work_types.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import work_types as wt  # noqa: E402
import profile_skills as pskills  # noqa: E402


class CatalogIntegrityTests(unittest.TestCase):
    def test_all_ids_unique(self):
        ids = [w['id'] for w in wt.WORK_TYPES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_featured_has_exactly_seven_in_correct_order(self):
        expected = [
            "tile_work", "painting", "plastering", "drywall",
            "masonry", "screed_concrete", "demolition",
        ]
        self.assertEqual(wt.FEATURED_ORDER, expected)
        catalog = wt.work_types_catalog()
        self.assertEqual(len(catalog['featured']), 7)
        self.assertEqual([w['id'] for w in catalog['featured']], expected)

    def test_every_active_work_type_belongs_to_a_group(self):
        catalog = wt.work_types_catalog()
        grouped_ids = {w['id'] for g in catalog['groups'] for w in g['items']}
        active_ids = {w['id'] for w in wt.WORK_TYPES if w['active']}
        self.assertEqual(grouped_ids, active_ids)

    def test_group_order_is_stable(self):
        catalog = wt.work_types_catalog()
        self.assertEqual([g['id'] for g in catalog['groups']], wt.GROUP_ORDER)

    def test_search_by_name(self):
        results = wt.search_work_types('плитк')
        ids = [w['id'] for w in results]
        self.assertIn('tile_work', ids)

    def test_search_by_keyword_alias(self):
        results = wt.search_work_types('fliesen')
        ids = [w['id'] for w in results]
        self.assertIn('tile_work', ids)

    def test_furniture_assembly_exists_as_single_skill(self):
        item = wt.get_work_type('furniture_assembly')
        self.assertIsNotNone(item)
        self.assertEqual(item['name'], 'Сборка мебели')

    def test_no_separate_kitchen_or_wardrobe_skills(self):
        names = [w['name'].lower() for w in wt.WORK_TYPES]
        for forbidden in ('кухн', 'шкаф'):
            self.assertFalse(any(forbidden in n for n in names), f"'{forbidden}' не должен быть отдельным навыком")

    def test_drywall_not_split_into_walls_and_ceilings(self):
        # Спека: "Не разделять навык Гипсокартон на стены и потолки"
        drywall_related = [w for w in wt.WORK_TYPES if w['id'] == 'drywall']
        self.assertEqual(len(drywall_related), 1)

    def test_electrical_requires_qualification(self):
        self.assertTrue(wt.get_work_type('electrical')['requires_qualification'])

    def test_most_skills_do_not_require_qualification(self):
        self.assertFalse(wt.get_work_type('tile_work')['requires_qualification'])

    def test_get_work_type_name_unknown_id_returns_id_itself(self):
        # Легаси/повреждённая запись не должна падать 500-кой -- см. main.py usage.
        self.assertEqual(pskills.skill_display_name('unknown_xyz'), 'unknown_xyz')


class LegacyMigrationTests(unittest.TestCase):
    def test_known_legacy_names_map_to_correct_ids(self):
        cases = {
            "Штукатурка": "plastering",
            "Малярные работы": "painting",
            "Электрика": "electrical",
            "Кровля": "roofing",
            "Фасад": "facade_wdvs",
            "Сантехника": "plumbing",
            "Плитка": "tile_work",
            "Демонтаж": "demolition",
            "Гипсокартон (сухая стройка)": "drywall",
            "Стяжка пола / бетонные работы": "screed_concrete",
        }
        for name, expected_id in cases.items():
            self.assertEqual(wt.legacy_skill_name_to_id(name), expected_id)

    def test_migration_produces_independent_level_unverified(self):
        result = pskills.migrate_legacy_skills(["Плитка"])
        self.assertEqual(result, [{"skill_id": "tile_work", "level": "independent", "verified": False}])

    def test_migration_is_idempotent(self):
        profile = {"skills": ["Плитка", "Демонтаж"]}
        skills_v2_first, changed_first = pskills.normalize_profile_skills(profile)
        self.assertTrue(changed_first)
        profile['skills_v2'] = skills_v2_first
        skills_v2_second, changed_second = pskills.normalize_profile_skills(profile)
        self.assertFalse(changed_second)
        self.assertEqual(skills_v2_first, skills_v2_second)

    def test_unknown_legacy_skill_not_silently_lost(self):
        result = pskills.migrate_legacy_skills(["Совершенно неизвестный навык XYZ"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['skill_id'], "Совершенно неизвестный навык XYZ")

    def test_existing_profile_without_legacy_skills_not_reset(self):
        profile = {"quiz_completed": True}
        skills_v2, changed = pskills.normalize_profile_skills(profile)
        self.assertEqual(skills_v2, [])
        self.assertFalse(changed)

    def test_legacy_skill_names_from_v2_roundtrip(self):
        skills_v2 = [{"skill_id": "tile_work", "level": "master", "verified": True}]
        names = pskills.legacy_skill_names_from_v2(skills_v2)
        self.assertEqual(names, ["Плиточные работы"])


class SkillMutationHelperTests(unittest.TestCase):
    def test_set_worker_skill_resets_verified(self):
        skills_v2 = [{"skill_id": "tile_work", "level": "master", "verified": True}]
        result = pskills.set_worker_skill(skills_v2, "tile_work", "independent")
        self.assertEqual(result, [{"skill_id": "tile_work", "level": "independent", "verified": False}])

    def test_remove_worker_skill(self):
        skills_v2 = [{"skill_id": "tile_work", "level": "master", "verified": True}]
        result = pskills.remove_worker_skill(skills_v2, "tile_work")
        self.assertEqual(result, [])

    def test_set_skill_verification_found(self):
        skills_v2 = [{"skill_id": "tile_work", "level": "master", "verified": False}]
        result, found = pskills.set_skill_verification(skills_v2, "tile_work", True)
        self.assertTrue(found)
        self.assertTrue(result[0]['verified'])

    def test_set_skill_verification_not_found(self):
        skills_v2 = []
        result, found = pskills.set_skill_verification(skills_v2, "tile_work", True)
        self.assertFalse(found)


if __name__ == '__main__':
    unittest.main()
