"""全局配置。"""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
MUSIC_DIR = DATA_DIR / "music"      # Navidrome 扫描此目录
COVER_DIR = DATA_DIR / "covers"     # 封面缓存
COOKIE_DIR = DATA_DIR / "cookies"   # 用户粘贴的 B 站 Cookie（Netscape 格式）
DB_PATH = DATA_DIR / "musicplayer.db"

# 常见浏览器请求头，避免 B 站接口反爬
BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

DOWNLOAD_THREADS = int(os.environ.get("DOWNLOAD_THREADS", "3"))

# 公网部署时建议设置 API 访问令牌（前端设置页里填同一个值）
API_TOKEN = os.environ.get("API_TOKEN", "")
