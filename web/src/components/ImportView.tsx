import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Bookmark,
  CalendarClock,
  Check,
  ChevronDown,
  Download,
  ImageOff,
  Link2,
  ListCollapse,
  Loader2,
  Play,
  RefreshCw,
  Rows3,
  Trash2,
} from 'lucide-react'
import { api } from '../lib/api'
import { fmtTime } from '../lib/lrc'
import type { JobDetail, SavedCollection, Song } from '../types'

interface Props {
  onImported: () => void
  onViewLibrary: () => void
}

type Step = 'input' | 'preview' | 'progress'
type Density = 'compact' | 'comfortable'

const LS_COOKIE = 'mp_bili_cookie'
const LS_DENSITY = 'mp_import_density'

export default function ImportView({ onImported, onViewLibrary }: Props) {
  const [step, setStep] = useState<Step>('input')
  const [url, setUrl] = useState('')
  // 私密收藏夹需要 Cookie；记住在本浏览器，方便反复导入
  const [cookie, setCookie] = useState(() => localStorage.getItem(LS_COOKIE) || '')
  const [album, setAlbum] = useState('')
  const [autoLyrics, setAutoLyrics] = useState(true)
  const [saveCollection, setSaveCollection] = useState(true)
  const [autoUpdate, setAutoUpdate] = useState(false)
  const [density, setDensityState] = useState<Density>(() =>
    localStorage.getItem(LS_DENSITY) === 'comfortable' ? 'comfortable' : 'compact',
  )
  const [showCookie, setShowCookie] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [collections, setCollections] = useState<SavedCollection[]>([])
  const [collectionBusy, setCollectionBusy] = useState<number | null>(null)
  const [collectionMessage, setCollectionMessage] = useState('')

  const [detail, setDetail] = useState<JobDetail | null>(null)
  const [edits, setEdits] = useState<
    Record<number, { title: string; artist: string; cid?: number; part_index?: number; part_title?: string; duration?: number }>
  >({})
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [starting, setStarting] = useState(false)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    api.collections().then(setCollections).catch(() => setCollections([]))
  }, [])

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [])

  const songs = detail?.songs ?? []
  const allSelected = songs.length > 0 && selected.size === songs.length
  const compact = density === 'compact'

  const setDensity = (next: Density) => {
    setDensityState(next)
    localStorage.setItem(LS_DENSITY, next)
  }

  const submit = async () => {
    setError('')
    if (!url.trim()) {
      setError('请先粘贴收藏夹链接')
      return
    }
    setLoading(true)
    try {
      if (cookie.trim()) localStorage.setItem(LS_COOKIE, cookie.trim())
      const d = await api.createJob(
        url.trim(), cookie.trim(), album.trim(), saveCollection, autoUpdate,
      )
      setDetail(d)
      // 已有实体音频默认不勾选；服务端仍会再次做文件级去重，双重防止重下。
      setSelected(new Set(d.songs.filter((song) => !song.file_path).map((song) => song.id)))
      setEdits({})
      setStep('preview')
      api.collections().then(setCollections).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const refreshSavedCollection = async (collection: SavedCollection) => {
    setCollectionBusy(collection.id)
    setCollectionMessage('')
    setError('')
    try {
      const result = await api.refreshCollection(collection.id)
      setCollectionMessage(
        result.queued > 0
          ? `「${collection.title}」新增 ${result.queued} 首，已自动加入下载队列`
          : `「${collection.title}」已是最新，没有新增歌曲`,
      )
      setCollections(await api.collections())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCollectionBusy(null)
    }
  }

  const toggleCollectionAutoUpdate = async (collection: SavedCollection) => {
    setCollectionBusy(collection.id)
    setError('')
    try {
      const updated = await api.updateCollection(collection.id, {
        auto_update: !collection.auto_update,
      })
      setCollections((items) => items.map((item) => item.id === updated.id ? updated : item))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCollectionBusy(null)
    }
  }

  const removeSavedCollection = async (collection: SavedCollection) => {
    if (!window.confirm(`不再保存「${collection.title}」？曲库中的歌曲和音频都会保留。`)) return
    setCollectionBusy(collection.id)
    setError('')
    try {
      await api.deleteCollection(collection.id)
      setCollections((items) => items.filter((item) => item.id !== collection.id))
      setCollectionMessage(`已移除「${collection.title}」的保存记录，歌曲仍保留在曲库`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCollectionBusy(null)
    }
  }

  const toggleAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(songs.map((s) => s.id)))
  }

  const updateEdit = (id: number, field: 'title' | 'artist' | 'cid', value: string | number) => {
    const src = songs.find((s) => s.id === id)
    setEdits((prev) => {
      // 首次编辑时用原始值初始化另一字段，避免歌名被空字符串覆盖
      const cur = prev[id] ?? {
        title: src?.title ?? '',
        artist: src?.artist ?? '',
        cid: src?.cid ?? undefined,
        part_index: src?.part_index ?? undefined,
        part_title: src?.part_title ?? undefined,
        duration: src?.duration ?? undefined,
      }
      if (field === 'cid') {
        const part = (src?.parts ?? []).find((p) => p.cid === value)
        return {
          ...prev,
          [id]: {
            ...cur,
            cid: value as number,
            part_index: part?.page,
            part_title: part?.part,
            duration: part?.duration,
          },
        }
      }
      return { ...prev, [id]: { ...cur, [field]: value as string } }
    })
  }

  const finalSong = (s: Song): Song => {
    const e = edits[s.id]
    if (!e) return s
    return { ...s, title: e.title || s.title, artist: e.artist || s.artist }
  }

  const start = async () => {
    if (!detail || selected.size === 0) return
    setStarting(true)
    try {
      const bvids = songs.filter((s) => selected.has(s.id)).map((s) => s.bvid)
      // 先提交编辑（歌名/歌手/分P选择）
      await Promise.all(
        songs
          .filter((s) => edits[s.id])
          .map((s) =>
            api.updateSong(s.id, {
              title: edits[s.id].title || s.title,
              artist: edits[s.id].artist || s.artist,
              cid: edits[s.id].cid,
              part_index: edits[s.id].part_index,
              part_title: edits[s.id].part_title,
              duration: edits[s.id].duration,
            }),
          ),
      )
      await api.startJob(detail.job.id, bvids, autoLyrics)
      setStep('progress')
      poll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setStarting(false)
    }
  }

  const poll = () => {
    timerRef.current = window.setInterval(async () => {
      if (!detail) return
      try {
        const d = await api.getJob(detail.job.id)
        setDetail(d)
        if (d.job.status === 'done' || d.job.status === 'error') {
          if (timerRef.current) window.clearInterval(timerRef.current)
        }
      } catch { /* 轮询失败就等下一次 */ }
    }, 2000)
  }

  const cancelJob = async () => {
    if (!detail) return
    try {
      await api.deleteJob(detail.job.id)
    } catch { /* ignore */ }
    reset()
  }

  const reset = () => {
    setStep('input')
    setDetail(null)
    setUrl('')
    setError('')
    setSelected(new Set())
    setEdits({})
  }

  const progress = detail?.job
  const progressSongs = songs.filter((song) => selected.has(song.id))
  const pct = progress && progress.total > 0
    ? Math.round(((progress.done + progress.failed) / progress.total) * 100)
    : 0

  return (
    <div className="max-w-4xl mx-auto px-4 pt-6 sm:px-6 md:px-8 md:pt-10">
      {/* ---------- 第一步：粘贴链接 ---------- */}
      {step === 'input' && (
        <div className="fade-in-up">
          <h1 className="text-3xl font-semibold tracking-tight mb-2">导入 B 站收藏夹</h1>
          <p className="text-sm text-muted mb-8">
            自动解析收藏夹内所有视频的歌曲名与歌手（虚拟主播翻唱优化），并匹配歌词、下载音频
          </p>

          {collections.length > 0 && (
            <section className="mb-5 rounded-2xl border border-line bg-panel p-4 sm:p-5" aria-labelledby="saved-collections-title">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h2 id="saved-collections-title" className="flex items-center gap-2 text-sm font-medium">
                    <Bookmark size={15} className="text-accent" /> 已保存收藏夹
                  </h2>
                  <p className="mt-1 text-[11px] text-faint">手动检查或开启每日自动更新，只下载新增歌曲</p>
                </div>
                <span className="rounded-full bg-accent-dim px-2 py-1 text-[10px] text-accent">
                  {collections.length} 个链接
                </span>
              </div>
              <div className="space-y-2">
                {collections.map((collection) => (
                  <div key={collection.id} className="flex flex-col gap-3 rounded-xl border border-line bg-bg2 px-3.5 py-3 sm:flex-row sm:items-center">
                    <button
                      type="button"
                      onClick={() => { setUrl(collection.url); setAlbum(collection.album || '') }}
                      className="min-w-0 flex-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                      title="将这个链接填入下方"
                    >
                      <div className="truncate text-sm font-medium">{collection.title}</div>
                      <div className="mt-0.5 text-[10px] text-faint">
                        {collection.downloaded_count || 0}/{collection.song_count} 首已下载
                        {collection.last_checked_at
                          ? ` · 上次检查 ${new Date(collection.last_checked_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
                          : ' · 尚未检查'}
                      </div>
                      {collection.last_error && (
                        <div className="mt-1 truncate text-[10px] text-danger" title={collection.last_error}>{collection.last_error}</div>
                      )}
                    </button>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="flex items-center gap-1 text-[10px] text-muted">
                        <CalendarClock size={12} /> 每日
                      </span>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={collection.auto_update}
                        aria-label={`${collection.title} 每日自动更新`}
                        disabled={collectionBusy === collection.id}
                        onClick={() => void toggleCollectionAutoUpdate(collection)}
                        className={`relative h-5 w-9 rounded-full transition-colors disabled:opacity-50 ${collection.auto_update ? 'bg-accent' : 'bg-panel2 border border-line'}`}
                      >
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${collection.auto_update ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
                      </button>
                      <button
                        type="button"
                        disabled={collectionBusy === collection.id}
                        onClick={() => void refreshSavedCollection(collection)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[11px] text-muted hover:border-accent/50 hover:text-ink disabled:opacity-50"
                      >
                        <RefreshCw size={12} className={collectionBusy === collection.id ? 'spin' : ''} />
                        手动更新
                      </button>
                      <button
                        type="button"
                        disabled={collectionBusy === collection.id}
                        onClick={() => void removeSavedCollection(collection)}
                        className="rounded-lg p-1.5 text-faint hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                        title="取消保存（不删除歌曲）"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {collectionMessage && (
            <div className="mb-4 flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-500">
              <Check size={14} /> {collectionMessage}
            </div>
          )}

          <div className="bg-panel border border-line rounded-2xl p-6">
            <label className="block text-sm font-medium mb-2">收藏夹链接</label>
            <div className="relative">
              <Link2 size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-faint" />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                placeholder="https://space.bilibili.com/xxx/favlist?fid=xxx 或 https://www.bilibili.com/medialist/detail/mlxxx"
                className="w-full bg-bg2 border border-line rounded-xl pl-10 pr-3 py-3 text-sm placeholder:text-faint focus:outline-none focus:border-accent/60 transition-colors"
                autoFocus
              />
            </div>

            <div className="mt-4">
              <label className="block text-sm font-medium mb-2">
                专辑名（可选，默认用收藏夹名）
              </label>
              <input
                value={album}
                onChange={(e) => setAlbum(e.target.value)}
                placeholder="留空则使用收藏夹标题"
                className="w-full bg-bg2 border border-line rounded-xl px-3 py-3 text-sm placeholder:text-faint focus:outline-none focus:border-accent/60 transition-colors"
              />
            </div>

            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors ${saveCollection ? 'border-accent/40 bg-accent-dim' : 'border-line bg-bg2'}`}>
                <input
                  type="checkbox"
                  checked={saveCollection}
                  onChange={(event) => {
                    setSaveCollection(event.target.checked)
                    if (!event.target.checked) setAutoUpdate(false)
                  }}
                  className="mt-0.5 h-4 w-4 accent-[#d97757]"
                />
                <span>
                  <span className="block text-xs font-medium">保存这个收藏夹</span>
                  <span className="mt-1 block text-[10px] leading-relaxed text-faint">以后可直接手动检查，并在曲库按收藏夹筛选</span>
                </span>
              </label>
              <label className={`flex items-start gap-3 rounded-xl border p-3.5 transition-colors ${saveCollection ? 'cursor-pointer' : 'cursor-not-allowed opacity-45'} ${autoUpdate ? 'border-accent/40 bg-accent-dim' : 'border-line bg-bg2'}`}>
                <input
                  type="checkbox"
                  checked={autoUpdate}
                  disabled={!saveCollection}
                  onChange={(event) => setAutoUpdate(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#d97757]"
                />
                <span>
                  <span className="block text-xs font-medium">每天自动更新</span>
                  <span className="mt-1 block text-[10px] leading-relaxed text-faint">每 24 小时检查一次，只自动下载新增歌曲</span>
                </span>
              </label>
            </div>

            <div className="mt-4">
              <button
                onClick={() => setShowCookie((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors"
              >
                <ChevronDown size={14} className={`transition-transform ${showCookie ? 'rotate-180' : ''}`} />
                收藏夹是私密的？粘贴 B 站 Cookie
              </button>
              {showCookie && (
                <>
                  <textarea
                    value={cookie}
                    onChange={(e) => setCookie(e.target.value)}
                    rows={3}
                    placeholder="SESSDATA=xxx; bili_jct=xxx; …（浏览器 F12 → 网络请求 → 复制 Cookie）"
                    className="mt-2 w-full bg-bg2 border border-line rounded-xl px-3 py-3 text-xs font-mono placeholder:text-faint focus:outline-none focus:border-accent/60 transition-colors"
                  />
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[11px] text-faint">
                      保存在当前浏览器和你的私人服务器，仅用于访问 B 站；私密收藏夹自动更新需要它
                    </span>
                    {cookie && (
                      <button
                        onClick={() => {
                          setCookie('')
                          localStorage.removeItem(LS_COOKIE)
                        }}
                        className="text-[11px] text-muted hover:text-danger transition-colors"
                      >
                        清除已保存的 Cookie
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>

            {error && (
              <div className="flex items-center gap-2 text-sm text-danger mt-4">
                <AlertTriangle size={15} /> {error}
              </div>
            )}

            <button
              onClick={submit}
              disabled={loading}
              className="mt-6 flex items-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary/85 text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 size={16} className="spin" /> : <Download size={16} />}
              {loading ? '解析中…' : '解析收藏夹'}
            </button>
          </div>
        </div>
      )}

      {/* ---------- 第二步：预览与编辑 ---------- */}
      {step === 'preview' && detail && (
        <div className="fade-in-up">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">确认歌曲信息</h1>
              <p className="text-sm text-muted mt-1">
                收藏夹「{detail.job.title}」· {songs.length} 首 · 已有音频默认不勾选，只下载新增歌曲
              </p>
            </div>
            <button
              onClick={cancelJob}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-danger transition-colors"
            >
              <Trash2 size={13} /> 取消导入
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3 mb-3 px-1">
            <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="accent-[#d97757] w-4 h-4"
              />
              全选
            </label>
            <span className="text-xs text-faint">已选 {selected.size}/{songs.length}</span>
            <div className="ml-auto inline-flex items-center rounded-lg border border-line bg-bg2 p-0.5" aria-label="预览密度">
              <button
                onClick={() => setDensity('compact')}
                aria-pressed={compact}
                title="紧凑：一屏显示更多歌曲"
                className={`inline-flex items-center gap-1 px-2 py-1.5 rounded-md text-[11px] transition-colors ${
                  compact ? 'bg-panel2 text-ink' : 'text-faint hover:text-muted'
                }`}
              >
                <Rows3 size={13} /> 紧凑
              </button>
              <button
                onClick={() => setDensity('comfortable')}
                aria-pressed={!compact}
                title="舒展：显示完整标签和多 P 选项"
                className={`inline-flex items-center gap-1 px-2 py-1.5 rounded-md text-[11px] transition-colors ${
                  !compact ? 'bg-panel2 text-ink' : 'text-faint hover:text-muted'
                }`}
              >
                <ListCollapse size={13} /> 舒展
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={autoLyrics}
                onChange={(e) => setAutoLyrics(e.target.checked)}
                className="accent-[#d97757] w-4 h-4"
              />
              自动匹配歌词
            </label>
          </div>

          <div className={`${compact ? 'space-y-1' : 'space-y-2'} max-h-[62vh] overflow-y-auto pr-1`}>
            {songs.map((song) => {
              const checked = selected.has(song.id)
              const e = edits[song.id]
              return (
                <div
                  key={song.id}
                  className={`song-preview-row flex items-start bg-panel border transition-colors ${
                    compact ? 'gap-2 rounded-lg px-3 py-2' : 'gap-3 rounded-xl px-4 py-3'
                  } ${
                    checked ? 'border-accent/40' : 'border-line opacity-60'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      setSelected((prev) => {
                        const n = new Set(prev)
                        if (n.has(song.id)) n.delete(song.id)
                        else n.add(song.id)
                        return n
                      })
                    }}
                    className={`accent-[#d97757] w-4 h-4 shrink-0 ${compact ? 'mt-2.5' : 'mt-4'}`}
                  />
                  <div className={`${compact ? 'w-9 h-9 rounded-md' : 'w-12 h-12 rounded-lg mt-0.5'} relative grid place-items-center overflow-hidden bg-panel2 text-faint shrink-0`}>
                    <ImageOff size={compact ? 13 : 16} aria-hidden="true" />
                    {song.cover_url && (
                      <img
                        src={`${song.cover_url}@160w_160h_1c.webp`}
                        alt=""
                        loading="lazy"
                        className="absolute inset-0 w-full h-full object-cover"
                        onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                      />
                    )}
                  </div>
                  <div className={`flex-1 min-w-0 grid grid-cols-2 ${compact ? 'gap-1.5' : 'gap-2'}`}>
                    <input
                      value={e?.title ?? song.title}
                      onChange={(ev) => updateEdit(song.id, 'title', ev.target.value)}
                      className={`bg-bg2 border border-line rounded-lg focus:outline-none focus:border-accent/60 ${
                        compact ? 'px-2 py-1.5 text-xs' : 'px-2.5 py-2 text-sm'
                      }`}
                      title="歌曲名"
                    />
                    <input
                      value={e?.artist ?? song.artist}
                      onChange={(ev) => updateEdit(song.id, 'artist', ev.target.value)}
                      className={`bg-bg2 border border-line rounded-lg focus:outline-none focus:border-accent/60 ${
                        compact ? 'px-2 py-1.5 text-xs' : 'px-2.5 py-2 text-sm'
                      }`}
                      title="歌手"
                    />
                    {compact ? (
                      <div className="col-span-2 flex items-center gap-2 min-w-0 pl-1 text-[10px] text-faint">
                        <span className="truncate flex-1">
                          {song.raw_title}{song.uploader ? ` · ${song.uploader}` : ''}
                          {song.file_path ? ' · 已有音频' : ''}
                        </span>
                        {(song.parts?.length ?? 0) > 1 ? (
                          <select
                            value={e?.cid ?? song.cid ?? ''}
                            onChange={(event) => updateEdit(song.id, 'cid', Number(event.target.value))}
                            className="max-w-48 shrink-0 bg-bg2 border border-line rounded-md px-1.5 py-0.5 text-[10px] text-muted focus:outline-none focus:border-accent/60"
                            aria-label={`${song.title} 分P选择`}
                          >
                            {song.parts!.map((part) => (
                              <option key={part.cid} value={part.cid}>
                                P{part.page} {part.part} · {fmtTime(part.duration)}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="tabular-nums shrink-0">{fmtTime(e?.duration ?? song.duration ?? 0)}</span>
                        )}
                      </div>
                    ) : (
                      <>
                        <div className="col-span-2 text-[11px] text-faint truncate pl-1">
                          原标题：{song.raw_title}
                          {song.uploader ? ` · UP主：${song.uploader}` : ''}
                          {song.tags?.length ? ` · 标签：${song.tags.join(' / ')}` : ''}
                        </div>
                        {/* 时长与分P选择 */}
                        {(song.parts?.length ?? 0) > 1 ? (
                      <div className="col-span-2 pl-1 mt-0.5">
                        <div className="text-[11px] text-muted mb-1">
                          多 P 视频（{song.parts!.length} P）· 选择要下载的 P：
                        </div>
                        <div className="space-y-0.5 max-h-24 overflow-y-auto">
                          {song.parts!.map((p) => (
                            <label
                              key={p.cid}
                              className="flex items-center gap-1.5 text-[11px] text-muted cursor-pointer hover:text-ink transition-colors"
                            >
                              <input
                                type="radio"
                                name={`part-${song.id}`}
                                checked={(e?.cid ?? song.cid) === p.cid}
                                onChange={() => updateEdit(song.id, 'cid', p.cid)}
                                className="accent-[#d97757] w-3.5 h-3.5"
                              />
                              <span className="truncate">P{p.page} {p.part}</span>
                              <span className="text-faint tabular-nums shrink-0">{fmtTime(p.duration)}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                        ) : (
                          <div className="col-span-2 pl-1 text-[11px] text-faint tabular-nums">
                            时长：{fmtTime(e?.duration ?? song.duration ?? 0)}
                            {song.parts?.[0]?.part ? ` · ${song.parts[0].part}` : ''}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-danger mt-4">
              <AlertTriangle size={15} /> {error}
            </div>
          )}

          <div className="flex items-center gap-3 mt-6">
            {selected.size > 0 ? (
              <button
                onClick={start}
                disabled={starting}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary/85 text-white text-sm font-medium transition-colors disabled:opacity-40"
              >
                {starting ? <Loader2 size={16} className="spin" /> : <Download size={16} />}
                下载选中的 {selected.size} 首
              </button>
            ) : (
              <button
                onClick={onImported}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary/85 text-white text-sm font-medium transition-colors"
              >
                <Check size={16} /> 没有新增歌曲，返回曲库
              </button>
            )}
            <span className="text-[11px] text-faint">
              {autoLyrics ? '会依次查询歌词源' : '已关闭歌词查询，可稍后手动上传'}
            </span>
            <button
              onClick={reset}
              className="flex items-center gap-1.5 px-4 py-3 rounded-xl bg-panel border border-line text-sm text-muted hover:text-ink transition-colors"
            >
              <ArrowLeft size={15} /> 重新粘贴
            </button>
          </div>
        </div>
      )}

      {/* ---------- 第三步：下载进度 ---------- */}
      {step === 'progress' && detail && progress && (
        <div className="fade-in-up">
          <h1 className="text-2xl font-semibold tracking-tight mb-6">正在下载</h1>

          <div className="bg-panel border border-line rounded-2xl p-6 mb-6">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-muted">
                {progress.status === 'downloading' ? '下载并匹配歌词中…' : '任务已结束'}
              </div>
              <div className="text-sm font-medium">
                {progress.done + progress.failed} / {progress.total} · {pct}%
              </div>
            </div>
            <div className="h-2 rounded-full bg-panel2 overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-3 text-xs text-faint">
              成功 {progress.done} · 失败 {progress.failed}
              {progress.message ? ` · ${progress.message}` : ''}
            </div>
          </div>

          <div className="space-y-2 max-h-[46vh] overflow-y-auto">
            {progressSongs.map((song) => (
              <div
                key={song.id}
                className="flex items-center gap-3 bg-panel border border-line rounded-xl px-4 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">
                    {finalSong(song).title} — {finalSong(song).artist}
                  </div>
                </div>
                {song.status === 'downloading' && (
                  <span className="flex items-center gap-1.5 text-xs text-accent">
                    <Loader2 size={13} className="spin" /> 下载中
                  </span>
                )}
                {song.status === 'pending' && <span className="text-xs text-faint">排队中</span>}
                {song.status === 'ready' && (
                  <span className="flex items-center gap-1 text-xs text-emerald-500">
                    <Check size={13} /> 完成{finalSong(song).lyrics_source ? ' · 有歌词' : ''}
                  </span>
                )}
                {song.status === 'error' && (
                  <span className="text-xs text-danger truncate max-w-[240px]" title={song.error || ''}>
                    {song.error || '失败'}
                  </span>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3 mt-6">
            <button
              onClick={onViewLibrary}
              className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary/85 text-white text-sm font-medium transition-colors"
            >
              <Play size={15} fill="currentColor" /> 前往曲库
            </button>
            <button
              onClick={() => {
                onImported()
              }}
              className="px-4 py-3 rounded-xl bg-panel border border-line text-sm text-muted hover:text-ink transition-colors"
            >
              完成
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
