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

def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """读取整数环境变量，并把危险配置限制在可接受范围内。"""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


# 下载并发是整个 API 进程共享的，不是“每个收藏夹各自拥有”。B 站在数据中心
# IP 上对高频请求较敏感，因此默认 3，且无论环境变量如何配置都不允许超过 5。
DOWNLOAD_THREADS = _bounded_int("DOWNLOAD_THREADS", 3, 1, 5)
METADATA_THREADS = _bounded_int("METADATA_THREADS", 4, 1, 8)

try:
    BILI_API_INTERVAL = max(0.25, float(os.environ.get("BILI_API_INTERVAL", "0.5")))
except ValueError:
    BILI_API_INTERVAL = 0.5

# 公网部署时建议设置 API 访问令牌（前端设置页里填同一个值）
API_TOKEN = os.environ.get("API_TOKEN", "")
