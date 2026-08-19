"""MusicPlayer API — FastAPI 入口。"""
import csv
import io
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .bilibili import BiliError
from .config import API_TOKEN, COVER_DIR, MUSIC_DIR
from .db import (delete_song, get_conn, get_job, get_song, list_jobs,
                 list_songs, update_song)
from .importer import (ImportError, is_job_active, is_song_active,
                       parse_and_store, start_download)
from .schemas import ImportRequest, SongUpdate, StartRequest

app = FastAPI(title="MusicPlayer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_token_guard(request: Request, call_next):
    """设置了 API_TOKEN 时，要求 X-Api-Token 请求头或 ?token= 参数（health 除外）。"""
    if API_TOKEN and request.url.path.startswith("/api") and request.url.path != "/api/health":
        token = request.headers.get("X-Api-Token") or request.query_params.get("token")
        if token != API_TOKEN:
            return JSONResponse({"detail": "需要有效的 API Token"}, status_code=401)
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "musicplayer"}


# ---------- 导入任务 ----------

@app.post("/api/jobs")
def create_job(req: ImportRequest):
    """粘贴收藏夹链接 → 解析标题 → 返回预览（不下载）。"""
    try:
        job_id = parse_and_store(req.url, req.cookie, req.album)
    except (ImportError, BiliError) as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logging.getLogger("uvicorn.error").exception("导入失败 url=%r", req.url)
        raise HTTPException(502, f"解析失败：{e}") from e
    conn = get_conn()
    return {"job": get_job(conn, job_id), "songs": list_songs(conn, job_id=job_id)}


@app.get("/api/jobs")
def jobs():
    conn = get_conn()
    return list_jobs(conn)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    conn = get_conn()
    job = get_job(conn, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return {"job": job, "songs": list_songs(conn, job_id=job_id)}


@app.post("/api/jobs/{job_id}/start")
def job_start(job_id: str, req: StartRequest | None = None):
    """确认元数据后开始下载（可只下载勾选的 bvid）。"""
    conn = get_conn()
    if not get_job(conn, job_id):
        raise HTTPException(404, "任务不存在")
    try:
        result = start_download(job_id, req.bvids if req else None)
    except ImportError as e:
        raise HTTPException(400, str(e)) from e
    return result


@app.delete("/api/jobs/{job_id}")
def job_delete(job_id: str):
    conn = get_conn()
    if not get_job(conn, job_id):
        raise HTTPException(404, "任务不存在")
    if is_job_active(job_id):
        raise HTTPException(409, "任务正在下载，完成后才能删除")
    for s in list_songs(conn, job_id=job_id):
        _remove_file(s)
        conn.execute("DELETE FROM songs WHERE id = ?", (s["id"],))
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    return {"deleted": True}


# ---------- 歌曲 ----------

@app.get("/api/songs")
def songs(status: str | None = None):
    conn = get_conn()
    return list_songs(conn, status=status)


@app.get("/api/export.csv")
def export_csv():
    """导出全曲库为 CSV（含 B 站视频链接），方便备份与去重核对。"""
    conn = get_conn()
    all_songs = list_songs(conn)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "歌曲名", "歌手", "专辑", "bvid", "B站视频链接", "分P", "时长(秒)", "状态", "歌词来源"])
    for s in all_songs:
        w.writerow([
            s["id"], s["title"], s["artist"], s.get("album") or "",
            s["bvid"], s.get("source_url") or f"https://www.bilibili.com/video/{s['bvid']}",
            s.get("part_index") or 1, s.get("duration") or "", s["status"],
            s.get("lyrics_source") or "",
        ])
    # UTF-8 BOM，Excel 打开中文不乱码
    return Response(
        content=("\ufeff" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=musicplayer-songs.csv"},
    )


@app.get("/api/songs/{sid}")
def song_detail(sid: int):
    conn = get_conn()
    song = get_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    return song


@app.patch("/api/songs/{sid}")
def song_update(sid: int, req: SongUpdate):
    conn = get_conn()
    song = get_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    update_song(conn, sid, **fields)
    _retag_file(song, fields)
    return get_song(conn, sid)


def _retag_file(song: dict, fields: dict) -> None:
    """把改动的元数据写回音频文件标签（Navidrome/iOS 同步）。"""
    if not song.get("file_path"):
        return
    path = MUSIC_DIR / song["file_path"]
    if not path.exists():
        return
    try:
        from mutagen.mp4 import MP4
        audio = MP4(str(path))
        tags = audio.tags or {}
        if fields.get("title"):
            tags["\xa9nam"] = fields["title"]
        if fields.get("artist"):
            tags["\xa9ART"] = fields["artist"]
        if fields.get("album"):
            tags["\xa9alb"] = fields["album"]
        audio.save()
    except Exception:  # noqa: BLE001
        pass  # 标签写入失败不影响数据库更新


@app.delete("/api/songs/{sid}")
def song_delete(sid: int):
    conn = get_conn()
    if is_song_active(sid):
        raise HTTPException(409, "歌曲正在下载，完成后才能删除")
    song = delete_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    _remove_file(song)
    return {"deleted": True}


# ---------- 媒体 ----------

@app.get("/api/stream/{sid}")
def stream(sid: int):
    conn = get_conn()
    song = get_song(conn, sid)
    if not song or not song.get("file_path"):
        raise HTTPException(404, "音频不存在")
    path = MUSIC_DIR / song["file_path"]
    if not path.exists():
        raise HTTPException(404, "音频文件丢失")
    return FileResponse(path, media_type="audio/mp4",
                        filename=f"{song['artist']} - {song['title']}.m4a")


@app.get("/api/songs/{sid}/cover")
def cover(sid: int):
    conn = get_conn()
    song = get_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    if song.get("cover_url") and not str(song["cover_url"]).startswith("http"):
        path = COVER_DIR / song["cover_url"]
        if path.exists():
            return FileResponse(path, media_type="image/jpeg")
    if song.get("cover_url"):
        return RedirectResponse(song["cover_url"])
    raise HTTPException(404, "无封面")


def _remove_file(song: dict) -> None:
    if song.get("file_path"):
        p = MUSIC_DIR / song["file_path"]
        try:
            p.unlink(missing_ok=True)
            p.with_suffix(".lrc").unlink(missing_ok=True)
        except OSError:
            pass
    if song.get("cover_url") and not str(song["cover_url"]).startswith("http"):
        try:
            (COVER_DIR / song["cover_url"]).unlink(missing_ok=True)
        except OSError:
            pass


# 托管前端静态文件（必须在所有 /api 路由之后挂载）
WEB_DIST = os.environ.get("WEB_DIST", "")
if WEB_DIST and Path(WEB_DIST).is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True, check_dir=False), name="web")
