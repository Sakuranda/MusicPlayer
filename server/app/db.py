"""SQLite 存储：歌曲与导入任务。"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DATA_DIR, MUSIC_DIR, COVER_DIR, DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    media_id    TEXT,
    title       TEXT,
    status      TEXT NOT NULL DEFAULT 'parsed',   -- parsed / downloading / done / error
    total       INTEGER NOT NULL DEFAULT 0,
    done        INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    message     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS songs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid        TEXT UNIQUE NOT NULL,
    job_id      TEXT,
    title       TEXT NOT NULL,          -- 歌曲名（解析结果，可编辑）
    artist      TEXT NOT NULL,          -- 歌手/UP主/标签
    album       TEXT,
    duration    REAL,
    raw_title   TEXT,
    uploader    TEXT,
    tags        TEXT,                   -- JSON 数组
    cover_url   TEXT,
    file_path   TEXT,                   -- 相对 MUSIC_DIR 的路径
    lyrics      TEXT,                   -- 纯文本歌词
    lrc         TEXT,                   -- 逐行时间轴歌词
    lyrics_source TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending/ready/error
    error       TEXT,
    created_at  TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with _lock:
        conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _song_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("tags"):
        try:
            d["tags"] = json.loads(d["tags"])
        except json.JSONDecodeError:
            d["tags"] = []
    d["cover"] = f"/api/songs/{d['id']}/cover" if d.get("cover_url") else None
    return d


# ---------- jobs ----------

def create_job(conn: sqlite3.Connection, job_id: str, url: str, media_id: str,
               title: str, total: int) -> None:
    conn.execute(
        "INSERT INTO jobs (id, url, media_id, title, status, total, created_at) "
        "VALUES (?,?,?,?, 'parsed', ?, ?)",
        (job_id, url, media_id, title, total, now()),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_job(conn: sqlite3.Connection, job_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", (*fields.values(), job_id))
    conn.commit()


# ---------- songs ----------

def insert_song(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        "INSERT OR REPLACE INTO songs "
        "(bvid, job_id, title, artist, album, duration, raw_title, uploader, tags, "
        " cover_url, status, created_at) "
        "VALUES (:bvid, :job_id, :title, :artist, :album, :duration, :raw_title, "
        ":uploader, :tags, :cover_url, 'pending', :created_at)",
        {**data, "created_at": now()},
    )
    conn.commit()
    return cur.lastrowid


def get_song(conn: sqlite3.Connection, sid: int) -> dict | None:
    row = conn.execute("SELECT * FROM songs WHERE id = ?", (sid,)).fetchone()
    return _song_row(row) if row else None


def list_songs(conn: sqlite3.Connection, job_id: str | None = None,
               status: str | None = None) -> list[dict]:
    q = "SELECT * FROM songs"
    conds, args = [], []
    if job_id:
        conds.append("job_id = ?")
        args.append(job_id)
    if status:
        conds.append("status = ?")
        args.append(status)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY id"
    rows = conn.execute(q, args).fetchall()
    return [_song_row(r) for r in rows]


def update_song(conn: sqlite3.Connection, sid: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE songs SET {sets} WHERE id = ?", (*fields.values(), sid))
    conn.commit()


def delete_song(conn: sqlite3.Connection, sid: int) -> dict | None:
    row = conn.execute("SELECT * FROM songs WHERE id = ?", (sid,)).fetchone()
    if row:
        conn.execute("DELETE FROM songs WHERE id = ?", (sid,))
        conn.commit()
        return _song_row(row)
    return None
