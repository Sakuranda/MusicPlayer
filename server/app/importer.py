"""导入流水线：收藏夹解析入库 + 后台下载编排。"""
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import bilibili, downloader, lyrics, parser
from .config import COOKIE_DIR, DOWNLOAD_THREADS, METADATA_THREADS
from .db import (create_job, get_conn, get_job, insert_song, list_songs,
                 update_job, update_song)

logger = logging.getLogger("uvicorn.error")


class ImportError(Exception):
    pass


# 所有收藏夹共享同一个下载执行器。旧实现会为每个任务新建线程池，两个收藏夹
# 同时启动时会把并发数翻倍；同一任务重复点击还可能重复下载同一首歌。
_download_executor = ThreadPoolExecutor(
    max_workers=DOWNLOAD_THREADS,
    thread_name_prefix="music-download",
)
_active_lock = threading.Lock()
_active_jobs: set[str] = set()
_active_song_ids: set[int] = set()


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
        # 视频详情：获取分P信息（cid、每P标题与时长）
        item["parts"] = []
        item["cid"] = None
        item["part_index"] = 1
        item["part_title"] = None
        try:
            detail = bilibili.fetch_detail(item["bvid"], cookie)
            pages = detail.get("pages") or []
            if pages:
                item["parts"] = [
                    {
                        "cid": p.get("cid"),
                        "page": p.get("page", i + 1),
                        "part": p.get("part") or f"P{i + 1}",
                        "duration": p.get("duration") or 0,
                    }
                    for i, p in enumerate(pages)
                ]
                first = item["parts"][0]
                item["cid"] = first["cid"]
                item["part_index"] = 1
                item["part_title"] = first["part"]
                item["duration"] = first["duration"] or item["duration"]
            elif detail.get("cid"):
                item["cid"] = detail["cid"]
                item["parts"] = [{
                    "cid": detail["cid"], "page": 1, "part": "P1",
                    "duration": detail.get("duration") or item["duration"],
                }]
                item["duration"] = detail.get("duration") or item["duration"]
                item["part_index"] = 1
                item["part_title"] = "P1"
        except Exception:
            pass  # 详情拉不到不阻塞导入，下载时再报错
        return item

    with ThreadPoolExecutor(max_workers=METADATA_THREADS) as ex:
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
            "cid": item["cid"],
            "part_index": item["part_index"],
            "part_title": item["part_title"],
            "parts": json.dumps(item["parts"], ensure_ascii=False) if item["parts"] else None,
            "source_url": f"https://www.bilibili.com/video/{item['bvid']}?p={item['part_index']}",
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

        # 用户上传的歌词优先且永不被自动匹配覆盖。旧实现更新数据库后仍读取
        # song 旧快照，导致侧车与内嵌标签没有歌词；这里显式保留本次结果。
        lyric_plain = song.get("lyrics") or ""
        lrc_text = song.get("lrc") or ""
        lyric_source = song.get("lyrics_source") or ""
        if song.get("lyrics_enabled", True) and lyric_source != "upload":
            try:
                hit = lyrics.fetch_lyrics(song["title"], song["artist"], song["duration"] or 0)
                lyric_plain = hit["plain"]
                lrc_text = hit["lrc"]
                lyric_source = hit["source"]
                update_song(conn, sid, lyrics=lyric_plain, lrc=lrc_text,
                            lyrics_source=lyric_source)
            except Exception:
                pass

        result = downloader.download_audio(
            song["bvid"], cookie_file,
            cid=song.get("cid"),
            part_index=song.get("part_index") or 1,
        )
        cover_bytes = downloader.optimize_cover(result["cover"])
        rel = downloader.tag_and_store(
            result["file"], song["title"], song["artist"], song["album"],
            cover_bytes, song["bvid"], lrc_text or lyric_plain or None,
        )
        # 歌词侧车文件（Navidrome/Amperfy 读取同名 .lrc）
        if lrc_text:
            downloader.write_lrc_sidecar(rel, lrc_text)
        cover_name = downloader.save_cover(cover_bytes, song["bvid"]) if cover_bytes else None
        update_song(conn, sid,
                    status="ready",
                    file_path=rel,
                    duration=song["duration"] or result["duration"],
                    cover_url=cover_name or song["cover_url"],
                    downloaded_cid=song.get("cid"),
                    error=None)
        old_rel = song.get("file_path")
        if old_rel and old_rel != rel:
            old_path = downloader.MUSIC_DIR / old_rel
            try:
                old_path.unlink(missing_ok=True)
                old_path.with_suffix(".lrc").unlink(missing_ok=True)
            except OSError:
                pass
        return True
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:500]
        # B 站原始报错补充说明，方便排查
        if "bad parameter" in msg:
            msg = "B 站接口限流或参数被拒（瞬时可恢复）：" + msg
        logger.error("歌曲下载失败 sid=%s bvid=%s: %s", sid, song["bvid"], msg, exc_info=True)
        update_song(conn, sid, status="error", error=msg)
        return False
    finally:
        tmp = Path("/tmp") / f"ytdl-{song['bvid']}"
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


