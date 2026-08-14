"""导入流水线：收藏夹解析入库 + 后台下载编排。"""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import bilibili, downloader, lyrics, parser
from .config import COOKIE_DIR, DOWNLOAD_THREADS
from .db import (create_job, get_conn, get_job, insert_song, list_songs,
                 update_job, update_song)


class ImportError(Exception):
    pass


def _cookie_file(media_id: str, cookie: str | None) -> Path | None:
    if not cookie:
        return None
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    path = COOKIE_DIR / f"{media_id}.txt"
    downloader.write_cookie_file(cookie, path)
    return path


def parse_and_store(url: str, cookie: str | None = None, album: str | None = None) -> str:
    """拉取收藏夹 → 解析标题 → 入库（status=pending），返回 job_id。"""
    conn = get_conn()
    media_ids = bilibili.parse_fav_url(url)
    fav_title, items, media_id = bilibili.fetch_favorites(media_ids, cookie)
    _cookie_file(media_id, cookie)
    if not items:
        raise ImportError("收藏夹是空的")

    job_id = uuid.uuid4().hex[:12]
    album = album or fav_title

    def enrich(item: dict) -> dict:
        item["tags"] = bilibili.fetch_tags(item["bvid"], cookie)
        return item

    with ThreadPoolExecutor(max_workers=8) as ex:
        items = list(ex.map(enrich, items))

    for item in items:
        song, artist = parser.parse_title(item["raw_title"], item["uploader"], item["tags"])
        insert_song(conn, {
            "bvid": item["bvid"],
            "job_id": job_id,
            "title": song,
            "artist": artist or item["uploader"] or "未知歌手",
            "album": album,
            "duration": item["duration"] or None,
            "raw_title": item["raw_title"],
            "uploader": item["uploader"],
            "tags": json.dumps(item["tags"], ensure_ascii=False),
            "cover_url": item["cover_url"],
        })

    create_job(conn, job_id, url, media_id, fav_title, len(items))
    return job_id


def _download_one(conn, song: dict, cookie_file: Path | None):
    sid = song["id"]
    try:
        update_song(conn, sid, status="downloading", error=None)

        # 歌词（下载前先匹配，失败也不阻塞）
        try:
            hit = lyrics.fetch_lyrics(song["title"], song["artist"], song["duration"] or 0)
            update_song(conn, sid, lyrics=hit["plain"], lrc=hit["lrc"],
                        lyrics_source=hit["source"])
        except Exception:
            pass

        result = downloader.download_audio(song["bvid"], cookie_file)
        rel = downloader.tag_and_store(
            result["file"], song["title"], song["artist"], song["album"],
            result["cover"], song["bvid"],
        )
        # 歌词侧车文件（Navidrome/Amperfy 读取同名 .lrc）
        lrc_text = song.get("lrc")
        if lrc_text:
            downloader.write_lrc_sidecar(rel, lrc_text)
        cover_name = downloader.save_cover(result["cover"], song["bvid"]) if result["cover"] else None
        update_song(conn, sid,
                    status="ready",
                    file_path=rel,
                    duration=song["duration"] or result["duration"],
                    cover_url=cover_name or song["cover_url"],
                    error=None)
        return True
    except Exception as e:  # noqa: BLE001
        update_song(conn, sid, status="error", error=str(e)[:500])
        return False
    finally:
        tmp = Path("/tmp") / f"ytdl-{song['bvid']}"
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


def start_download(job_id: str, bvids: list[str] | None = None):
    """后台线程：逐首下载。可指定 bvids 只下载勾选的歌曲。"""
    conn = get_conn()
    job = get_job(conn, job_id)
    if not job:
        raise ImportError("任务不存在")

    songs = list_songs(conn, job_id=job_id)
    if bvids:
        bv_set = set(bvids)
        songs = [s for s in songs if s["bvid"] in bv_set]
        update_job(conn, job_id, total=len(songs), done=0, failed=0, message="")
    else:
        # 失败的重试，已就绪的跳过
        songs = [s for s in songs if s["status"] != "ready"]
        update_job(conn, job_id, total=len(songs), done=0, failed=0, message="")

    if not songs:
        update_job(conn, job_id, status="done", message="没有需要下载的歌曲")
        return

    update_job(conn, job_id, status="downloading", message="开始下载")
    cookie_file = COOKIE_DIR / f"{job['media_id']}.txt"
    if not cookie_file.exists():
        cookie_file = None

    def worker(song):
        ok = _download_one(conn, song, cookie_file)
        conn.execute(
            "UPDATE jobs SET done = done + (CASE WHEN ? THEN 1 ELSE 0 END), "
            "failed = failed + (CASE WHEN ? THEN 0 ELSE 1 END) WHERE id = ?",
            (ok, ok, job_id),
        )
        conn.commit()
        return ok

    def run():
        ok_count = 0
        with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as ex:
            futs = [ex.submit(worker, s) for s in songs]
            for fut in as_completed(futs):
                try:
                    if fut.result():
                        ok_count += 1
                except Exception:
                    pass
        final = get_job(conn, job_id)
        status = "done" if final and final["failed"] == 0 else "done"
        update_job(conn, job_id, status=status,
                   message=f"完成：成功 {ok_count} 首，失败 {final['failed'] if final else '?'} 首")

    t = threading.Thread(target=run, daemon=True)
    t.start()
