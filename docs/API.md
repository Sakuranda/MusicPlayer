# API 参考

MusicPlayer 后端（FastAPI）接口文档。基础地址：`https://music.sakuranda.site` 或 `http://45.125.33.88:8080`。

## 认证

网页端默认使用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录，并在登录前填写一次性图片验证码。登录成功后服务器设置 HttpOnly、SameSite=Lax 的签名会话 Cookie，默认有效 30 天；连续登录失败会触发按 IP 限流。

无需登录的端点：`/api/health`、`/api/auth/status`、`/api/auth/captcha`、`/api/auth/login`、`/api/auth/logout`。其余 `/api/*` 需要有效会话。

登录接口：

```
GET  /api/auth/status   → {enabled, authenticated, username}
GET  /api/auth/captcha  → {id, image, expires_in}   // image 为 data URL，5 分钟有效
POST /api/auth/login    {username,password,captcha_id,captcha}
POST /api/auth/logout
GET  /api/auth/access-audit → 成功登录 IP 数、属地、登录/最近访问时间和分钟级活跃记录数
```

`API_TOKEN` 保留给脚本、Navidrome 之外的旧客户端和应急管理。设置后可用以下任一方式代替网页登录会话：

```http
X-Api-Token: <token>
```

或查询参数（用于 `<audio>` 等无法自定义请求头的场景）：

```
/api/stream/1?token=<token>
```

未认证返回 `401 {"detail": "请先登录"}`。查询参数令牌仅应用于 `<audio>`、封面、CSV 等无法添加自定义请求头的兼容场景，不应出现在普通网页链接中。

## 数据结构

### Song

```jsonc
{
  "id": 149,
  "bvid": "BV1Z1421U7rD",              // B站视频号（唯一键，去重依据）
  "job_id": "241f2992fb5f",
  "title": "カタオモイ",                 // 歌曲名（可编辑）
  "artist": "单相思",                   // 歌手（可编辑）
  "album": "musicplayer",              // 专辑（可编辑）
  "duration": 205.0,                   // 选中分P的时长（秒）
  "cid": 123456789,                    // 选中分P的 cid
  "part_index": 1,                     // 选中第几P
  "part_title": "P1",
  "parts": [                           // 全部分P
    { "cid": 123, "page": 1, "part": "【xx】海屿你", "duration": 296 }
  ],
  "source_url": "https://www.bilibili.com/video/BV1Z1421U7rD?p=1",  // B站源链接
  "downloaded_cid": 123456789,         // 实际下载过的分P（去重用）
  "raw_title": "原标题",
  "uploader": "呜米",
  "tags": ["翻唱", "Aimer"],
  "cover_url": "…", "cover": "/api/songs/149/cover",
  "file_path": "musicplayer/单相思 - カタオモイ [BV1Z1421U7rD].m4a",
  "lyrics": "纯文本歌词", "lrc": "[00:00.00]…", "lyrics_source": "lrclib",
  "lyrics_enabled": true,
  "status": "ready",                   // pending | downloading | ready | error
  "error": null
}
```

### Job

```jsonc
{
  "id": "241f2992fb5f",
  "url": "https://space.bilibili.com/19468476/favlist?fid=4112724176",
  "media_id": "4112724176",
  "title": "musicplayer",
  "status": "parsed",                  // parsed | downloading | done
  "total": 40, "done": 40, "failed": 0,
  "message": "完成：成功 40 首，失败 0 首"
}
```

## 端点

### 健康检查

```
GET /api/health
→ {"ok": true, "service": "musicplayer"}
```

### 导入任务

**解析收藏夹（不下载）**

```
POST /api/jobs
{ "url": "…", "cookie": "SESSDATA=…（可选）", "album": "自定义专辑名（可选）" }
→ {"job": Job, "songs": [Song…]}      // 全部为 pending，等待确认
```

错误：`400` 链接格式错误/私密缺 Cookie；`502` 服务器内部错误（含日志）。

**任务列表 / 详情**

