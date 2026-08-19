import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import importer
from app.db import SCHEMA, update_song


class DownloadQueueTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "queue.db"
        conn = self.get_conn()
        conn.execute(
            "INSERT INTO jobs (id, url, media_id, title, status, total, created_at) "
            "VALUES ('job','https://example.com','123','测试','parsed',12,'now')"
        )
        for index in range(12):
            conn.execute(
                "INSERT INTO songs (bvid, job_id, title, artist, status, created_at) "
                "VALUES (?,?,?,?, 'pending','now')",
                (f"BV{index:010d}", "job", f"歌曲{index}", "歌手"),
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tempdir.cleanup()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        return conn

    def test_partial_job_is_bounded_idempotent_and_completes(self):
        state_lock = threading.Lock()
        active = 0
        max_active = 0

        def fake_download(conn, song, _cookie_file):
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            update_song(conn, song["id"], status="ready", error=None)
            with state_lock:
                active -= 1
            return True

        selected = [f"BV{index:010d}" for index in range(7)]
        with (
            patch.object(importer, "get_conn", side_effect=self.get_conn),
            patch.object(importer, "_download_one", side_effect=fake_download),
        ):
            started = importer.start_download("job", selected, fetch_lyrics=False)
            duplicate = importer.start_download("job", selected, fetch_lyrics=False)
            self.assertTrue(started["started"])
            self.assertEqual(started["queued"], 7)
            self.assertFalse(duplicate["started"])

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                conn = self.get_conn()
                job = conn.execute("SELECT * FROM jobs WHERE id='job'").fetchone()
                conn.close()
                if job["status"] == "done":
                    break
                time.sleep(0.02)
            else:
                self.fail("下载队列未在超时前完成")

        self.assertLessEqual(max_active, importer.DOWNLOAD_THREADS)
        self.assertEqual(job["total"], 7)
        self.assertEqual(job["done"], 7)
        self.assertEqual(job["failed"], 0)

        conn = self.get_conn()
        remaining = conn.execute("SELECT COUNT(*) FROM songs WHERE status='pending'").fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 5)


if __name__ == "__main__":
    unittest.main()
