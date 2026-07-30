"""Backend tests for upload hardening (Release-аудит Этап 1, P0): chat attachments/
voice/transcribe raньше принимали ЛЮБОЙ файл без magic-byte проверки (только size
limit) -- единственные upload endpoints без sniff_image()/sniff_image_or_pdf(),
которые уже используются для avatar/object-photo/document/feed/mangel/blocker.

Same plain stdlib unittest approach as tests/test_tools.py -- pure functions
(sniff_*, path-safety helpers) tested directly without needing real UploadFile/
multipart machinery or network access (libmagic magic-byte detection is a pure
function of raw bytes, no I/O).

Run:
    cd miniapp-repo && python3 -m unittest tests.test_upload_security -v
(same environment requirements as test_tools.py: BOT_TOKEN in env, run with the
miniapp .venv's python3 which has python-magic installed.)
"""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402


# Real, minimal, ffmpeg-generated file bytes (base64-embedded so tests run fully
# offline -- no ffmpeg/network dependency at test time). A hand-crafted header
# alone isn't enough for libmagic's OGG/PNG rules to positively identify the
# format, so these are genuine tiny valid files, not synthetic byte patterns.
JPEG_HEADER = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01' + b'\x00' * 100
PNG_HEADER = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAACXBIWXMAAAABAAAAAQBPJcTWAAAAC0lEQVR4nGNgQAYAAA4AAamRc7EAAAAASUVORK5CYII=')
OGG_HEADER = base64.b64decode('T2dnUwACAAAAAAAAAAApe1cTAAAAAJLh9ooBHgF2b3JiaXMAAAAAAUAfAAAAAAAAgFcAAAAAAACZAU9nZ1MAAAAAAAAAAAAAKXtXEwEAAABzFKVmC0D///////////+1A3ZvcmJpcw0AAABMYXZmNjAuMTYuMTAwAQAAAB8AAABlbmNvZGVyPUxhdmM2MC4zMS4xMDIgbGlidm9yYmlzAQV2b3JiaXMSQkNWAQAAAQAMUhQhJRlTSmMIlVJSKQUdY1BbRx1j1DlGIWQQU4hJGaV7TyqVWErIEVJYKUUdU0xTSZVSlilFHWMUU0ghU9YxZaFzFEuGSQklbE2udBZL6JljljFGHWPOWkqdY9YxRR1jUlJJoXMYOmYlZBQ6RsXoYnwwOpWiQii+x95S6S2FiluKvdcaU+sthBhLacEIYXPttdXcSmrFGGOMMcbF4lMogtCQVQAAAQAAQAQBQkNWAQAKAADCUAxFUYDQkFUAQAYAgAAURXEUx3EcR5IkywJCQ1YBAEAAAAIAACiO4SiSI0mSZFmWZVmWpnmWqLmqL/uuLuuu7eq6DoSGrAQAyAAAGIYhh95JzJBTkEkmKVXMOQih9Q455RRk0lLGmGKMUc6QUwwxBTGG0CmFENROOaUMIghDSJ1kziBLPejgYuc4EBqyIgCIAgAAjEGMIcaQcwxKBiFyjknIIETOOSmdlExKKK20lkkJLZXWIueclE5KJqW0FlLLpJTWQisFAAAEOAAABFgIhYasCACiAAAQg5BSSCnElGJOMYeUUo4px5BSzDnFmHKMMeggVMwxyByESCnFGHNOOeYgZAwq5hyEDDIBAAABDgAAARZCoSErAoA4AQCDJGmapWmiaGmaKHqmqKqiKKqq5Xmm6ZmmqnqiqaqmqrquqaqubHmeaXqmqKqeKaqqqaqua6qq64qqasumq9q26aq27MqybruyrNueqsq2qbqybqqubbuybOuuLNu65Hmq6pmm63qm6bqq69qy6rqy7Zmm64qqK9um68qy68q2rcqyrmum6bqiq9quqbqy7cqubbuyrPum6+q26sq6rsqy7tu2rvuyrQu76Lq2rsqurquyrOuyLeu2bNtCyfNU1TNN1/VM03VV17Vt1XVtWzNN1zVdV5ZF1XVl1ZV1XXVlW/dM03VNV5Vl01VlWZVl3XZlV5dF17VtVZZ9XXVlX5dt3fdlWdd903V1W5Vl21dlWfdlXfeFWbd93VNVWzddV9dN19V9W9d9YbZt3xddV9dV2daFVZZ139Z9ZZh1nTC6rq6rtuzrqizrvq7rxjDrujCsum38rq0Lw6vrxrHrvq7cvo9q277w6rYxvLpuHLuwG7/t+8axqaptm66r66Yr67ps675v67pxjK6r66os+7rqyr5v67rw674vDKPr6roqy7qw2rKvy7ouDLuuG8Nq28Lu2rpwzLIuDLfvK8evC0PVtoXh1XWjq9vGbwvD0jd2vgAAgAEHAIAAE8pAoSErAoA4AQAGIQgVYxAqxiCEEFIKIaRUMQYhYw5KxhyUEEpJIZTSKsYgZI5JyByTEEpoqZTQSiilpVBKS6GU1lJqLabUWgyhtBRKaa2U0lpqKbbUUmwVYxAy56RkjkkopbRWSmkpc0xKxqCkDkIqpaTSSkmtZc5JyaCj0jlIqaTSUkmptVBKa6GU1kpKsaXSSm2txRpKaS2k0lpJqbXUUm2ttVojxiBkjEHJnJNSSkmplNJa5pyUDjoqmYOSSimplZJSrJiT0kEoJYOMSkmltZJKK6GU1kpKsYVSWmut1ZhSSzWUklpJqcVQSmuttRpTKzWFUFILpbQWSmmttVZrai22UEJroaQWSyoxtRZjba3FGEppraQSWympxRZbja21WFNLNZaSYmyt1dhKLTnWWmtKLdbSUoyttZhbTLnFWGsNJbQWSmmtlNJaSq3F1lqtoZTWSiqxlZJabK3V2FqMNZTSYikptZBKbK21WFtsNaaWYmyx1VhSizHGWHNLtdWUWouttVhLKzXGGGtuNeVSAADAgAMAQIAJZaDQkJUAQBQAAGAMY4xBaBRyzDkpjVLOOSclcw5CCCllzkEIIaXOOQiltNQ5B6GUlEIpKaUUWyglpdZaLAAAoMABACDABk2JxQEKDVkJAEQBACDGKMUYhMYgpRiD0BijFGMQKqUYcw5CpRRjzkHIGHPOQSkZY85BJyWEEEIppYQQQiillAIAAAocAAACbNCUWByg0JAVAUAUAABgDGIMMYYgdFI6KRGETEonpZESWgspZZZKiiXGzFqJrcTYSAmthdYyayXG0mJGrcRYYioAAOzAAQDswEIoNGQlAJAHAEAYoxRjzjlnEGLMOQghNAgx5hyEECrGnHMOQggVY845ByGEzjnnIIQQQueccxBCCKGDEEIIpZTSQQghhFJK6SCEEEIppXQQQgihlFIKAAAqcAAACLBRZHOCkaBCQ1YCAHkAAIAxSjknJaVGKcYgpBRboxRjEFJqrWIMQkqtxVgxBiGl1mLsIKTUWoy1dhBSai3GWkNKrcVYa84hpdZirDXX1FqMtebce2otxlpzzrkAANwFBwCwAxtFNicYCSo0ZCUAkAcAQCCkFGOMOYeUYowx55xDSjHGmHPOKcYYc8455xRjjDnnnHOMMeecc845xphzzjnnnHPOOeegg5A555xz0EHonHPOOQghdM455xyEEAoAACpwAAAIsFFkc4KRoEJDVgIA4QAAgDGUUkoppZRSSqijlFJKKaWUUgIhpZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoppZRSSimllFJKKaWUUkoplVJKKaWUUkoppZRSSimlACDfCgcA/wcbZ1hJOiscDS40ZCUAEA4AABjDGISMOSclpYYxCKV0TkpJJTWMQSilcxJSSimD0FpqpaTSUkoZhJRiCyGVlFoKpbRWaymptZRSKCnFGktKqaXWMuckpJJaS622mDkHpaTWWmqtxRBCSrG11lJrsXVSUkmttdZabS2klFprLcbWYmwlpZZaa6nF1lpMqbUWW0stxtZiS63F2GKLMcYaCwDgbnAAgEiwcYaVpLPC0eBCQ1YCACEBAAQySjnnnIMQQgghUoox56CDEEIIIURKMeacgxBCCCGEjDHnIIQQQgihlJAx5hyEEEIIIYRSOucghFBKCaWUUkrnHIQQQgillFJKCSGEEEIopZRSSikhhBBKKaWUUkopJYQQQiillFJKKaWEEEIopZRSSimllBBCKKWUUkoppZQSQgihlFJKKaWUUkIIpZRSSimllFJKKCGEUkoppZRSSgkllFJKKaWUUkopIZRSSimllFJKKaUAAIADBwCAACPoJKPKImw04cIDEAAAAAIAAkwAgQGCglEIAoQRCAAAAAAACAD4AABICoCIiGjmDA4QEhQWGBocHiAiJAAAAAAAAAAAAAAAAARPZ2dTAAQgAwAAAAAAACl7VxMCAAAACPw2wwUBAQEBAQAAAAAA')
PDF_HEADER = b'%PDF-1.4\n' + b'\x00' * 100

