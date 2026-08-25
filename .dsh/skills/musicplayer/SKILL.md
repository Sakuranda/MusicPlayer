---
name: musicplayer
description: MusicPlayer 项目专属技能 —— B站收藏夹歌曲库（FastAPI + React + Navidrome）。在开发、调试、部署、修复 Bug、添加功能、调整标题解析器、处理 B 站风控、运维 hk 服务器时使用。加载本技能可瞬间获得该项目的架构、约定、历史踩坑与标准工作流。
whenToUse: 任务涉及 MusicPlayer 仓库、music.sakuranda.site、B站收藏夹/音频/歌词、hk 服务器、Navidrome/Amperfy、或该项目任何代码时。
---

# MusicPlayer 项目技能

B站收藏夹歌曲库。仓库：`https://github.com/Sakuranda/MusicPlayer`，本机工作区 `/Users/sakuranda/temp/MusicPlayer`。
先读仓库根目录 `AGENTS.md`（项目记忆），本技能是它的 DSH 版速览 + 工作流。

## 架构速览

```
web/        React + Vite + Tailwind v4 前端（曲库/导入/播放器歌词/设置）
server/     FastAPI 后端（bilibili.py 解析、parser.py 标题解析、downloader.py 下载、lyrics.py 歌词、importer.py 流水线、db.py SQLite）
docker-compose.yml   api(8080, 含网页静态托管) + navidrome(4533, Subsonic) + caddy(profile https, 备用)
deploy/     部署脚本与环境模板
docs/       使用指南 / 部署运维 / API 参考
bilibili-research-report.md   B站 API 实测调研（media_id 公式、412 对策、歌词源）
```

生产环境：hk 服务器 `ssh hk`（45.125.33.88:63195，密钥 `~/.ssh/id_ed25519_hk`）
- 部署目录 `/opt/musicplayer`，数据 `/opt/musicplayer/data/`（musicplayer.db、music/、covers/、cookies/、navidrome/）
- 容器：`musicplayer-api`、`musicplayer-navidrome`
- 域名 `https://music.sakuranda.site`（系统级 Caddy `/etc/caddy/sites-enabled/` 反代 8080）
- API Token：`d0689adf8786539510fc906531076ac7`（存于服务器 deploy/.env）
- Navidrome 账号：sakuranda / MusicPlayer2026（http://45.125.33.88:4533）

## 关键事实（务必记住）

1. **media_id 双形态**：`space.bilibili.com/{mid}/favlist?fid={x}` 的 fid 有时是 media_id 本身、有时要按 `fid + mid后两位` 换算 —— `parse_fav_url` 返回两个候选，`fetch_favorites` 依次尝试，哪个有数据用哪个。不要只信一种公式。
2. **私密收藏夹**：B 站返回 `code=0 + data=null`（不是 -403）。必须带用户 Cookie（SESSDATA）。Cookie 存 `data/cookies/{media_id}.txt`（Netscape 格式），下载时还原为 k=v 串 + 合并 buvid3/buvid4 指纹。
3. **下载双路线**：DASH 直连（view→cid→playurl→CDN 直链给 yt-dlp generic 下载，`Referer: https://www.bilibili.com/` 必需，否则 CDN 403）→ 失败回退 yt-dlp 网页路线。数据中心 IP 会吃 412 / "bad parameter or other API misuse"（限流）—— 所有任务共享全局下载队列（默认 3、硬上限 5）和 API 请求间隔，另有多级等待重试 + 批次结束后自动重试一轮失败项。
4. **音质上限 192k AAC**（B 站 UGC 没有 320k）。曲库保留源 AAC/M4A，不为格式偏好二次编码；这是空间、音质和 iOS/Navidrome 兼容性的最佳平衡。封面只存最大 320px 的压缩 JPEG。
5. **多P支持**：`songs.cid/part_index/part_title/parts` + `source_url`（B站链接）+ `downloaded_cid`（去重）。下载指定 P 用其 cid；重复导入时已下载且分P未变的自动跳过。
6. **数据库**：SQLite，`db.get_conn()` 每次建新连接并执行 SCHEMA + MIGRATIONS（ALTER TABLE 容错）。**线程必须各用各的连接**（曾因共享连接并发提交报 "cannot commit - no transaction is active"）。加列必须同时加进 SCHEMA 和 MIGRATIONS。
7. **歌词三级降级**：LRCLIB（带 duration 参数+模糊匹配）→ 网易云（GET 参数、无头可用）→ QQ 音乐（需 y.qq.com Referer），共享全局限速与进程缓存。翻唱曲目查不到是常态。导入可关闭自动查询；用户上传的 `.lrc/.txt` 优先且不可被自动匹配覆盖，并同步 DB、`.lrc` 侧车、MP4 `©lyr` 标签。
8. **标题解析**（parser.py）：信号优先级 = 《》「」书名号（歌名）＞ 标题切分（含"歌手 - 歌名"逆序、YOASOBI 等原唱歌手名单排除）＞ 标签挖歌名（排除噪音词/原唱歌手名单/运营活动词）＞ 英文短语提取。歌手 = 【】人名（呜米x咩栗 取前者、阿梓歌→阿梓）＞ 标签主播名聚类（阿梓/阿梓从小就很可爱）＞ UP主。启发式不可能全对 —— 预览可编辑是设计的一部分，不要过度调参。

