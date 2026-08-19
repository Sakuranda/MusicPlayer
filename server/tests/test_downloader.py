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


if __name__ == "__main__":
    unittest.main()