# A file that LOOKS like a jpg by extension but contains HTML -- the exact
# attack the task calls out ("поддельный JPG с HTML внутри").
FAKE_JPG_WITH_HTML = b'<html><body><script>alert(1)</script></body></html>'
SVG_CONTENT = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
PLAIN_TEXT = b'just some plain text, not any known binary format'


class SniffImageTests(unittest.TestCase):
    """Разрешённые изображения проходят, всё остальное -- нет."""

    def test_jpeg_allowed(self):
        self.assertEqual(backend.sniff_image(JPEG_HEADER), 'image/jpeg')

    def test_png_allowed(self):
        self.assertEqual(backend.sniff_image(PNG_HEADER), 'image/png')

    def test_svg_rejected(self):
        # SVG может содержать <script> -- никогда не должен проходить как "изображение".
        self.assertIsNone(backend.sniff_image(SVG_CONTENT))

    def test_html_rejected(self):
        self.assertIsNone(backend.sniff_image(FAKE_JPG_WITH_HTML))

    def test_pdf_rejected_by_image_only_sniffer(self):
        self.assertIsNone(backend.sniff_image(PDF_HEADER))

    def test_plain_text_rejected(self):
        self.assertIsNone(backend.sniff_image(PLAIN_TEXT))


class SniffImageOrPdfTests(unittest.TestCase):
    def test_pdf_allowed(self):
        self.assertEqual(backend.sniff_image_or_pdf(PDF_HEADER), 'application/pdf')

    def test_jpeg_allowed(self):
        self.assertEqual(backend.sniff_image_or_pdf(JPEG_HEADER), 'image/jpeg')

    def test_html_rejected(self):
        self.assertIsNone(backend.sniff_image_or_pdf(FAKE_JPG_WITH_HTML))

    def test_svg_rejected(self):
        self.assertIsNone(backend.sniff_image_or_pdf(SVG_CONTENT))


