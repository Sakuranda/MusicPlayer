import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Disc3,
  Download,
  Loader2,
  Pencil,
  Play,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import { usePlayer } from '../hooks/usePlayer'
import type { Song } from '../types'

interface Props {
  songs: Song[]
  serverOk: boolean | null
  onRefresh: () => void
  onGoImport: () => void
}

function Cover({ song, className }: { song: Song; className?: string }) {
  const [failed, setFailed] = useState(false)
  const url = api.coverUrl(song)
  if (!url || failed) {
    return (
      <div className={`flex items-center justify-center bg-panel2 ${className ?? ''}`}>
        <Disc3 size={28} className="text-faint" />
      </div>
    )
  }
  return (
    <img
      src={url}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className={`object-cover ${className ?? ''}`}
    />
  )
}

function EditModal({
  song,
  onClose,
  onSaved,
}: {
  song: Song
  onClose: () => void
  onSaved: (s: Song) => void
}) {
  const [title, setTitle] = useState(song.title)
  const [artist, setArtist] = useState(song.artist)
  const [album, setAlbum] = useState(song.album || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const updated = await api.updateSong(song.id, {
        title: title.trim() || song.title,
        artist: artist.trim() || song.artist,
        album: album.trim(),
      })
      onSaved(updated)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center fade-in-up"
      onClick={onClose}
    >
      <div
        className="w-[420px] max-w-[92vw] bg-panel border border-line rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-medium">编辑歌曲信息</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted hover:text-ink transition-colors">
            <X size={16} />
          </button>
        </div>

        <label className="block text-xs text-muted mb-1.5">歌曲名</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          autoFocus
          className="w-full bg-bg2 border border-line rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-accent/60 transition-colors mb-4"
        />
        <label className="block text-xs text-muted mb-1.5">歌手</label>
        <input
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          className="w-full bg-bg2 border border-line rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-accent/60 transition-colors mb-4"
        />
        <label className="block text-xs text-muted mb-1.5">专辑（可选）</label>
        <input
          value={album}
          onChange={(e) => setAlbum(e.target.value)}
          className="w-full bg-bg2 border border-line rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-accent/60 transition-colors"
        />

        <div className="text-[11px] text-faint mt-2">
          原标题：{song.raw_title} · UP主：{song.uploader}
        </div>

        {error && <div className="text-xs text-danger mt-3">{error}</div>}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-panel2 border border-line text-sm text-muted hover:text-ink transition-colors"
          >
            取消
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2.5 rounded-xl bg-accent hover:bg-accent-soft text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

function DeleteModal({
  song,
  onClose,
  onDeleted,
}: {
  song: Song
  onClose: () => void
  onDeleted: () => void
}) {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const doDelete = async () => {
    setDeleting(true)
    setError('')
    try {
      await api.deleteSong(song.id)
      onDeleted()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setDeleting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center fade-in-up"
      onClick={onClose}
    >
      <div
        className="w-[360px] max-w-[92vw] bg-panel border border-line rounded-2xl p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-medium mb-2">删除歌曲</h3>
        <p className="text-sm text-muted leading-relaxed mb-5">
          确定删除 <span className="text-ink">{song.title}</span> — {song.artist} 吗？
          音频文件和歌词将一并从服务器移除，此操作不可撤销。
        </p>
        {error && <div className="text-xs text-danger mb-4">{error}</div>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-panel2 border border-line text-sm text-muted hover:text-ink transition-colors"
          >
            取消
          </button>
          <button
            onClick={doDelete}
            disabled={deleting}
            className="px-4 py-2.5 rounded-xl bg-danger hover:bg-danger/85 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {deleting ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function LibraryView({ songs, serverOk, onRefresh, onGoImport }: Props) {
  const { playSong, playQueue, current, playing } = usePlayer()
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Song | null>(null)
  const [deleting, setDeleting] = useState<Song | null>(null)
  const [localSongs, setLocalSongs] = useState(songs)

  // 外部刷新时同步
  const [lastSynced, setLastSynced] = useState(songs)
  if (songs !== lastSynced) {
    setLastSynced(songs)
    setLocalSongs(songs)
  }

  const ready = useMemo(() => localSongs.filter((s) => s.status === 'ready'), [localSongs])
  const others = useMemo(() => localSongs.filter((s) => s.status !== 'ready'), [localSongs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return ready
    return ready.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.artist.toLowerCase().includes(q) ||
        (s.album || '').toLowerCase().includes(q) ||
        (s.raw_title || '').toLowerCase().includes(q),
    )
  }, [ready, query])

  return (
    <div className="max-w-6xl mx-auto px-8 pt-10">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight mb-1.5">曲库</h1>
          <p className="text-sm text-muted">
            {ready.length} 首歌曲{others.length > 0 ? ` · ${others.length} 首处理中/失败` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索歌曲、歌手…"
              className="w-56 bg-panel border border-line rounded-xl pl-9 pr-3 py-2 text-sm placeholder:text-faint focus:outline-none focus:border-accent/50 transition-colors"
            />
          </div>
          <button
            onClick={onRefresh}
            title="刷新"
            className="p-2.5 rounded-xl bg-panel border border-line text-muted hover:text-ink transition-colors"
          >
            <RefreshCw size={15} />
          </button>
          <button
            onClick={() => playQueue(filtered)}
            disabled={!filtered.length}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent hover:bg-accent-soft text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={15} fill="currentColor" /> 播放全部
          </button>
        </div>
      </div>

      {serverOk === false && (
        <div className="flex items-center gap-3 bg-danger/10 border border-danger/30 rounded-2xl px-5 py-4 mb-6 text-sm">
          <AlertTriangle size={17} className="text-danger shrink-0" />
          无法连接服务器。请到「设置」检查服务器地址，或确认服务器已部署。
        </div>
      )}

      {ready.length === 0 && others.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-28 text-center">
          <div className="w-20 h-20 rounded-3xl bg-accent-dim flex items-center justify-center mb-6">
            <Disc3 size={36} className="text-accent" />
          </div>
          <h2 className="text-xl font-medium mb-2">曲库还是空的</h2>
          <p className="text-sm text-muted mb-6 max-w-sm">
            粘贴一个 B 站收藏夹链接，自动解析歌曲名、歌手、歌词并下载音频
          </p>
          <button
            onClick={onGoImport}
            className="flex items-center gap-2 px-5 py-3 rounded-xl bg-accent hover:bg-accent-soft text-white text-sm font-medium transition-colors"
          >
            <Download size={16} /> 导入第一个收藏夹
          </button>
        </div>
      ) : (
        <>
          {filtered.length > 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {filtered.map((song, i) => {
                const isCurrent = current?.id === song.id
                return (
                  <div
                    key={song.id}
                    onClick={() => playSong(song, filtered)}
                    className="group hover-lift bg-panel border border-line rounded-2xl overflow-hidden cursor-pointer fade-in-up"
                    style={{ animationDelay: `${Math.min(i * 25, 300)}ms` }}
                  >
                    <div className="relative aspect-square overflow-hidden bg-panel2">
                      <Cover song={song} className="w-full h-full transition-transform duration-300 group-hover:scale-105" />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                        <div className="w-12 h-12 rounded-full bg-white/95 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all translate-y-2 group-hover:translate-y-0">
                          {isCurrent && playing ? (
                            <Loader2 size={18} className="text-bg spin" />
                          ) : (
                            <Play size={18} className="text-bg ml-0.5" fill="currentColor" />
                          )}
                        </div>
                      </div>
                      {isCurrent && (
                        <div className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-accent text-white text-[10px] font-medium">
                          播放中
                        </div>
                      )}
                    </div>
                    <div className="p-3.5">
                      <div className="font-medium text-sm truncate" title={song.title}>
                        {song.title}
                      </div>
                      <div className="text-xs text-muted truncate mt-0.5" title={song.artist}>
                        {song.artist}
                        {song.album ? ` · ${song.album}` : ''}
                      </div>
                      <div className="flex justify-end gap-0.5 mt-1.5">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditing(song)
                          }}
                          className="p-1.5 rounded-lg text-faint hover:text-accent hover:bg-accent-dim transition-colors"
                          title="编辑歌曲信息"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleting(song)
                          }}
                          className="p-1.5 rounded-lg text-faint hover:text-danger hover:bg-danger/10 transition-colors"
                          title="删除歌曲"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-muted py-12 text-center">没有匹配的歌曲</p>
          )}

          {others.length > 0 && (
            <div className="mt-10">
              <h2 className="text-sm font-medium text-muted mb-3">处理中 / 失败的条目</h2>
              <div className="space-y-2">
                {others.map((song) => (
                  <div
                    key={song.id}
                    className="flex items-center gap-3 bg-panel border border-line rounded-xl px-4 py-3"
                  >
                    <div className="w-10 h-10 rounded-lg overflow-hidden bg-panel2 shrink-0">
                      <Cover song={song} className="w-full h-full" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm truncate">{song.title} — {song.artist}</div>
                      <div className="text-[11px] text-faint truncate mt-0.5">{song.raw_title}</div>
                    </div>
                    {song.status === 'downloading' && (
                      <span className="flex items-center gap-1.5 text-xs text-accent">
                        <Loader2 size={13} className="spin" /> 下载中
                      </span>
                    )}
                    {song.status === 'pending' && (
                      <span className="text-xs text-faint">待下载</span>
                    )}
                    {song.status === 'error' && (
                      <span
                        className="text-xs text-danger max-w-[220px] truncate"
                        title={song.error || ''}
                      >
                        <AlertTriangle size={12} className="inline mr-1" />
                        {song.error || '失败'}
                      </span>
                    )}
                    <button
                      onClick={() => setDeleting(song)}
                      className="p-1.5 rounded-lg text-faint hover:text-danger hover:bg-danger/10 transition-colors shrink-0"
                      title="删除该条目"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {editing && (
        <EditModal
          song={editing}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setLocalSongs((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
            onRefresh()
          }}
        />
      )}

      {deleting && (
        <DeleteModal
          song={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setLocalSongs((prev) => prev.filter((s) => s.id !== deleting.id))
            onRefresh()
          }}
        />
      )}
    </div>
  )
}