## 标准工作流

**修 bug / 加功能**：
1. 改代码（后端 `server/app/`、前端 `web/src/`）
2. 本地验证：后端 `cd server && .venv/bin/python -c "..."`；前端 `cd web && pnpm build`
3. 提交推送：`git add -A && git commit -m "..." && git push origin main`
4. 部署：`ssh hk 'cd /opt/musicplayer && git pull -q --ff-only && docker compose up -d --build'`
5. 公网验证：`curl http://45.125.33.88:8080/api/health`（带 Token 的请求加 `-H "X-Api-Token: d0689..."`）

**⚠️ 部署会中断正在跑的下载**（容器重建几秒）。部署前先查任务状态：`curl http://45.125.33.88:8080/api/jobs -H "X-Api-Token: ..."`。若中断后卡了「下载中」的歌，复位：
```bash
ssh hk 'docker exec musicplayer-api python -c "
import sqlite3
c = sqlite3.connect(\"/data/musicplayer.db\")
c.execute(\"UPDATE songs SET status=\x27pending\x27, error=NULL WHERE status=\x27downloading\x27\")
c.commit()"'
```
然后 POST /api/jobs/{id}/start 继续。前端已有 502 自动重试，但能不打断就不打断（用户在用的时候先打招呼）。

**调标题解析器**：用真实数据回归测试（脚本模式：本地用 httpx + Cookie 拉收藏夹 → parse_title 全量对比），同时跑早期用例防回归。用户收藏夹：`https://space.bilibili.com/19468476/favlist?fid=4112724176`（musicplayer，40首，私密需 Cookie）。

**排查下载失败**：`docker logs musicplayer-api --tail 100`；歌曲级错误存在 DB 的 songs.error；任务进度从 songs 表重算（`_recount`）。

## 历史踩坑（本项目独有的教训）