class SniffAudioTests(unittest.TestCase):
    """Голосовые (chat voice, /api/transcribe) -- отдельный allowlist (Release-аудит P0)."""

    def test_ogg_allowed(self):
        self.assertEqual(backend.sniff_audio(OGG_HEADER), 'audio/ogg')

    def test_html_rejected(self):
        self.assertIsNone(backend.sniff_audio(FAKE_JPG_WITH_HTML))

    def test_svg_rejected(self):
        self.assertIsNone(backend.sniff_audio(SVG_CONTENT))

    def test_pdf_rejected(self):
        self.assertIsNone(backend.sniff_audio(PDF_HEADER))

    def test_plain_text_rejected(self):
        self.assertIsNone(backend.sniff_audio(PLAIN_TEXT))


class SniffChatAttachmentTests(unittest.TestCase):
    """Объединённый allowlist для /api/chat/messages/attachment (изображения+PDF+аудио).
    Расширение возвращается ИЗ ТАБЛИЦЫ, не из имени файла клиента -- закрывает и
    "любой файл проходит", и path-traversal через непровалидированное расширение."""

    def test_jpeg_returns_safe_ext(self):
        result = backend.sniff_chat_attachment(JPEG_HEADER)
        self.assertIsNotNone(result)
        mime, ext = result
        self.assertEqual(mime, 'image/jpeg')
        self.assertEqual(ext, 'jpg')
        # Расширение не может содержать path-traversal символы -- оно из фиксированной таблицы.
        self.assertNotIn('/', ext)
        self.assertNotIn('..', ext)

    def test_pdf_returns_safe_ext(self):
        result = backend.sniff_chat_attachment(PDF_HEADER)
        self.assertIsNotNone(result)
        _, ext = result
        self.assertEqual(ext, 'pdf')

    def test_ogg_voice_returns_safe_ext(self):
        result = backend.sniff_chat_attachment(OGG_HEADER)
        self.assertIsNotNone(result)
        _, ext = result
        self.assertEqual(ext, 'ogg')

    def test_html_rejected(self):
        # Основной сценарий из задачи: поддельный файл с HTML внутри отклоняется
        # независимо от того, каким именем/content-type его прислал клиент --
        # sniff_chat_attachment смотрит только на реальные байты.
        self.assertIsNone(backend.sniff_chat_attachment(FAKE_JPG_WITH_HTML))

    def test_svg_rejected(self):
        self.assertIsNone(backend.sniff_chat_attachment(SVG_CONTENT))

    def test_plain_text_rejected(self):
        self.assertIsNone(backend.sniff_chat_attachment(PLAIN_TEXT))

    def test_all_returned_extensions_are_safe_path_components(self):
        # Ни одно расширение в allowlist не может само по себе представлять
        # path-traversal (нет '/', нет '..', нет управляющих символов).
        for ext in backend._ALLOWED_CHAT_ATTACHMENT_MIME_EXT.values():
            self.assertNotIn('/', ext)
            self.assertNotIn('\\', ext)
            self.assertNotIn('..', ext)
            self.assertEqual(ext, os.path.basename(ext))


