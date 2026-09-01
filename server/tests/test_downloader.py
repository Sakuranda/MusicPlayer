import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import downloader
from app.downloader import optimize_cover


class CoverOptimizationTests(unittest.TestCase):
    def test_large_png_becomes_small_jpeg(self):
        source = io.BytesIO()
        Image.new("RGB", (1600, 900), "#d97757").save(source, format="PNG")

        result = optimize_cover(source.getvalue())

        self.assertIsNotNone(result)
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 320)
        self.assertLess(len(result), len(source.getvalue()))

    def test_invalid_cover_is_discarded(self):
        self.assertIsNone(optimize_cover(b"not-an-image"))


class CookieFileTests(unittest.TestCase):
    def test_cookie_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookie.txt"
            downloader.write_cookie_file("SESSDATA=secret; bili_jct=csrf", path)

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn("SESSDATA\tsecret", path.read_text())


class MetadataTests(unittest.TestCase):
    def test_empty_tag_container_is_created_and_album_can_be_removed(self):
        class FakeAudio:
            def __init__(self):
                self.tags = None
                self.saved = False

            def add_tags(self):
                self.tags = {"\xa9alb": ["旧专辑"]}

            def save(self):
                self.saved = True

        fake = FakeAudio()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            downloader, "MP4", return_value=fake
        ):
            path = Path(tmp) / "song.m4a"
            path.touch()
            downloader.update_audio_metadata(path, title="新歌名", album="")

        self.assertEqual(fake.tags["\xa9nam"], "新歌名")
        self.assertNotIn("\xa9alb", fake.tags)
        self.assertTrue(fake.saved)


class DirectDashTests(unittest.TestCase):
    def test_known_cid_survives_blocked_detail_api(self):
        fake_info = {"ext": "m4a"}

        class FakeYDL:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download):
                self.download = download
                return fake_info

            def prepare_filename(self, _info):
                return str(target)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "BVTEST.m4a"
            target.write_bytes(b"audio")
            with (
                patch.object(downloader.bilibili, "fetch_detail", side_effect=RuntimeError("HTTP 412")),
                patch.object(downloader.bilibili, "fetch_playurl", return_value={
                    "dash": {"audio": [{"id": 30280, "baseUrl": "https://cdn/audio.m4s"}]},
                }) as playurl,
                patch("yt_dlp.YoutubeDL", FakeYDL),
            ):
                result = downloader._direct_dash("BVTEST", None, Path(tmp), cid=9988)

        playurl.assert_called_once_with("BVTEST", 9988, None)
        self.assertEqual(result["duration"], 0.0)


if __name__ == "__main__":
    unittest.main()
