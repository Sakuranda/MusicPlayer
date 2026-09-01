# AGENTS.md — MusicPlayer 项目记忆

> 任何 AI 助手（Claude Code / Cursor / Codex / DeepSeek Harness）开始本项目的任务前，先读本文件。
> 这是「活的」文档：每次修复 Bug、添加功能后，把新经验追加到文末「踩坑记录」，让项目越用越聪明。

## 项目是什么

**B站收藏夹歌曲库**：粘贴 B 站收藏夹链接 → 自动解析歌曲名/歌手（虚拟主播翻唱优化）→ 匹配歌词 → 下载音频（分P可选）→ 网页播放器 + iOS（Navidrome/Amperfy）在线播放。含去重（保存B站源链接、已下载自动跳过）与 CSV 备份。

- 仓库：https://github.com/Sakuranda/MusicPlayer
- 生产：https://music.sakuranda.site（hk 服务器 45.125.33.88，`ssh hk`）

## 架构

```
web/                     React + Vite + Tailwind v4（曲库、导入三步、播放器+滚动歌词、设置）
  src/lib/api.ts         API 客户端（Token、502 自动重试）
  src/hooks/usePlayer.tsx  播放器状态（Audio 单例 + 队列）
  src/components/        LibraryView(编辑/删除弹窗) ImportView(预览+分P选择) PlayerBar SettingsView
server/app/              FastAPI 后端
  bilibili.py            B站 API（收藏夹分页、详情/分P、标签、playurl、buvid 指纹、限速）
  parser.py              标题→歌名/歌手解析（启发式，见下）
  downloader.py          DASH 直连下载 + yt-dlp 回退 + mutagen 打标签 + .lrc 侧车
  lyrics.py              LRCLIB→网易云→QQ 三级降级
  importer.py            导入流水线（解析入库、后台下载、自动重试、统计重算）
  db.py                  SQLite（schema + MIGRATIONS 迁移）
  main.py                路由 + API Token 中间件 + 静态托管 + CSV 导出
docker-compose.yml       api(8080) + navidrome(4533) + caddy(profile https 备用)
deploy/                  deploy.sh、.env.example、Caddyfile
docs/                    使用指南 / 部署运维 / API 参考
bilibili-research-report.md  B站 API 实测调研
.dsh/skills/musicplayer/    DSH 专属技能（本文件的可执行版）
```

## 关键事实（改动前必读）

1. **media_id 双形态**：`favlist?fid={x}` 的 fid 有时就是 media_id，有时需 `fid + mid后两位` 换算。`parse_fav_url` 返回双候选、`fetch_favorites` 逐个尝试 —— 永远不要只信一种公式。
2. **私密收藏夹**：B 站返回 `code=0 + data=null`（不是 -403），需 Cookie（SESSDATA）。Cookie 存 `data/cookies/{media_id}.txt`。
3. **下载**：DASH 直连为主（`Referer: https://www.bilibili.com/` 必需），yt-dlp 网页路线为回退。数据中心 IP 会触发 412 / "bad parameter or other API misuse"（限流）→ 已内置多级等待重试 + 批次后自动重试失败项。音质上限 192k AAC。
4. **多P**：`songs.cid/part_index/part_title/parts`；`source_url` 存B站链接；`downloaded_cid` 用于去重（已下载且分P未变→跳过）。
5. **SQLite**：`db.get_conn()` 建新连接 + 幂等迁移（SCHEMA 与 MIGRATIONS 两处都要加新列）。线程各自独立连接（共享连接会报 "cannot commit - no transaction is active"）。
6. **标题解析**：信号优先级 = 《》「」书名号 > 标题切分（逆序"歌手-歌名"、原唱歌手名单排除）> 标签挖歌名 > 英文短语。歌手 = 【】人名 > 标签主播名聚类 > UP主。启发式不全对 → 预览可编辑是设计，勿过度调参。

## 常用命令

```bash
# 本地开发
cd server && .venv/bin/uvicorn app.main:app --reload --port 8080
cd web && pnpm dev                       # /api 自动代理到 8080

# 验证
cd server && .venv/bin/python -c "from app.main import app"
cd web && pnpm build

# 部署（⚠️ 会中断正在跑的下载，先查任务状态）
ssh hk 'cd /opt/musicplayer && git pull -q --ff-only && docker compose up -d --build'

# 排障
ssh hk 'docker logs musicplayer-api --tail 100'
curl http://45.125.33.88:8080/api/health

# 数据
ssh hk 'docker exec musicplayer-api python -c "..."'   # DB 位于 /data/musicplayer.db
curl -o songs.csv "http://45.125.33.88:8080/api/export.csv?token=TOKEN"
```

