"""Regression test for the UI fix round item 5: /api/profile/me must never
return a garbled/tofu name when both the stored profile name AND the current
Telegram first_name fail sanitization -- falls back to the user_id, matching
the same pattern /api/roles already used correctly.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend


class ProfileMeGarbledNameFallbackTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='promonta-test-tofu-')
        backend.WORKER_PROFILES_FILE = os.path.join(self._tmp, 'worker_profiles.json')
        backend.ROLES_FILE = os.path.join(self._tmp, 'roles.json')

    def test_sanitize_display_name_rejects_hangul_filler(self):
        # Exact real-world case from the owner's screenshot: Telegram
        # first_name made entirely of Hangul filler characters (U+3164 and
        # relatives) -- a valid Unicode letter category, so a naive \w check
        # would NOT catch it, which is exactly why _sanitize_display_name
        # explicitly strips these first.
        garbled = 'ㅤ ㅤ ㅤ ㅤ ㅤ ㅤ'
        result = backend._sanitize_display_name(garbled, 'FALLBACK')
        self.assertEqual(result, 'FALLBACK',
            'Hangul filler characters must not be treated as a real name')

    def test_sanitize_display_name_preserves_real_cyrillic(self):
        # Never silently strip a legitimate name -- explicit owner requirement.
        result = backend._sanitize_display_name('Иван Петров', 'FALLBACK')
        self.assertEqual(result, 'Иван Петров')

    def test_get_my_profile_falls_back_to_user_id_when_both_names_garbled(self):
        uid = '999888777'
        garbled = 'ㅤ ㅤ ㅤ'
        profiles = {uid: {'name': garbled, 'skills': [], 'quiz_completed': True}}
        backend._save_worker_profiles(profiles)
        backend._save_roles({uid: 'worker'})

        user = {'id': int(uid), 'first_name': garbled}
        result = backend.get_my_profile(user=user)
        self.assertEqual(result['name'], uid,
            'When both stored name and current Telegram first_name are garbled, '
            'must fall back to user_id (matching /api/roles pattern), not pass '
            'the garbled string through to the client')

    def test_get_my_profile_heals_from_valid_first_name(self):
        uid = '999888778'
        garbled = 'ㅤ ㅤ'
        profiles = {uid: {'name': garbled, 'skills': [], 'quiz_completed': True}}
        backend._save_worker_profiles(profiles)
        backend._save_roles({uid: 'worker'})

        user = {'id': int(uid), 'first_name': 'Виктор'}
        result = backend.get_my_profile(user=user)
        self.assertEqual(result['name'], 'Виктор',
            'A garbled stored name must still heal from a valid Telegram first_name')


if __name__ == '__main__':
    unittest.main()