- media_id 只信一种公式 → 私密收藏夹永远返回空数据
- 编辑对象初始化空字符串覆盖原始歌名（`??` 不挡 `''`）
- StrictMode 下 setState 回调里带副作用 → onEnded 重构成 effect
- `/tmp` 与 `/data` 跨文件系统 → 移动文件必须 `shutil.move`
- 共享 SQLite 连接并发提交冲突 → 每线程独立 `get_conn()`
- 管道 `cmd | tail && deploy` 吞掉失败退出码 → 重要命令别接管道
- B 站 CDN 直链无 Referer 必 403；网页抓取路线数据中心 IP 吃 412 → DASH 直连是主路线
- 部署时机撞上用户操作 → 502 误报，前端加重试 + 服务端重算统计兜底
- ssh 嵌套引号 heredoc 易碎 → 长脚本走 `docker exec -i ... python < 本地文件`
- 每个收藏夹各建线程池会让并发随任务数倍增，同一任务重复启动还会重复提交 → 使用进程级共享执行器、活跃任务/歌曲集合，并按本次选择重算进度
- AAC 转 MP3 会增加体积或损失音质；iOS/网页/Navidrome 原生支持 M4A → 保留源 AAC/M4A，只压缩封面并清理重下产生的旧路径文件
- 歌词查询后只更新 DB、继续读 worker 的旧 song 快照 → `.lrc`/内嵌标签为空；必须把本次 hit 保存在局部变量并传入标签/侧车写入，上传歌词则始终优先
- bvid 冲突更新会把既有歌曲归到新 job；取消重复导入若按 job 级联删除会误删已下载文件 → 任务删除仅清理无文件的新预览项，ready/file_path 项解除关联，并在冲突更新时保留本地封面
- 下载队列改动至少回归三件事：全局活跃数不超上限、同任务重复启动幂等、部分选择能结束且未选歌曲保持 pending；前端改动需同时看桌面和 390px 手机视口
- Mutagen 的空 `MP4Tags` 是 falsy，不能写 `audio.tags or {}`（会得到与音频无关的普通 dict）；仅当 `tags is None` 时调用 `audio.add_tags()`
- 500 首导入预览不要只靠缩小字体：默认紧凑行、多P改 select，保留舒展模式供精细核对；封面 lazy-load，行使用 `content-visibility` 降低离屏布局开销
- SQLite 多线程写入使用“线程独立连接 + WAL + busy timeout”，schema/migration 每进程只初始化一次；客户端只重试幂等读取，POST/PATCH/DELETE 遇到网关错误不可自动重放；B 站 httpx Client 必须用上下文管理器关闭，并把 HTTP/非 JSON 响应转成可读错误
- 收藏夹视频可能没有封面 URL；React 中不可渲染 `img src=""`，无 URL 时直接显示占位图，图片加载失败也应保留占位层
- 曲库主体点击只播放，封面点击才展开全屏封面/歌词；展开状态放在 PlayerContext 供曲库与 PlayerBar 共用。封面事件必须阻止冒泡，当前歌曲已播放时只展开、不要重复 playSong 触发暂停；卡片/列表和封面开关偏好持久化
- 播放模式放在 PlayerContext 并持久化；单曲循环只处理自然 ended，主动切歌仍正常工作；随机选曲排除当前索引，避免用户点击后听起来像没有生效
- 歌单表只存歌曲关系与顺序，不复制音频；歌曲删除依赖 SQLite 外键级联清关系。歌单、歌手、关键词筛选必须汇总成同一个播放队列，避免界面显示与下一首范围不一致
- 网页鉴权用一次性验证码 + HttpOnly 签名 Cookie，API_TOKEN 只做脚本兼容。仅代理对端为内网/回环时信任 X-Forwarded-For；只记录成功会话，last_seen 写入需节流，IP 属地查不到不能阻塞登录
- Compose 不会默认读取 `deploy/.env`，而显式 `environment` 会覆盖 env_file；部署变量统一走可选的 `env_file: deploy/.env`，只保留固定 DATA_DIR。上线必须验证 auth/status 已启用且匿名 API 返回 401
- 香港机房请求 ipwho.is 偶尔超过 2.5 秒；首次新 IP 查询使用 5 秒超时并将成功属地缓存到 SQLite，查询失败仍不得阻断登录
- macOS 媒体键/iOS 锁屏使用 Media Session API；同步歌曲 metadata、playbackState、positionState，封面给绝对 URL。WebKit action 支持不齐，逐项 try/catch；系统 previoustrack 必须直接切上一首，不复用 UI 的 3 秒回到开头逻辑
- React effect cleanup 会在依赖变化时执行，不等于组件卸载；Media Session 切歌时不可清空 metadata 或反复撤销 action handler，否则 macOS 会短暂把媒体焦点交给网易云等其他播放器。元数据直接覆盖，handler 注册一次并通过 ref 调用最新队列逻辑，仅在 PlayerProvider 真正卸载时清理

## 验证清单（每次改动后）

- [ ] 后端模块可导入（`from app.main import app`）
- [ ] 前端 `pnpm build` 通过
- [ ] 部署后 `/api/health` 200、网页 title 正确
- [ ] 涉及下载：真实下载 1 首验证
- [ ] 涉及解析：真实数据 + 回归用例
- [ ] 涉及 schema：老库迁移能跑（MIGRATIONS 幂等）

## 维护规则（让项目越用越聪明）

每次修完 bug / 加完功能：把新教训追加到仓库 `AGENTS.md` 的「踩坑记录」和本技能的「历史踩坑」两处，并提交。这样任何未来的会话（含其他机器）都继承全部经验。
