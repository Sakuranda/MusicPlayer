# API 参考

MusicPlayer 后端（FastAPI）接口文档。基础地址：`https://music.sakuranda.site` 或 `http://45.125.33.88:8080`。

## 认证

部署时若设置了 `API_TOKEN`（`deploy/.env`），除 `/api/health` 外所有 `/api/*` 请求需携带令牌，两种方式任选：

```http
X-Api-Token: <token>
```

或查询参数（用于 `<audio>` 等无法自定义请求头的场景）：

```
/api/stream/1?token=<token>
```

未带令牌返回 `401 {"detail": "需要有效的 API Token"}`。

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
{ "bvids": ["BV…", …] }  // 只下载勾选的；已下载且分P未变的自动跳过
→ {"started": true}      // 后台线程执行，轮询 GET /api/jobs/{id}
```

**删除任务（连带删除任务下所有歌曲与文件）**

```
DELETE /api/jobs/{id}
→ {"deleted": true}
```

### 歌曲

```
GET  /api/songs?status=ready        → [Song…]（曲库列表）
GET  /api/songs/{id}                → Song（含歌词）
PATCH /api/songs/{id}               // 修改元数据，音频文件标签同步重写
  { "title": "…", "artist": "…", "album": "…",
    "cid": 123, "part_index": 2, "part_title": "…", "duration": 296.0 }
DELETE /api/songs/{id}              → {"deleted": true}   // 删除音频/.lrc/封面/记录
```

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
