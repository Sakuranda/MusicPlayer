"""音频下载（yt-dlp）与元数据写入（mutagen）。

流程：yt-dlp 抽音频(m4a) → 嵌入 标题/歌手/专辑/封面/歌词 → 移入曲库目录。
数据中心 IP 易触发 B 站 412，策略：注入真实 buvid 指纹 Cookie + 自动重试。
"""
import re
import time
from pathlib import Path

import httpx
import mutagen
from mutagen.mp4 import MP4, MP4Cover

from . import bilibili
from .config import COVER_DIR, MUSIC_DIR, BILI_HEADERS


def _safe(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len]


def write_cookie_file(cookie_str: str, path: Path) -> Path:
    """把浏览器复制的 Cookie 字符串转成 yt-dlp 用的 Netscape 格式文件。"""
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{k.strip()}\t{v.strip()}")
    path.write_text("\n".join(lines) + "\n")
    return path


def download_audio(bvid: str, cookie_file: Path | None = None, progress_hook=None) -> dict:
    """下载视频音频，返回 {file: 临时文件, duration: 秒, cover: 图片字节或 None}。

    策略：直连 DASH 音频（view→cid→playurl→CDN，不抓网页，绕开 412 网页风控）
         → 失败再回退 yt-dlp（带 buvid 指纹 + 重试）。
    """
    tmp = Path("/tmp") / f"ytdl-{bvid}"
    tmp.mkdir(exist_ok=True)

    cookie = None
    if cookie_file and cookie_file.exists():
        cookie = cookie_file.read_text(encoding="utf-8", errors="ignore")
        # 取原始 Cookie 串（我们写入时保留了 "k=v; k=v" 无法还原，直接传文件内容
        # 供 httpx 用需要还原格式，见 _cookie_str_from_netscape）
        cookie = _cookie_str_from_netscape(cookie)

    # 1) 直连 DASH（JSON API 路线，服务器 IP 已被验证可用）
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            return _direct_dash(bvid, cookie, tmp)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(3 * (attempt + 1))

    # 2) 回退 yt-dlp（网页路线，带指纹 Cookie，应对 412）
    import yt_dlp
    from yt_dlp.utils import DownloadError

    for attempt in range(2):
        try:
            return _ytdlp_download(bvid, cookie_file, progress_hook, tmp, attempt)
        except DownloadError as e:
            last_err = e
            time.sleep(8 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(8 * (attempt + 1))

    raise RuntimeError(f"下载失败（B 站风控，两条路线均已重试）: {last_err}")


def _cookie_str_from_netscape(text: str) -> str | None:
    """把 Netscape 格式 Cookie 文件还原成 k=v; k=v 字符串（bilibili 域）。"""
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 7 and "bilibili" in fields[0]:
            parts.append(f"{fields[5]}={fields[6]}")
    return "; ".join(parts) or None


def _direct_dash(bvid: str, cookie: str | None, tmp: Path) -> dict:
    """直连 DASH：view → playurl → CDN 下载 m4a。"""
    detail = bilibili.fetch_detail(bvid, cookie)
    cid = detail.get("cid") or (detail.get("pages") or [{}])[0].get("cid")
    if not cid:
        raise RuntimeError("视频没有可用的 cid")
    play = bilibili.fetch_playurl(bvid, cid, cookie)
    dash = play.get("dash") or {}
    audios = dash.get("audio") or []
    if not audios:
        raise RuntimeError("该视频没有 DASH 音频流")
    audio = max(audios, key=lambda a: a.get("id", 0))  # 30280 = 192k
    url = audio.get("baseUrl") or audio.get("base_url") or (audio.get("backupUrl") or [None])[0]
    if not url:
        raise RuntimeError("音频地址为空")

    dest = tmp / f"{bvid}.m4a"
    headers = {"User-Agent": BILI_HEADERS["User-Agent"], "Referer": "https://www.bilibili.com/"}
    with httpx.stream("GET", url, headers=headers, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)

    cover = None
    pic = detail.get("pic")
    if pic:
        try:
            r = httpx.get(pic, headers=headers, timeout=15)
            if r.status_code == 200:
                cover = r.content
        except Exception:
            cover = None
    return {"file": dest, "duration": float(detail.get("duration") or 0), "cover": cover}


def _ytdlp_download(bvid: str, cookie_file: Path | None, progress_hook, tmp: Path, attempt: int) -> dict:
    import yt_dlp

    # 合并用户 Cookie + 每次全新获取的 buvid 指纹（应对数据中心 IP 风控）
    merged = _merged_cookie_file(cookie_file, tmp, attempt)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "0",
            }
        ],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        # 批量下载时温柔一点，避免触发 B 站 412
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "sleep_requests": 0.5,
        "http_headers": {
            "User-Agent": BILI_HEADERS["User-Agent"],
            "Referer": "https://www.bilibili.com/",
        },
    }
    if merged:
        ydl_opts["cookiefile"] = str(merged)
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.bilibili.com/video/{bvid}", download=True)
        path = Path(ydl.prepare_filename(info))
        m4a = path.with_suffix(".m4a")
        if not m4a.exists():  # 某些情况下后缀不同
            candidates = [p for p in tmp.glob(f"{info['id']}*") if p.suffix in (".m4a", ".mp3", ".webm", ".m4s")]
            if not candidates:
                raise RuntimeError("未找到下载的音频文件")
            m4a = candidates[0]
        cover = None
        thumb = info.get("thumbnail")
        if thumb:
            try:
                r = httpx.get(thumb, headers=BILI_HEADERS, timeout=15)
                if r.status_code == 200:
                    cover = r.content
            except Exception:
                cover = None
        return {"file": m4a, "duration": float(info.get("duration") or 0), "cover": cover}


