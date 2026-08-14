# 🎵 MusicPlayer — B站收藏夹歌曲库

粘贴一个 Bilibili（B站）收藏夹链接，自动完成：

1. **解析收藏夹** — 获取收藏夹内所有视频（公开列表免登录，私密列表粘贴 Cookie）
2. **提取元数据** — 从标题/标签智能解析歌曲名与歌手（针对虚拟主播翻唱优化，可预览修改）
3. **获取歌词** — LRCLIB → 网易云 → QQ 音乐 三级降级匹配，支持逐行时间轴
4. **下载音频** — yt-dlp 抽取 192k AAC（B站 UGC 最高音质），自动写入标题/歌手/专辑/封面/歌词标签
5. **在线播放** — 美观的网页播放器（歌词滚动高亮）+ iOS 免费 App「Amperfy」在线收听

## 架构

```
┌─────────────┐   ┌──────────────────────────────────┐   ┌──────────────┐
│  网页播放器   │──▶│  hk 服务器 (Docker)                │──▶│  iOS App      │
│  React 前端  │   │  ├─ api: FastAPI(解析/下载/歌词/网页) │   │  Amperfy 等   │
└─────────────┘   │  ├─ navidrome: 曲库服务(Subsonic)   │   │  (免费/国区)   │
                  │  └─ 音频 + .lrc 歌词文件             │   └──────────────┘
                  └──────────────────────────────────┘
```

- **web/** — React + Vite + Tailwind v4 前端（播放器、歌词、导入界面）
- **server/** — FastAPI 后端（B站解析、元数据提取、yt-dlp 下载、歌词匹配、曲库 API）
- **docker-compose.yml** — 服务器部署编排（api + navidrome + caddy 可选 HTTPS）

## 本地开发

```bash
# 后端（需要 ffmpeg 与 Python 3.11+）
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8080

# 前端（自动代理 /api → localhost:8080）
cd web
pnpm install && pnpm dev
```

## 服务器部署（hk）

```bash
# 1. 首次：配置免密登录（或手动 ssh hk）
#    ~/.ssh/config 中已有 Host hk（45.125.33.88:63195）

# 2. 一键部署
./deploy/deploy.sh
# 等效于：ssh hk → git clone 到 /opt/musicplayer → docker compose up -d --build

# 3. 首次创建 Navidrome 账号（iOS 用）
ssh hk
curl -X POST "http://localhost:4533/auth/createAdmin?username=YOUR_NAME&password=YOUR_PASS"
```

访问：

| 用途 | 地址 |
|---|---|
| 网页播放器（HTTPS，推荐） | `https://music.sakuranda.site` |
| 网页播放器（裸 IP 直连） | `http://45.125.33.88:8080` |
| iOS 曲库服务 (Subsonic) | `http://45.125.33.88:4533` |

> `music.sakuranda.site` 由服务器上的系统级 Caddy（`/etc/caddy/`）反代到 8080。

### iOS 播放（Amperfy）

1. App Store（国区）下载免费的 [Amperfy](https://apps.apple.com/cn/app/amperfy-music/id1530145038)
2. 添加服务器：协议 **Subsonic**，地址 `http://45.125.33.88:4533`
3. 填 Navidrome 账号密码（即上一步 createAdmin 创建的用户）
4. 支持在线播放、歌词（.lrc）、离线缓存、CarPlay

### 可选：HTTPS（免费域名）

裸 IP + HTTP 已可用（Amperfy 支持 http://IP）。想上 HTTPS：

1. 注册免费域名：`xxx.duckdns.org`（指向服务器 IP）或直接用 `45.125.33.88.sslip.io`
2. 编辑 `deploy/Caddyfile` 里的域名
3. `ssh hk "cd /opt/musicplayer && docker compose --profile https up -d"`
4. Caddy 自动申请/续期 Let's Encrypt 证书，iOS 填 `https://navi.xxx.duckdns.org`

## API Token（安全）

服务器部署时会自动生成随机 `API_TOKEN`（存于服务器 `deploy/.env`）。
网页「设置」页里填同一个值。不想用可把 `.env` 中 `API_TOKEN=` 留空并重启。

## 常见问题

- **私密收藏夹**：导入页展开「粘贴 B 站 Cookie」，填浏览器里的 `SESSDATA=...` 即可
- **下载失败 412**：B 站风控。稍等几分钟重试；服务器网络出口质量影响较大
- **歌词没有**：翻唱曲目在歌词库里常查不到，属正常情况，可手动改歌名后重试下载
- **磁盘**：服务器剩余 ~13GB，每首歌约 2-6MB（192k AAC），数千首无压力

## 调研依据

- B 站 API 实测报告：[bilibili-research-report.md](bilibili-research-report.md)
  （收藏夹 API 免登录、media_id = fid + UP主uid后两位、CDN 需 Referer 等）
- iOS 方案实测：Navidrome（v0.63+，支持 .lrc 侧车歌词）+ Amperfy（免费、国区、歌词/CarPlay）
