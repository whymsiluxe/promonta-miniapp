import os
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402


class FeedPhotoIntegrityTests(unittest.TestCase):
    def test_list_feed_photos_hides_posts_without_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = os.path.join(tmp, 'keep.jpg')
            with open(keep, 'wb') as f:
                f.write(b'jpg')

            items = [
                {'id': 'missing', 'files': ['missing.jpg'], 'comments': [{'id': 'c1'}]},
                {'id': 'partial', 'files': ['keep.jpg', 'gone.jpg'], 'comments': []},
            ]
            with patch.object(backend, 'PHOTO_DIR', tmp), patch.object(backend, '_load_photo_meta', return_value=items):
                result = backend.list_feed_photos(user={'id': 1})

            self.assertEqual([p['id'] for p in result['photos']], ['partial'])
            self.assertEqual(result['photos'][0]['files'], ['keep.jpg'])
            self.assertEqual(result['photos'][0]['comment_count'], 0)


if __name__ == '__main__':
    unittest.main()
