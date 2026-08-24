"""MusicPlayer API — FastAPI 入口。"""
import csv
import io
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .bilibili import BiliError
from .config import API_TOKEN, COVER_DIR, MUSIC_DIR
from .db import (add_song_to_playlist, create_playlist, delete_playlist,
                 delete_song, get_conn, get_job, get_playlist, get_song,
                 list_jobs, list_playlist_songs, list_playlists, list_songs,
                 recover_interrupted_downloads, remove_song_from_playlist,
                 rename_playlist, update_song)
from . import downloader, lyrics
from .importer import (ImportError, is_job_active, is_song_active,
                       parse_and_store, start_download)
from .schemas import ImportRequest, PlaylistWrite, SongUpdate, StartRequest

@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = get_conn()
    try:
        recovered_songs, recovered_jobs = recover_interrupted_downloads(conn)
        if recovered_songs or recovered_jobs:
            logging.getLogger("uvicorn.error").warning(
                "已恢复中断状态：songs=%d jobs=%d", recovered_songs, recovered_jobs
            )
    finally:
        conn.close()
    yield


app = FastAPI(title="MusicPlayer API", version="0.2.0", lifespan=lifespan)

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
        result = start_download(
            job_id,
            req.bvids if req else None,
            req.fetch_lyrics if req else True,
        )
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
        # 取消重复导入时，已有歌曲也会暂时归到新 job。绝不能因此删除已下载
        # 文件；只移除这次新建且尚无文件的预览记录。
        if s.get("file_path") or s["status"] == "ready":
            conn.execute("UPDATE songs SET job_id = NULL WHERE id = ?", (s["id"],))
        else:
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


@app.put("/api/songs/{sid}/lyrics")
async def song_lyrics_upload(sid: int, file: UploadFile = File(...)):
    """上传 UTF-8/UTF-16/GB18030 的 .lrc 或 .txt 歌词。"""
    conn = get_conn()
    song = get_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".lrc", ".txt"):
        raise HTTPException(400, "只支持 .lrc 或 .txt 歌词文件")
    data = await file.read(1024 * 1024 + 1)
    await file.close()
    try:
        text = lyrics.decode_lyrics_file(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    plain = lyrics.lrc_to_plain(text) or text.strip()
    update_song(
        conn,
        sid,
        lyrics=plain,
        lrc=text,
        lyrics_source="upload",
        lyrics_enabled=1,
    )
    if song.get("file_path"):
        downloader.write_lrc_sidecar(song["file_path"], text)
        downloader.update_embedded_lyrics(song["file_path"], text)
    return get_song(conn, sid)


@app.delete("/api/songs/{sid}/lyrics")
def song_lyrics_delete(sid: int):
    """删除数据库、侧车文件和音频标签中的歌词。"""
    conn = get_conn()
    song = get_song(conn, sid)
    if not song:
        raise HTTPException(404, "歌曲不存在")
    update_song(conn, sid, lyrics=None, lrc=None, lyrics_source=None)
    if song.get("file_path"):
        downloader.remove_lrc_sidecar(song["file_path"])
        downloader.update_embedded_lyrics(song["file_path"], None)
    return get_song(conn, sid)


def _retag_file(song: dict, fields: dict) -> None:
    """把改动的元数据写回音频文件标签（Navidrome/iOS 同步）。"""
    if not song.get("file_path"):
        return
    path = MUSIC_DIR / song["file_path"]
    if not path.exists():
        return
    try:
        downloader.update_audio_metadata(
            path,
            title=fields.get("title") if "title" in fields else None,
            artist=fields.get("artist") if "artist" in fields else None,
            album=fields.get("album") if "album" in fields else None,
        )
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


# ---------- 歌单 ----------

def _playlist_name(name: str) -> str:
    clean = " ".join(name.strip().split())
    if not clean:
        raise HTTPException(400, "歌单名称不能为空")
    if len(clean) > 80:
        raise HTTPException(400, "歌单名称不能超过 80 个字符")
    return clean


@app.get("/api/playlists")
def playlists():
    conn = get_conn()
    return list_playlists(conn)


@app.post("/api/playlists", status_code=201)
def playlist_create(req: PlaylistWrite):
    conn = get_conn()
    try:
        return create_playlist(conn, _playlist_name(req.name))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "已经有同名歌单") from exc


@app.patch("/api/playlists/{playlist_id}")
def playlist_rename(playlist_id: int, req: PlaylistWrite):
    conn = get_conn()
    if not get_playlist(conn, playlist_id):
        raise HTTPException(404, "歌单不存在")
    try:
        return rename_playlist(conn, playlist_id, _playlist_name(req.name))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "已经有同名歌单") from exc


@app.delete("/api/playlists/{playlist_id}")
def playlist_delete(playlist_id: int):
    conn = get_conn()
    if not delete_playlist(conn, playlist_id):
        raise HTTPException(404, "歌单不存在")
    return {"deleted": True}


@app.get("/api/playlists/{playlist_id}/songs")
def playlist_songs(playlist_id: int):
    conn = get_conn()
    if not get_playlist(conn, playlist_id):
        raise HTTPException(404, "歌单不存在")
    return list_playlist_songs(conn, playlist_id)


@app.post("/api/playlists/{playlist_id}/songs/{sid}")
def playlist_song_add(playlist_id: int, sid: int):
    conn = get_conn()
    if not get_playlist(conn, playlist_id):
        raise HTTPException(404, "歌单不存在")
    if not get_song(conn, sid):
        raise HTTPException(404, "歌曲不存在")
    added = add_song_to_playlist(conn, playlist_id, sid)
    return {"added": added}


@app.delete("/api/playlists/{playlist_id}/songs/{sid}")
def playlist_song_remove(playlist_id: int, sid: int):
    conn = get_conn()
    if not get_playlist(conn, playlist_id):
        raise HTTPException(404, "歌单不存在")
    removed = remove_song_from_playlist(conn, playlist_id, sid)
    return {"removed": removed}


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
