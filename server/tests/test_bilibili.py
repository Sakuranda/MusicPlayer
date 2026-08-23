import unittest

import httpx

from app.bilibili import BiliError, _response_json


class BilibiliResponseTest(unittest.TestCase):
    def test_http_error_is_translated(self):
        response = httpx.Response(503, text="service unavailable")

        with self.assertRaisesRegex(BiliError, "HTTP 503"):
            _response_json(response, "获取收藏夹")

    def test_invalid_json_is_translated(self):
        response = httpx.Response(200, text="<html>blocked</html>")

        with self.assertRaisesRegex(BiliError, "无法解析"):
            _response_json(response, "获取收藏夹")


if __name__ == "__main__":
    unittest.main()
