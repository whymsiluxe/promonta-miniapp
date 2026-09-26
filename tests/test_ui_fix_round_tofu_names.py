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
        self._tmp = tempfile.mkdtemp(prefix='grandmont-group-test-tofu-')
        # 25.09 (test-pollution fix): these reassignments used to leak into
        # every later test in the same pytest process (no teardown) --
        # harmless while every reader lived in main.py's own namespace, but
        # after routes/auth.py's extraction moved _load_worker_profiles to
        # core.profiles (its own namespace, unaffected by this leak), a
        # write via the leaked backend.WORKER_PROFILES_FILE and a read via
        # core.profiles.WORKER_PROFILES_FILE silently diverged in later
        # tests. Save so tearDown can restore them.
        self._saved_attrs = {
            name: getattr(backend, name) for name in ('WORKER_PROFILES_FILE', 'ROLES_FILE')
        }
        backend.WORKER_PROFILES_FILE = os.path.join(self._tmp, 'worker_profiles.json')
        backend.ROLES_FILE = os.path.join(self._tmp, 'roles.json')

    def tearDown(self):
        for name, value in self._saved_attrs.items():
            setattr(backend, name, value)

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

    def test_sanitize_display_name_strips_filler_from_mixed_name(self):
        # 18.09 real-world case found live in a daily_plan_cutoff_check alert:
        # a name that is MOSTLY filler characters with one real character mixed
        # in ('ᅠ ᅠ ᅠ ᅠ ᅠ ᅠ1') passed the "is there anything real here" check
        # (the '1' counts as \w) but the function then returned the ORIGINAL
        # uncleaned string, filler characters and all, instead of the cleaned
        # one -- so the garbled pattern still reached the UI/Telegram alert
        # even though the function's whole purpose is to strip exactly this.
        garbled_mixed = 'ᅠ ᅠ ᅠ ᅠ ᅠ ᅠ1'
        result = backend._sanitize_display_name(garbled_mixed, 'FALLBACK')
        self.assertEqual(result, '1',
            'Filler characters must be stripped even when a real character is '
            'mixed in, not passed through whole once any \\w character is found')

    def test_sanitize_display_name_collapses_whitespace_left_by_filler(self):
        # Filler characters removed from the middle of a name must not leave
        # behind a run of bare spaces where they used to be word-separated.
        result = backend._sanitize_display_name('Анна ㅤ ㅤ Иванова', 'FALLBACK')
        self.assertEqual(result, 'Анна Иванова')

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
