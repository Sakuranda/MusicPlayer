import sqlite3
import unittest
from unittest.mock import patch

from app import main
from app.db import SCHEMA, insert_song, recover_interrupted_downloads


def song_data(**overrides):
    data = {
        "bvid": "BVTEST",
        "job_id": "job-new",
        "title": "歌名",
        "artist": "歌手",
        "album": "专辑",
        "duration": 120,
        "cid": 1,
        "part_index": 1,
        "part_title": "P1",
        "parts": None,
        "source_url": "https://www.bilibili.com/video/BVTEST",
        "raw_title": "原标题",
        "uploader": "UP",
        "tags": "[]",
        "cover_url": "https://example.com/cover.jpg",
    }
    data.update(overrides)
    return data


class DataSafetyTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_reimport_preserves_local_cover(self):
        sid = insert_song(self.conn, song_data(cover_url="BVTEST.jpg"))
        self.conn.execute(
            "UPDATE songs SET file_path = ?, status = 'ready' WHERE id = ?",
            ("专辑/歌.m4a", sid),
        )
        self.conn.commit()

        insert_song(self.conn, song_data(cover_url="https://example.com/new-large.jpg"))

        row = self.conn.execute("SELECT cover_url FROM songs WHERE id = ?", (sid,)).fetchone()
        self.assertEqual(row["cover_url"], "BVTEST.jpg")

    def test_cancel_reimport_keeps_ready_song_and_removes_new_preview(self):
        self.conn.execute(
            "INSERT INTO jobs (id, url, status, total, created_at) "
            "VALUES ('job-new','https://example.com','parsed',2,'now')"
        )
        ready_id = insert_song(self.conn, song_data())
        self.conn.execute(
            "UPDATE songs SET file_path = '专辑/歌.m4a', status = 'ready' WHERE id = ?",
            (ready_id,),
        )
        insert_song(self.conn, song_data(bvid="BVNEW", title="新歌"))
        self.conn.commit()

        with patch.object(main, "get_conn", return_value=self.conn):
            result = main.job_delete("job-new")

        self.assertEqual(result, {"deleted": True})
        ready = self.conn.execute("SELECT job_id FROM songs WHERE id = ?", (ready_id,)).fetchone()
        self.assertIsNotNone(ready)
        self.assertIsNone(ready["job_id"])
        self.assertIsNone(self.conn.execute("SELECT 1 FROM songs WHERE bvid='BVNEW'").fetchone())

    def test_restart_marks_in_memory_downloads_as_interrupted(self):
        self.conn.execute(
            "INSERT INTO jobs (id, url, status, total, created_at) "
            "VALUES ('job','https://example.com','downloading',1,'now')"
        )
        insert_song(self.conn, song_data(job_id="job"))
        self.conn.execute("UPDATE songs SET status='downloading'")
        self.conn.commit()

        recovered = recover_interrupted_downloads(self.conn)

        self.assertEqual(recovered, (1, 1))
        self.assertEqual(self.conn.execute("SELECT status FROM songs").fetchone()[0], "error")
        self.assertEqual(self.conn.execute("SELECT status FROM jobs").fetchone()[0], "error")


if __name__ == "__main__":
    unittest.main()