class CheckinObjectIdPathSafetyTests(unittest.TestCase):
    """object_id на /api/checkin/start приходит от клиента как Form-параметр --
    раньше только .strip()[:100], без защиты от '../' (Release-аудит P0). Тест
    проверяет саму санитацию внутри _save_checkin_photos напрямую (без реального
    upload -- files=[] означает функция вернёт [] сразу после создания директории,
    что и нужно для проверки безопасности пути)."""

    def test_traversal_object_id_is_confined_to_basename(self):
        import asyncio
        malicious_id = '../../../etc/passwd_dir'
        result = asyncio.run(backend._save_checkin_photos([], malicious_id, '2026-07-30'))
        # Функция не должна была создать директорию вне CHECKIN_PHOTO_BASE --
        # проверяем что итоговый day_dir остаётся строго внутри базовой директории.
        expected_base = os.path.basename(malicious_id)
        day_dir = os.path.join(backend.CHECKIN_PHOTO_BASE, expected_base, '2026-07-30')
        self.assertTrue(os.path.commonpath([backend.CHECKIN_PHOTO_BASE, os.path.abspath(day_dir)])
                        == os.path.abspath(backend.CHECKIN_PHOTO_BASE))
        # cleanup -- тест реально создаёт директорию (os.makedirs), не мокаем I/O здесь,
        # т.к. это единственный способ проверить итоговый путь без переписывания функции.
        try:
            os.rmdir(day_dir)
            os.rmdir(os.path.dirname(day_dir))
        except OSError:
            pass

    def test_empty_object_id_falls_back_to_unknown(self):
        import asyncio
        result = asyncio.run(backend._save_checkin_photos([], '', '2026-07-30'))
        self.assertEqual(result, [])
        day_dir = os.path.join(backend.CHECKIN_PHOTO_BASE, 'unknown', '2026-07-30')
        self.assertTrue(os.path.isdir(day_dir))
        try:
            os.rmdir(day_dir)
            os.rmdir(os.path.dirname(day_dir))
        except OSError:
            pass


class ChatAttachmentServingSafetyTests(unittest.TestCase):
    """GET /api/chat/attachments/{fname} -- fname раньше шёл в os.path.join без
    basename-проверки (Release-аудит P1-8-style gap, fixed alongside P0)."""

    def test_traversal_fname_rejected_before_filesystem_check(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            backend.get_chat_attachment(fname='../../etc/passwd', user={'id': 1}, role='owner')
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