```
GET /api/jobs            → [Job…]
GET /api/jobs/{id}       → {"job": Job, "songs": [Song…]}   // 下载进度轮询用
```

**开始下载（确认元数据后）**

```
POST /api/jobs/{id}/start
{ "bvids": ["BV…", …], "fetch_lyrics": true }  // 可关闭自动歌词匹配
→ {"started": true, "queued": 500, "concurrency": 3, "message": "已排队 500 首"}
```

所有任务共享同一个下载队列；`concurrency` 默认 3 且服务端硬限制不超过 5。
重复启动正在运行的同一任务不会重复排队。只选择部分歌曲时，任务进度只按本次选择统计。

**删除/取消任务**

```
DELETE /api/jobs/{id}
→ {"deleted": true}
```

取消预览会删除本次新增且尚未下载的记录；重复导入时关联到该任务的既有曲库歌曲会保留并解除任务关联。
正在下载的任务返回 `409`，防止后台线程与删除操作竞态。

### 歌曲

```
GET  /api/songs?status=ready        → [Song…]（曲库列表）
GET  /api/songs/{id}                → Song（含歌词）
PATCH /api/songs/{id}               // 修改元数据，音频文件标签同步重写
  { "title": "…", "artist": "…", "album": "…",
    "cid": 123, "part_index": 2, "part_title": "…", "duration": 296.0 }
DELETE /api/songs/{id}              → {"deleted": true}   // 删除音频/.lrc/封面/记录
PUT    /api/songs/{id}/lyrics       // multipart/form-data，file=.lrc 或 .txt，最大 1 MB
DELETE /api/songs/{id}/lyrics       // 删除数据库、.lrc 侧车和 M4A 内嵌歌词
```

### 歌单

```
GET    /api/playlists                         → [{id,name,song_count,created_at}]
POST   /api/playlists  {"name":"通勤"}       → 创建歌单
PATCH  /api/playlists/{id} {"name":"夜间"}  → 重命名
DELETE /api/playlists/{id}                    → 只删除歌单，不删除歌曲文件
GET    /api/playlists/{id}/songs              → 按加入顺序返回 [Song…]
POST   /api/playlists/{id}/songs/{song_id}    → 加入歌曲（重复请求幂等）
DELETE /api/playlists/{id}/songs/{song_id}    → 从歌单移除
```

歌单只保存歌曲引用与顺序，不复制音频、封面或歌词。删除歌曲时，其所有歌单关系由数据库级联清理。

### 媒体

```
GET /api/songs/{id}/cover            // 封面（本地缓存或 302 到 B 站 CDN）
GET /api/stream/{id}                 // 音频流（audio/mp4，支持 Range 拖动进度）
```

### 备份导出

```
GET /api/export.csv                  // 全曲库 CSV（UTF-8 BOM，Excel 友好）
```

CSV 列：`id,歌曲名,歌手,专辑,bvid,B站视频链接,分P,时长(秒),状态,歌词来源`。

## 典型流程

```bash
BASE=http://45.125.33.88:8080
TOKEN=xxx

# 1. 解析（私密收藏夹带 cookie）
curl -X POST $BASE/api/jobs -H "X-Api-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://space.bilibili.com/19468476/favlist?fid=4112724176","cookie":"SESSDATA=…"}'

# 2. 修改某首元数据/分P（可选）
curl -X PATCH $BASE/api/songs/149 -H "X-Api-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"artist":"呜米","cid":40201488806,"part_index":2}'

# 3. 开始下载
curl -X POST $BASE/api/jobs/<job_id>/start -H "X-Api-Token: $TOKEN" \
  -H "Content-Type: application/json" -d '{"bvids":["BV1Z1421U7rD"]}'

# 4. 轮询进度
curl $BASE/api/jobs/<job_id> -H "X-Api-Token: $TOKEN"

# 5. 播放
curl -r 0-100000 "$BASE/api/stream/149?token=$TOKEN" -o /dev/null
```