def _merged_cookie_file(cookie_file: Path | None, tmp: Path, attempt: int) -> Path | None:
    """用户 Cookie（若有）与 buvid 指纹合并为 Netscape 格式 Cookie 文件。"""
    buvids = bilibili.fetch_buvid()
    if cookie_file and cookie_file.exists():
        user_lines = cookie_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    else:
        user_lines = []
    lines = ["# Netscape HTTP Cookie File"] + user_lines
    for k, v in buvids.items():
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}")
    if len(lines) == 1:
        return None
    p = tmp / f"cookies-{attempt}.txt"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def tag_and_store(
    src: Path,
    title: str,
    artist: str,
    album: str,
    cover_bytes: bytes | None,
    bvid: str,
    lyrics_text: str | None = None,
) -> str:
    """写入元数据并移动到曲库目录，返回相对 MUSIC_DIR 的路径。"""
    try:
        audio = MP4(str(src))
        tags = audio.tags or {}
        tags["\xa9nam"] = title
        tags["\xa9ART"] = artist
        if album:
            tags["\xa9alb"] = album
        if cover_bytes:
            fmt = MP4Cover.FORMAT_PNG if cover_bytes[:8] == b"\x89PNG\r\n\x1a\n" else MP4Cover.FORMAT_JPEG
            tags["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
        if lyrics_text:
            tags["\xa9lyr"] = lyrics_text  # 内嵌歌词，客户端离线也能显示
        audio.save()
    except mutagen.MutagenError:
        pass  # 元数据失败不阻塞入库

    album_dir = MUSIC_DIR / _safe(album or "未分类")
    album_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe(f"{artist} - {title}")
    final = album_dir / f"{filename} [{bvid}].m4a"
    src.replace(final)
    return str(final.relative_to(MUSIC_DIR))


def write_lrc_sidecar(rel_path: str, lrc: str) -> None:
    """在音频旁写同名 .lrc 歌词文件（Navidrome/Amperfy 会读取）。"""
    if not lrc:
        return
    path = MUSIC_DIR / rel_path
    sidecar = path.with_suffix(".lrc")
    try:
        sidecar.write_text(lrc, encoding="utf-8")
    except OSError:
        pass


def save_cover(cover_bytes: bytes, bvid: str) -> str | None:
    """缓存封面文件，返回文件名。"""
    if not cover_bytes:
        return None
    name = f"{bvid}.jpg"
    (COVER_DIR / name).write_bytes(cover_bytes)
    return name
