# 🎵 MusicPlayer — B站收藏夹歌曲库

粘贴一个 Bilibili（B站）收藏夹链接，自动完成：

1. **解析收藏夹** — 获取收藏夹内所有视频
2. **提取元数据** — 从标题/标签智能解析歌曲名与歌手（针对虚拟主播翻唱优化）
3. **获取歌词** — 自动匹配歌词（LRCLIB / 网易云等源）
4. **下载音频** — 服务器端抽取音频（yt-dlp / DASH）
5. **在线播放** — 美观的网页播放器 + iOS App 在线收听（Navidrome / Subsonic 协议）

## 架构

```
┌─────────────┐   ┌──────────────────────────────────┐   ┌──────────────┐
│  网页播放器   │──▶│  hk 服务器 (Docker)                │──▶│  iOS App      │
│  React 前端  │   │  ├─ api: FastAPI 后端(解析/下载/歌词) │   │  Amperfy 等   │
└─────────────┘   │  ├─ music: Navidrome 曲库(Subsonic) │   └──────────────┘
                  │  └─ 音频文件存储                     │
                  └──────────────────────────────────┘
```

- **web/** — React + Vite 前端（播放器、歌词、导入界面）
- **server/** — FastAPI 后端（B站解析、元数据提取、yt-dlp 下载、歌词匹配、曲库 API）
- **docker-compose.yml** — 服务器部署编排（api + navidrome + caddy）

## 本地开发

```bash
# 后端
cd server && pip install -r requirements.txt && uvicorn app.main:app --reload

# 前端
cd web && pnpm install && pnpm dev
```

## 服务器部署

```bash
ssh hk
git clone <repo> /opt/musicplayer
cd /opt/musicplayer
cp deploy/.env.example deploy/.env  # 编辑配置
docker compose up -d
```

- 网页: `http://45.125.33.88:8080`
- iOS (Subsonic): `http://45.125.33.88:4533`
