import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'
import type { Song } from '../types'
import { PlayerContext, type PlaybackMode } from './playerContext'

const PLAYBACK_MODE_KEY = 'mp_playback_mode'
const DEFAULT_DOCUMENT_TITLE = 'MusicPlayer · B站收藏夹曲库'

function initialPlaybackMode(): PlaybackMode {
  const saved = localStorage.getItem(PLAYBACK_MODE_KEY)
  return saved === 'shuffle' || saved === 'one' ? saved : 'repeat'
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [queue, setQueue] = useState<Song[]>([])
  const [index, setIndex] = useState(-1)
  const [current, setCurrent] = useState<Song | null>(null)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.8)
  const [expanded, setExpanded] = useState(false)
  const [playbackMode, setPlaybackModeState] = useState<PlaybackMode>(initialPlaybackMode)

  // 创建音频元素并绑定基础事件（只执行一次）
  useEffect(() => {
    const a = new Audio()
    a.preload = 'metadata'
    a.volume = 0.8
    audioRef.current = a
    const onTime = () => setTime(a.currentTime)
    const onDur = () => setDuration(a.duration || 0)
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    const onError = () => setPlaying(false)
    a.addEventListener('timeupdate', onTime)
    a.addEventListener('durationchange', onDur)
    a.addEventListener('play', onPlay)
    a.addEventListener('pause', onPause)
    a.addEventListener('error', onError)
    return () => {
      a.pause()
      a.removeEventListener('timeupdate', onTime)
      a.removeEventListener('durationchange', onDur)
      a.removeEventListener('play', onPlay)
      a.removeEventListener('pause', onPause)
      a.removeEventListener('error', onError)
      a.src = ''
      audioRef.current = null
    }
  }, [])

  const start = useCallback((song: Song, songs: Song[], i: number) => {
    const a = audioRef.current
    if (!a) return
    setQueue(songs)
    setIndex(i)
    setCurrent(song)
    setTime(0)
    setDuration(song.duration || 0)
    a.src = api.streamUrl(song.id)
    a.play().catch(() => setPlaying(false))
  }, [])

  const randomIndex = useCallback((length: number, currentIndex: number) => {
    if (length <= 1) return 0
    const offset = 1 + Math.floor(Math.random() * (length - 1))
    return (currentIndex + offset) % length
  }, [])

  // 播放结束自动切下一首（依赖 queue/index 重新绑定）
  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onEnded = () => {
      if (queue.length === 0) {
        setPlaying(false)
        return
      }
      if (playbackMode === 'one') {
        a.currentTime = 0
        a.play().catch(() => setPlaying(false))
        return
      }
      const n = playbackMode === 'shuffle'
        ? randomIndex(queue.length, index)
        : (index + 1) % queue.length
      start(queue[n], queue, n)
    }
    a.addEventListener('ended', onEnded)
    return () => a.removeEventListener('ended', onEnded)
  }, [queue, index, playbackMode, randomIndex, start])

  const playSong = useCallback((song: Song, songs?: Song[]) => {
    const a = audioRef.current
    if (!a) return
    if (current?.id === song.id) {
      if (a.paused) a.play().catch(() => {})
      else a.pause()
      return
    }
    const q = songs && songs.length ? songs : queue.length ? queue : [song]
    const i = Math.max(0, q.findIndex((s) => s.id === song.id))
    start(song, q, i)
  }, [current, queue, start])

  const playQueue = useCallback((songs: Song[], i = 0) => {
    if (!songs.length) return
    start(songs[i], songs, i)
  }, [start])

  const toggle = useCallback(() => {
    const a = audioRef.current
    if (!a) return
    if (a.paused) a.play().catch(() => {})
    else a.pause()
  }, [])

  const next = useCallback(() => {
    if (!queue.length) return
    const n = playbackMode === 'shuffle'
      ? randomIndex(queue.length, index)
      : (index + 1) % queue.length
    start(queue[n], queue, n)
  }, [queue, index, playbackMode, randomIndex, start])

  // 系统级“上一曲”必须确实切换歌曲；播放器 UI 的 prev 仍保留播放超过
  // 3 秒时先回到本曲开头的常见交互。
  const previousTrack = useCallback(() => {
    if (!queue.length) return
    const n = (index - 1 + queue.length) % queue.length
    start(queue[n], queue, n)
  }, [queue, index, start])

  const prev = useCallback(() => {
    const a = audioRef.current
    if (!queue.length) return
    if (a && a.currentTime > 3) {
      a.currentTime = 0
      setTime(0)
      return
    }
    const n = (index - 1 + queue.length) % queue.length
    start(queue[n], queue, n)
  }, [queue, index, start])

  // Media Session 的处理器只注册一次；通过 ref 读取最新队列，避免切歌时先撤销
  // 系统按键处理器、再重新注册所产生的短暂媒体焦点空档。
  const mediaTrackHandlersRef = useRef({ next, previousTrack })
  useEffect(() => {
    mediaTrackHandlersRef.current = { next, previousTrack }
  }, [next, previousTrack])

  const seek = useCallback((t: number) => {
    const a = audioRef.current
    if (!a) return
    a.currentTime = t
    setTime(t)
  }, [])

  const setVolume = useCallback((v: number) => {
    setVolumeState(v)
    if (audioRef.current) audioRef.current.volume = v
  }, [])

  const setPlaybackMode = useCallback((mode: PlaybackMode) => {
    setPlaybackModeState(mode)
    localStorage.setItem(PLAYBACK_MODE_KEY, mode)
  }, [])

  // 向 macOS 控制中心/媒体键和 iOS 锁屏提供歌曲信息与系统控制。
  useEffect(() => {
    if (!current) {
      document.title = DEFAULT_DOCUMENT_TITLE
      if ('mediaSession' in navigator) {
        navigator.mediaSession.metadata = null
        navigator.mediaSession.playbackState = 'none'
        try { navigator.mediaSession.setPositionState() } catch { /* unsupported */ }
      }
      return
    }

    document.title = `${current.title} — ${current.artist}`
    if (!('mediaSession' in navigator)) return
    const mediaSession = navigator.mediaSession
    const cover = api.coverUrl(current)
    const artwork = cover
      ? [{ src: new URL(cover, window.location.href).href, sizes: '320x320', type: 'image/jpeg' }]
      : []
    if (typeof MediaMetadata !== 'undefined') {
      mediaSession.metadata = new MediaMetadata({
        title: current.title,
        artist: current.artist,
        album: current.album || 'MusicPlayer',
        artwork,
      })
    }
  }, [current])

  // 切换 current 也会执行依赖 effect 的 cleanup，因此媒体会话只能在 Provider
  // 真正卸载时清空。否则 macOS 会在两首歌之间短暂切到其他播放器。
  useEffect(() => () => {
    document.title = DEFAULT_DOCUMENT_TITLE
    if (!('mediaSession' in navigator)) return
    navigator.mediaSession.metadata = null
    navigator.mediaSession.playbackState = 'none'
    try { navigator.mediaSession.setPositionState() } catch { /* unsupported */ }
  }, [])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    navigator.mediaSession.playbackState = current
      ? (playing ? 'playing' : 'paused')
      : 'none'
  }, [current, playing])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    const a = audioRef.current
    if (!a || !current || !Number.isFinite(duration) || duration <= 0) return
    try {
      navigator.mediaSession.setPositionState({
        duration,
        playbackRate: a.playbackRate || 1,
        position: Math.min(Math.max(time, 0), duration),
      })
    } catch {
      // Safari 旧版本可能暴露 mediaSession 但尚未实现位置状态。
    }
  }, [current, duration, time])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    const mediaSession = navigator.mediaSession
    const a = audioRef.current
    const setHandler = (action: MediaSessionAction, handler: MediaSessionActionHandler) => {
      try {
        mediaSession.setActionHandler(action, handler)
      } catch {
        // WebKit/Chrome 版本支持的 action 集合不同，逐项失败不能影响其他按键。
      }
    }
    const seekBy = (offset: number) => {
      if (!a || !Number.isFinite(a.duration)) return
      const target = Math.min(Math.max(a.currentTime + offset, 0), a.duration)
      a.currentTime = target
      setTime(target)
    }

    setHandler('play', () => a?.play().catch(() => setPlaying(false)))
    setHandler('pause', () => a?.pause())
    setHandler('nexttrack', () => mediaTrackHandlersRef.current.next())
    setHandler('previoustrack', () => mediaTrackHandlersRef.current.previousTrack())
    setHandler('seekbackward', (details) => seekBy(-(details.seekOffset || 10)))
    setHandler('seekforward', (details) => seekBy(details.seekOffset || 10))
    setHandler('seekto', (details) => {
      if (!a || details.seekTime == null) return
      const target = Number.isFinite(a.duration)
        ? Math.min(Math.max(details.seekTime, 0), a.duration)
        : Math.max(details.seekTime, 0)
      if (details.fastSeek && typeof a.fastSeek === 'function') a.fastSeek(target)
      else a.currentTime = target
      setTime(target)
    })
    setHandler('stop', () => {
      if (!a) return
      a.pause()
      a.currentTime = 0
      setTime(0)
    })

    return () => {
      for (const action of [
        'play', 'pause', 'nexttrack', 'previoustrack',
        'seekbackward', 'seekforward', 'seekto', 'stop',
      ] as MediaSessionAction[]) {
        try { mediaSession.setActionHandler(action, null) } catch { /* unsupported */ }
      }
    }
  }, [])

  return (
    <PlayerContext.Provider
      value={{
        current,
        queue,
        playing,
        time,
        duration,
        volume,
        expanded,
        playbackMode,
        playSong,
        toggle,
        next,
        prev,
        seek,
        setVolume,
        setExpanded,
        setPlaybackMode,
        playQueue,
      }}
    >
      {children}
    </PlayerContext.Provider>
  )
}