API Token：`d0689adf8786539510fc906531076ac7`（服务器 deploy/.env 内）。Navidrome：sakuranda / MusicPlayer2026。

## 回归测试数据

用户收藏夹（私密，需 Cookie）：`https://space.bilibili.com/19468476/favlist?fid=4112724176`（"musicplayer"，40 首，含 1 个多P：BV1MCKa6REjd 海屿你 2P）。调解析器必须跑：真实 40 首 + 早期合成用例双回归。

## 踩坑记录（按时间累积）

- 2026-08-14 初始化：fid→media_id 只信调研公式导致私密收藏夹空数据 → 双候选逐个尝试
- 2026-08-14 私密收藏夹 code=0+data=null，友好提示需 Cookie
- 2026-08-14 数据中心 IP 网页抓取 412 → DASH 直连主路线（view→playurl→CDN），yt-dlp 回退
- 2026-08-14 httpx 流式下载 CDN 卡死 → 直链交给 yt-dlp generic（续传/重试）
- 2026-08-14 `/tmp`→`/data` 跨文件系统 `Path.replace` 报 Errno 18 → `shutil.move`
- 2026-08-14 yt-dlp 进度刷屏 → `noprogress: True`
- 2026-08-14 解析器多轮调优：书名号歌名、呜米x咩栗拆分、逆序标题、句子/歌词判定、标签挖歌名、原唱歌手名单
- 2026-08-14 编辑歌手名清空歌名（`??` 不挡空串）→ 首次编辑用原始值初始化
- 2026-08-14 StrictMode 下 onEnded 副作用 → 重构成 effect
- 2026-08-14 共享 SQLite 连接并发提交冲突 → 每线程独立连接
- 2026-08-14 多次点击下载计数错乱 → 任务结束从 songs 表重算统计
- 2026-08-14 部署瞬间撞用户操作 → 502；前端对 502/503/504 自动重试一次；部署前查任务状态、被打断后复位 downloading 状态
- 2026-08-14 限流 "bad parameter or other API misuse" → 多级等待 + 批次后自动重试
- 2026-08-14 `cmd | tail && deploy` 管道吞退出码 → 关键命令不接管道
- 2026-08-14 ssh 嵌套 heredoc 引号地狱 → 脚本文件走 `docker exec -i ... python < 文件`
- 2026-08-14 封面旋转动画（spin）观感差 → 移除，静态封面
- 2026-08-14 多P：只下 P1 且时长误导 → parts/cid/source_url/downloaded_cid + 预览内联选择
- 2026-08-14 重复导入重复下载 → bvid UNIQUE + ON CONFLICT 保留文件 + downloaded_cid 跳过
- 2026-08-14 项目记忆机制：AGENTS.md + .dsh/skills/musicplayer（DSH 自动发现，文件监听热更新）
- 2026-08-19 每个任务各建下载线程池会让多个收藏夹叠加并发、重复点击还会重复提交；改为进程级共享队列，默认 3、硬上限 5，同一任务幂等启动，部分选择按本次歌曲统计进度
- 2026-08-19 为兼顾空间、音质与 iOS/Navidrome 兼容性，保留 B 站原始 AAC/M4A 不二次编码；封面统一缩成最大 320px、质量 70 的 JPEG，重下后清理旧路径文件
- 2026-08-19 歌词先更新 DB 再读旧 song 快照，导致 `.lrc` 与内嵌歌词实际为空；下载函数必须持有本次歌词结果。新增自动匹配开关、歌词 API 全局限速/缓存、上传/删除 `.lrc|.txt` 并同步侧车与 M4A 标签、播放器本地隐藏开关
- 2026-08-19 重复导入会把既有歌曲临时关联到新 job，取消预览若级联删歌会误删完整曲库；任务删除只清理无文件的新记录，既有 ready/file_path 歌曲改为解除关联。本地封面在 ON CONFLICT 时也必须优先保留；重启自动把内存下载任务标错防卡死
- 2026-08-19 补全批量队列回归（并发上限/重复启动/部分选择），前端修复 render 内同步 state 与 Fast Refresh 警告；导航、曲库、导入、设置、播放器完成 390px 移动端适配并经本地浏览器桌面/手机双视口验收
- 2026-08-19 Mutagen 的空 `MP4Tags` 为 falsy，`audio.tags or {}` 会退化成未关联的普通 dict，造成标签写了但没保存；必须仅在 `tags is None` 时 `add_tags()`，并显式处理清空专辑标签
- 2026-08-23 多线程 SQLite 每次连接都重复跑 schema/migration，默认 rollback journal 也容易在下载进度频繁写入时锁库；改为进程内只初始化一次、WAL + 30 秒 busy timeout，迁移只忽略明确的重复列错误。前端只自动重试幂等 GET/HEAD，避免 502 时重放创建任务等写操作；B 站客户端必须及时关闭并统一处理 HTTP/非 JSON 异常
- 2026-08-23 大收藏夹预览卡片过高且 500 首会增加布局绘制压力 → 默认紧凑密度（多P用单行 select），保留舒展模式切换并持久化；图片 lazy-load + `content-visibility` 跳过离屏绘制
- 2026-08-23 预览条目无封面时渲染 `img src=""` 会触发 React 错误并可能重新请求整页；无 URL 时不渲染 img，加载失败则露出轻量占位图标
- 2026-08-24 曲库卡片/列表的主体点击应只负责播放，封面点击才负责“选中歌曲 + 展开封面歌词”；展开状态需上提到 PlayerContext，封面事件必须 stopPropagation，且当前歌曲已播放时不可再次调用 playSong 导致暂停。视图/封面偏好本地持久化，大曲库行用 content-visibility 跳过离屏绘制
- 2026-08-24 播放模式属于跨页面播放器状态，应由 PlayerContext 统一维护并本地持久化；单曲循环只拦截音频自然 ended，用户主动上一首/下一首仍应正常切换，随机模式必须排除当前索引避免原曲连播
- 2026-08-24 歌单只保存 playlist_songs 关系，绝不复制媒体文件；SQLite 外键级联负责歌曲删除后的关系清理。曲库的歌单/歌手/关键词筛选应共同生成同一份 filtered 队列，确保“点歌”和“播放全部”行为一致
- 2026-08-24 网页鉴权使用一次性图片验证码 + HttpOnly 签名 Cookie，API_TOKEN 仅保留脚本兼容；真实 IP 只在直连对端为内网/回环代理时信任 X-Forwarded-For。只审计成功会话，last_seen 每会话最多每分钟落库一次；IP 属地必须缓存且外部查询失败不能阻断登录
- 2026-08-24 Compose 默认不会自动读取 `deploy/.env`，且 `environment` 的显式空值/默认值优先于 `env_file`；部署变量统一由可选 `env_file: deploy/.env` 注入，compose 仅显式保留容器内固定的 DATA_DIR。上线必须用 `/api/auth/status` 和未认证 401 验证配置确实进入容器，不能只看构建成功
- 2026-08-24 香港机房访问 ipwho.is 的 TLS/响应偶尔超过 2.5 秒，过短超时会让所有新 IP 属地静默为空；新 IP 首次成功登录允许 5 秒超时，成功后按 IP 缓存到 SQLite，失败仍不得阻断登录
- 2026-08-25 macOS 媒体键与 iOS 锁屏控制必须走 Media Session API，不能监听普通键盘事件；metadata 同步歌名/歌手/专辑/绝对封面 URL，playbackState/positionState 同步实际 Audio。WebKit 对 action 支持不一致，setActionHandler 必须逐项 try/catch；系统 previoustrack 应直接切歌，不能复用“播放超过 3 秒先回到开头”的 UI prev
- 2026-08-25 Media Session 的 metadata effect cleanup 会在每次切歌时执行，不只是组件卸载；若此时清空 metadata 并撤销 action handler，macOS 会在空档把“正在播放”切到网易云等其他播放器。曲目切换只覆盖元数据，action handler 只注册一次并用 ref 获取最新队列，仅在 PlayerProvider 真正卸载时统一清理
- 2026-09-01 重复导入遇到 B 站详情风控时，空 cid 覆盖既有 cid，再叠加旧任务把 ready 状态污染成 pending/error，会让已有文件被误判为分P变化并全量重下。去重必须以实际 file_path 文件存在为最终事实；当前 cid 未知时保留既有分P并视为未变化，修复脏状态为 ready。收藏夹列表的 ugc.first_cid 可作为 view API 412 时的直连依据，已知 cid 时详情请求只能补元数据、不可阻断 playurl
- 2026-09-01 收藏夹归属不能复用 songs.job_id（重复导入会重新归属且一首歌无法属于多个收藏夹）；新增 collections/collection_songs/job_songs 多对多关系。日更以 last_checked_at 满 24 小时为准，只 enrich 新增或缺 cid 且未下载的条目，只把本次新成员交给共享下载队列；取消保存仅删关系，不删歌曲文件

## 维护规则

1. 每次修 bug / 加功能：把教训追加到本文件「踩坑记录」和 `.dsh/skills/musicplayer/SKILL.md` 的「历史踩坑」，再提交
2. 涉及 schema / API / 流程：同步更新 `docs/` 对应文档
3. 部署前确认没有下载任务在跑；部署后跑「验证清单」（健康检查、真实下载一首、解析回归）
