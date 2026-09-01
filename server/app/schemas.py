"""Pydantic 请求/响应模型。"""
from typing import Optional

from pydantic import BaseModel


class ImportRequest(BaseModel):
    url: str
    cookie: Optional[str] = None       # 收藏夹为私密时需提供 B 站 Cookie
    album: Optional[str] = None        # 专辑名，默认取收藏夹标题
    save_collection: bool = False      # 保存链接，供手动/自动增量更新
    auto_update: bool = False          # 每 24 小时自动同步并下载新增歌曲


class SongUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    cid: Optional[int] = None          # 选中的分P
    part_index: Optional[int] = None
    part_title: Optional[str] = None
    duration: Optional[float] = None   # 选中P的时长
    lyrics_enabled: Optional[bool] = None


class StartRequest(BaseModel):
    # 可选：只下载部分 bvid（用户勾选）
    bvids: Optional[list[str]] = None
    fetch_lyrics: bool = True


class PlaylistWrite(BaseModel):
    name: str


class CollectionUpdate(BaseModel):
    auto_update: Optional[bool] = None
    fetch_lyrics: Optional[bool] = None


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha: str
