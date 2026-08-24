import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db


class DatabaseConnectionTests(unittest.TestCase):
    def test_connections_use_wal_and_wait_for_busy_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with patch.multiple(
                db,
                DATA_DIR=data_dir,
                MUSIC_DIR=data_dir / "music",
                COVER_DIR=data_dir / "covers",
                DB_PATH=data_dir / "musicplayer.db",
                _initialized=False,
            ):
                first = db.get_conn()
                second = db.get_conn()
                try:
                    self.assertEqual(first.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                    self.assertEqual(second.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
                    self.assertEqual(second.execute("PRAGMA synchronous").fetchone()[0], 1)
                    columns = {
                        row[1] for row in second.execute("PRAGMA table_info(songs)").fetchall()
                    }
                    self.assertIn("lyrics_enabled", columns)
                    tables = {
                        row[0] for row in second.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        ).fetchall()
                    }
                    self.assertIn("playlists", tables)
                    self.assertIn("access_sessions", tables)
                finally:
                    first.close()
                    second.close()

    def test_initialization_does_not_hide_real_migration_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with patch.multiple(
                db,
                DATA_DIR=data_dir,
                MUSIC_DIR=data_dir / "music",
                COVER_DIR=data_dir / "covers",
                DB_PATH=data_dir / "musicplayer.db",
                MIGRATIONS=["ALTER TABLE missing_table ADD COLUMN value TEXT"],
                _initialized=False,
            ):
                with self.assertRaises(sqlite3.OperationalError):
                    db.get_conn()


if __name__ == "__main__":
    unittest.main()
