import io
import unittest

from PIL import Image

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


if __name__ == "__main__":
    unittest.main()