def start_download(job_id: str, bvids: list[str] | None = None,
                   fetch_lyrics: bool = True):
    """把歌曲加入进程级共享队列；可指定 bvids 只下载勾选的歌曲。

    返回本次是否真正启动及排队数量。同一任务正在执行时重复调用是幂等的，
    不会再提交一批重复 future。
    """
    conn = get_conn()
    job = get_job(conn, job_id)
    if not job:
        raise ImportError("任务不存在")

    all_songs = list_songs(conn, job_id=job_id)
    if bvids is not None:
        if not bvids:
            raise ImportError("请至少选择一首歌曲")
        bv_set = set(bvids)
        selected = [s for s in all_songs if s["bvid"] in bv_set]
    else:
        selected = all_songs

    if not selected:
        raise ImportError("所选歌曲不属于该任务")

    skipped = [
        s for s in selected
        if s["status"] == "ready"
        and (s.get("downloaded_cid") is None or s.get("downloaded_cid") == s.get("cid"))
    ]
    songs = [s for s in selected if s not in skipped]

    with _active_lock:
        if job_id in _active_jobs:
            return {
                "started": False,
                "queued": 0,
                "concurrency": DOWNLOAD_THREADS,
                "message": "任务已在下载队列中",
            }
        conflicts = [s for s in songs if s["id"] in _active_song_ids]
        if conflicts:
            raise ImportError("部分歌曲已在另一个下载任务中，请等待其完成")
        _active_jobs.add(job_id)
        _active_song_ids.update(s["id"] for s in songs)

    if not songs:
        update_job(
            conn,
            job_id,
            status="done",
            total=len(selected),
            done=len(skipped),
            failed=0,
            message=f"全部 {len(skipped)} 首均已下载，已跳过",
        )
        with _active_lock:
            _active_jobs.discard(job_id)
        return {
            "started": False,
            "queued": 0,
            "concurrency": DOWNLOAD_THREADS,
            "message": "所选歌曲均已下载",
        }

    song_ids = [s["id"] for s in songs]
    for sid in song_ids:
        update_song(conn, sid, status="pending", error=None,
                    lyrics_enabled=int(fetch_lyrics))
    for song in songs:
        song["lyrics_enabled"] = fetch_lyrics
    update_job(
        conn,
        job_id,
        status="downloading",
        total=len(selected),
        done=len(skipped),
        failed=0,
        message=f"已排队 {len(songs)} 首，全局并发 {DOWNLOAD_THREADS}",
    )
    cookie_file = COOKIE_DIR / f"{job['media_id']}.txt"
    if not cookie_file.exists():
        cookie_file = None

    def worker(song):
        # 每个线程用独立的数据库连接，避免并发提交事务互相冲突
        worker_conn = get_conn()
        try:
            return _download_one(worker_conn, song, cookie_file)
        finally:
            worker_conn.close()

    def run():
        try:
            futs = [_download_executor.submit(worker, s) for s in songs]
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("下载 worker 异常 job=%s: %s", job_id, exc, exc_info=True)
                _recount_selected(conn, job_id, [s["id"] for s in selected], final=False)

            # 第二批只重试“本次选择且本轮失败”的歌曲，避免把旧任务错误混进来。
            retry = []
            for sid in song_ids:
                row = conn.execute("SELECT * FROM songs WHERE id = ?", (sid,)).fetchone()
                if row and row["status"] == "error":
                    retry.append(dict(row))
            if retry:
                time.sleep(15)
                update_job(conn, job_id, message=f"自动重试 {len(retry)} 首失败的歌…")
                futs = [_download_executor.submit(worker, s) for s in retry]
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.error("重试 worker 异常 job=%s: %s", job_id, exc, exc_info=True)
                    _recount_selected(conn, job_id, [s["id"] for s in selected], final=False)

            _recount_selected(conn, job_id, [s["id"] for s in selected], final=True)
        except Exception as exc:  # noqa: BLE001
            update_job(conn, job_id, status="error", message=f"下载调度异常：{str(exc)[:300]}")
        finally:
            conn.close()
            with _active_lock:
                _active_jobs.discard(job_id)
                _active_song_ids.difference_update(song_ids)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {
        "started": True,
        "queued": len(songs),
        "concurrency": DOWNLOAD_THREADS,
        "message": f"已排队 {len(songs)} 首",
    }


def _recount_selected(conn, job_id: str, song_ids: list[int], final: bool) -> None:
    """只按本次选择重算进度，避免部分下载时任务永远无法完成。"""
    if not song_ids:
        return
    marks = ",".join("?" for _ in song_ids)
    rows = conn.execute(
        f"SELECT status, COUNT(*) AS n FROM songs WHERE id IN ({marks}) GROUP BY status",
        song_ids,
    ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}
    done = counts.get("ready", 0)
    failed = counts.get("error", 0)
    total = len(song_ids)
    status = "done" if final else "downloading"
    message = (
        f"完成：成功 {done} 首，失败 {failed} 首"
        if final
        else f"下载中：成功 {done} 首，失败 {failed} 首，全局并发 {DOWNLOAD_THREADS}"
    )
    update_job(conn, job_id, status=status, total=total, done=done, failed=failed, message=message)


def is_job_active(job_id: str) -> bool:
    with _active_lock:
        return job_id in _active_jobs


def is_song_active(song_id: int) -> bool:
    with _active_lock:
        return song_id in _active_song_ids
