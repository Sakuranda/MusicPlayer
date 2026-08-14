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

## 维护规则

1. 每次修 bug / 加功能：把教训追加到本文件「踩坑记录」和 `.dsh/skills/musicplayer/SKILL.md` 的「历史踩坑」，再提交
2. 涉及 schema / API / 流程：同步更新 `docs/` 对应文档
3. 部署前确认没有下载任务在跑；部署后跑「验证清单」（健康检查、真实下载一首、解析回归）
