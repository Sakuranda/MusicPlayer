"""Pydantic 请求/响应模型。"""
from typing import Optional

from pydantic import BaseModel


class ImportRequest(BaseModel):
    url: str
    cookie: Optional[str] = None       # 收藏夹为私密时需提供 B 站 Cookie
    album: Optional[str] = None        # 专辑名，默认取收藏夹标题


class SongUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None


class StartRequest(BaseModel):
    # 可选：只下载部分 bvid（用户勾选）
    bvids: Optional[list[str]] = None
