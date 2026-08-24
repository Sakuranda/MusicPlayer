"""SQLite 存储：歌曲与导入任务。"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DATA_DIR, MUSIC_DIR, COVER_DIR, DB_PATH

_lock = threading.Lock()
_initialized = False

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
    cid         INTEGER,                -- 选中的分P cid
    part_index  INTEGER DEFAULT 1,      -- 选中的第几P
    part_title  TEXT,                   -- 选中P的标题
    parts       TEXT,                   -- JSON: 全部分P [{cid,page,part,duration}]
    source_url  TEXT,                   -- B站视频完整链接（含分P参数）
    downloaded_cid INTEGER,             -- 实际下载过的分P cid（去重用）
    raw_title   TEXT,
    uploader    TEXT,
    tags        TEXT,                   -- JSON 数组
    cover_url   TEXT,
    file_path   TEXT,                   -- 相对 MUSIC_DIR 的路径
    lyrics      TEXT,                   -- 纯文本歌词
    lrc         TEXT,                   -- 逐行时间轴歌词
    lyrics_source TEXT,
    lyrics_enabled INTEGER NOT NULL DEFAULT 1, -- 是否自动匹配歌词
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending/ready/error
    error       TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_songs (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    song_id     INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (playlist_id, song_id)
);

CREATE INDEX IF NOT EXISTS idx_playlist_songs_order
ON playlist_songs (playlist_id, position, added_at);
"""

# 旧库迁移：补充分P相关列
MIGRATIONS = [
    "ALTER TABLE songs ADD COLUMN cid INTEGER",
    "ALTER TABLE songs ADD COLUMN part_index INTEGER DEFAULT 1",
    "ALTER TABLE songs ADD COLUMN part_title TEXT",
    "ALTER TABLE songs ADD COLUMN parts TEXT",
    "ALTER TABLE songs ADD COLUMN source_url TEXT",
    "ALTER TABLE songs ADD COLUMN downloaded_cid INTEGER",
    "ALTER TABLE songs ADD COLUMN lyrics_enabled INTEGER NOT NULL DEFAULT 1",
]


def get_conn() -> sqlite3.Connection:
    global _initialized
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 独立连接共享 WAL，写入冲突时最多等待 30 秒，而不是立即抛 database is locked。
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        with _lock:
            if not _initialized:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA)
                for stmt in MIGRATIONS:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
                        # 幂等迁移：仅忽略确定的“列已存在”，锁库/磁盘等错误必须暴露。
                conn.commit()
                _initialized = True
    except Exception:
        conn.close()
        raise
    return conn


def recover_interrupted_downloads(conn: sqlite3.Connection) -> tuple[int, int]:
    """服务重启后把无法继续的内存任务标成错误，避免永久显示“下载中”。"""
    song_cur = conn.execute(
        "UPDATE songs SET status = 'error', "
        "error = '服务重启中断了下载，请重新导入或再次开始任务' "
        "WHERE status = 'downloading'"
    )
    job_cur = conn.execute(
        "UPDATE jobs SET status = 'error', "
        "message = '服务重启中断了下载，请重新开始' "
        "WHERE status = 'downloading'"
    )
    conn.commit()
    return song_cur.rowcount, job_cur.rowcount


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _song_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("tags", "parts"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                d[key] = []
    d["cover"] = f"/api/songs/{d['id']}/cover" if d.get("cover_url") else None
    d["lyrics_enabled"] = bool(d.get("lyrics_enabled", 1))
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
    """插入歌曲；bvid 已存在时更新元数据，保留音频文件与歌词（重新导入不丢数据）。"""
    cur = conn.execute(
        "INSERT INTO songs "
        "(bvid, job_id, title, artist, album, duration, cid, part_index, part_title, parts, "
        " source_url, raw_title, uploader, tags, cover_url, status, created_at) "
        "VALUES (:bvid, :job_id, :title, :artist, :album, :duration, :cid, :part_index, "
        ":part_title, :parts, :source_url, :raw_title, :uploader, :tags, :cover_url, 'pending', :created_at) "
        "ON CONFLICT(bvid) DO UPDATE SET "
        "job_id=excluded.job_id, title=excluded.title, artist=excluded.artist, "
        "album=excluded.album, duration=excluded.duration, cid=excluded.cid, "
        "part_index=excluded.part_index, part_title=excluded.part_title, parts=excluded.parts, "
        "source_url=excluded.source_url, raw_title=excluded.raw_title, "
        "uploader=excluded.uploader, tags=excluded.tags, "
        "cover_url=CASE "
        "WHEN songs.cover_url IS NOT NULL AND songs.cover_url NOT LIKE 'http%' "
        "THEN songs.cover_url ELSE excluded.cover_url END",
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


# ---------- playlists ----------

def list_playlists(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT p.*, COUNT(ps.song_id) AS song_count "
        "FROM playlists p LEFT JOIN playlist_songs ps ON ps.playlist_id = p.id "
        "GROUP BY p.id ORDER BY p.created_at, p.id"
    ).fetchall()
    return [dict(row) for row in rows]


def create_playlist(conn: sqlite3.Connection, name: str) -> dict:
    cur = conn.execute(
        "INSERT INTO playlists (name, created_at) VALUES (?, ?)",
        (name, now()),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT p.*, 0 AS song_count FROM playlists p WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone())


def get_playlist(conn: sqlite3.Connection, playlist_id: int) -> dict | None:
    row = conn.execute(
        "SELECT p.*, COUNT(ps.song_id) AS song_count "
        "FROM playlists p LEFT JOIN playlist_songs ps ON ps.playlist_id = p.id "
        "WHERE p.id = ? GROUP BY p.id",
        (playlist_id,),
    ).fetchone()
    return dict(row) if row else None


def rename_playlist(conn: sqlite3.Connection, playlist_id: int, name: str) -> dict | None:
    conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))
    conn.commit()
    return get_playlist(conn, playlist_id)


def delete_playlist(conn: sqlite3.Connection, playlist_id: int) -> bool:
    cur = conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()
    return cur.rowcount > 0


def list_playlist_songs(conn: sqlite3.Connection, playlist_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT s.* FROM playlist_songs ps "
        "JOIN songs s ON s.id = ps.song_id "
        "WHERE ps.playlist_id = ? ORDER BY ps.position, ps.added_at, s.id",
        (playlist_id,),
    ).fetchall()
    return [_song_row(row) for row in rows]


def add_song_to_playlist(conn: sqlite3.Connection, playlist_id: int, song_id: int) -> bool:
    position = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_songs WHERE playlist_id = ?",
        (playlist_id,),
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT OR IGNORE INTO playlist_songs "
        "(playlist_id, song_id, position, added_at) VALUES (?, ?, ?, ?)",
        (playlist_id, song_id, position, now()),
    )
    conn.commit()
    return cur.rowcount > 0


def remove_song_from_playlist(conn: sqlite3.Connection, playlist_id: int, song_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM playlist_songs WHERE playlist_id = ? AND song_id = ?",
        (playlist_id, song_id),
    )
    conn.commit()
    return cur.rowcount > 0
