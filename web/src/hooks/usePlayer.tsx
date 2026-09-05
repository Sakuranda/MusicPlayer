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

function shuffledCopy<T>(items: T[]): T[] {
  const shuffled = [...items]
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  return shuffled
}

function initialPlaybackMode(): PlaybackMode {
  const saved = localStorage.getItem(PLAYBACK_MODE_KEY)
  return saved === 'shuffle' || saved === 'one' ? saved : 'repeat'
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  // Native audio and lock-screen events must advance immediately even when React
  // effects are deferred in the background. This is the authoritative cursor.
  const playbackRef = useRef<{ queue: Song[]; index: number; current: Song | null; mode: PlaybackMode }>({
    queue: [], index: -1, current: null, mode: initialPlaybackMode(),
  })
  const generationRef = useRef(0)
  const resumeAtRef = useRef<number | null>(null)
  const [playbackError, setPlaybackError] = useState<string | null>(null)
  const sourceQueueRef = useRef<Song[]>([])
  const lastShuffleStartIdRef = useRef<number | null>(null)
  const lastShuffleSignatureRef = useRef('')
  const [queue, setQueue] = useState<Song[]>([])
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
    a.preload = 'auto'
    a.volume = 0.8
    audioRef.current = a
    const syncSession = () => {
      if (!('mediaSession' in navigator)) return
      navigator.mediaSession.playbackState = !playbackRef.current.current
        ? 'none' : a.paused ? 'paused' : 'playing'
      try {
        if (Number.isFinite(a.duration) && a.duration > 0) {
          navigator.mediaSession.setPositionState({ duration: a.duration,
            position: Math.min(Math.max(a.currentTime, 0), a.duration), playbackRate: a.playbackRate || 1 })
        } else navigator.mediaSession.setPositionState()
      } catch { /* older Safari */ }
    }
    const onTime = () => { setTime(a.currentTime); syncSession() }
    const onDur = () => { setDuration(Number.isFinite(a.duration) ? a.duration : 0); syncSession() }
    const onPlay = () => { setPlaying(true); setPlaybackError(null); syncSession() }
    const onPause = () => { setPlaying(false); syncSession() }
    const onError = () => {
      setPlaying(false)
      setPlaybackError('音频加载失败，点击播放重试；若持续失败，请重新登录或检查音频文件。')
      syncSession()
    }
    const onMetadata = () => {
      if (resumeAtRef.current !== null && Number.isFinite(a.duration)) {
        a.currentTime = Math.min(resumeAtRef.current, Math.max(0, a.duration - .1))
        resumeAtRef.current = null
      }
      onDur()
    }
    a.addEventListener('loadedmetadata', onMetadata)
    a.addEventListener('timeupdate', onTime)
    a.addEventListener('durationchange', onDur)
    a.addEventListener('play', onPlay)
    a.addEventListener('pause', onPause)
    a.addEventListener('error', onError)
    return () => {
      a.pause()
      generationRef.current += 1
      a.removeEventListener('loadedmetadata', onMetadata)
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
    playbackRef.current = { ...playbackRef.current, queue: songs, index: i, current: song }
    const generation = ++generationRef.current
    resumeAtRef.current = null
    setPlaybackError(null)
    setQueue(songs)
    setCurrent(song)
    setTime(0)
    setDuration(song.duration || 0)
    document.title = `${song.title} — ${song.artist}`
    if ('mediaSession' in navigator) {
      const cover = api.coverUrl(song)
      if (typeof MediaMetadata !== 'undefined') {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: song.title, artist: song.artist, album: song.album || 'MusicPlayer',
          artwork: [{ src: new URL(cover || '/icon-512.png', window.location.href).href }],
        })
      }
      try { navigator.mediaSession.setPositionState() } catch { /* unsupported */ }
    }
    a.src = api.streamUrl(song.id)
    a.play().catch(() => {
      if (generation !== generationRef.current) return
      setPlaying(false)
      setPlaybackError('播放未能启动，点击播放重试。')
    })
  }, [])

  const buildShuffleQueue = useCallback((songs: Song[], leading?: Song, avoidStartId?: number) => {
    if (!songs.length) return []
    let shuffled: Song[]
    if (leading) {
      shuffled = [leading, ...shuffledCopy(songs.filter((song) => song.id !== leading.id))]
    } else {
      shuffled = shuffledCopy(songs)
      const blockedStartId = avoidStartId ?? lastShuffleStartIdRef.current
      if (shuffled.length > 1 && shuffled[0].id === blockedStartId) {
        const swapIndex = 1 + Math.floor(Math.random() * (shuffled.length - 1))
        ;[shuffled[0], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[0]]
      }
    }

    let signature = shuffled.map((song) => song.id).join(',')
    if (signature === lastShuffleSignatureRef.current && shuffled.length > 2) {
      // 保留已选定的起始歌曲，只交换后续顺序；两首歌时无法同时改变
      // 顺序并避免轮末歌曲紧接着重复，优先保证不连续重复。
      ;[shuffled[1], shuffled[2]] = [shuffled[2], shuffled[1]]
      signature = shuffled.map((song) => song.id).join(',')
    }
    lastShuffleStartIdRef.current = shuffled[0].id
    lastShuffleSignatureRef.current = signature
    return shuffled
  }, [])

  const resume = useCallback(() => {
    const a = audioRef.current
    if (!a || !playbackRef.current.current) return
    const generation = generationRef.current
    if (a.error || (a.ended && Number.isFinite(a.duration) && a.currentTime + 1 < a.duration)) {
      resumeAtRef.current = a.currentTime
      a.load()
    }
    a.play().catch(() => {
      if (generation !== generationRef.current) return
      setPlaying(false)
      setPlaybackError('播放未能启动，点击播放重试。')
    })
  }, [])

  const toggle = useCallback(() => {
    const a = audioRef.current
    if (!a) return
    if (a.paused) resume()
    else a.pause()
  }, [resume])

  const playSong = useCallback((song: Song, songs?: Song[]) => {
    const a = audioRef.current
    if (!a) return
    const { current, queue, mode: playbackMode } = playbackRef.current
    if (current?.id === song.id) {
      if (a.paused) resume()
      else a.pause()
      return
    }
    const candidates = songs && songs.length ? songs : queue.length ? queue : [song]
    const q = candidates.some((item) => item.id === song.id) ? candidates : [...candidates, song]
    sourceQueueRef.current = q
    if (playbackMode === 'shuffle') {
      const shuffled = buildShuffleQueue(q, song)
      start(song, shuffled, 0)
      return
    }
    const i = Math.max(0, q.findIndex((item) => item.id === song.id))
    start(song, q, i)
  }, [buildShuffleQueue, resume, start])

  const playQueue = useCallback((songs: Song[], i = 0) => {
    if (!songs.length) return
    const playbackMode = playbackRef.current.mode
    i = Math.min(Math.max(Number.isFinite(i) ? Math.floor(i) : 0, 0), songs.length - 1)
    sourceQueueRef.current = songs
    if (playbackMode === 'shuffle') {
      const shuffled = buildShuffleQueue(songs)
      start(shuffled[0], shuffled, 0)
      return
    }
    start(songs[i], songs, i)
  }, [buildShuffleQueue, start])

  const next = useCallback(() => {
    const { queue, index, mode: playbackMode } = playbackRef.current
    if (!queue.length) return
    if (playbackMode === 'shuffle' && index === queue.length - 1 && queue.length > 1) {
      const sourceQueue = sourceQueueRef.current.length ? sourceQueueRef.current : queue
      const shuffled = buildShuffleQueue(sourceQueue, undefined, queue[index].id)
      start(shuffled[0], shuffled, 0)
      return
    }
    const n = (index + 1) % queue.length
    start(queue[n], queue, n)
  }, [buildShuffleQueue, start])

  // 系统级“上一曲”必须确实切换歌曲；播放器 UI 的 prev 仍保留播放超过
  // 3 秒时先回到本曲开头的常见交互。
  const previousTrack = useCallback(() => {
    const { queue, index } = playbackRef.current
    if (!queue.length) return
    const n = (index - 1 + queue.length) % queue.length
    start(queue[n], queue, n)
  }, [start])

  const prev = useCallback(() => {
    const { queue, index } = playbackRef.current
    const a = audioRef.current
    if (!queue.length) return
    if (a && a.currentTime > 3) {
      a.currentTime = 0
      setTime(0)
      return
    }
    const n = (index - 1 + queue.length) % queue.length
    start(queue[n], queue, n)
  }, [start])

  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onEnded = () => {
      // Ignore delayed/duplicate events from an old source, and never silently
      // skip a track when a broken stream reports an early end.
      if (!a.ended || !playbackRef.current.current) return
      if (!Number.isFinite(a.duration) || a.duration <= 0 || a.currentTime + 1 < a.duration) {
        a.pause()
        setPlaying(false)
        setPlaybackError('音频意外中断，点击播放重试。')
        return
      }
      if (playbackRef.current.mode === 'one') {
        a.currentTime = 0
        resume()
      } else next()
    }
    a.addEventListener('ended', onEnded)
    return () => a.removeEventListener('ended', onEnded)
  }, [next, resume])

  const seek = useCallback((t: number) => {
    const a = audioRef.current
    if (!a || !Number.isFinite(t) || !Number.isFinite(a.duration) || a.duration <= 0) return
    const target = Math.min(Math.max(t, 0), a.duration)
    a.currentTime = target
    setTime(target)
  }, [])

  const setVolume = useCallback((v: number) => {
    if (!Number.isFinite(v)) return
    v = Math.min(Math.max(v, 0), 1)
    setVolumeState(v)
    if (audioRef.current) audioRef.current.volume = v
  }, [])

  const setPlaybackMode = useCallback((mode: PlaybackMode) => {
    const { current, queue } = playbackRef.current
    playbackRef.current.mode = mode
    setPlaybackModeState(mode)
    localStorage.setItem(PLAYBACK_MODE_KEY, mode)
    if (!current || !queue.length) return

    const sourceQueue = sourceQueueRef.current.length ? sourceQueueRef.current : queue
    const nextQueue = mode === 'shuffle'
      ? buildShuffleQueue(sourceQueue, current)
      : sourceQueue
    const nextIndex = Math.max(0, nextQueue.findIndex((song) => song.id === current.id))
    playbackRef.current.queue = nextQueue
    playbackRef.current.index = nextIndex
    setQueue(nextQueue)
  }, [buildShuffleQueue])

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
    const mediaSession = navigator.mediaSession
    const a = audioRef.current
    const setHandler = (action: MediaSessionAction, handler: MediaSessionActionHandler | null) => {
      try {
        mediaSession.setActionHandler(action, handler)
      } catch {
        // WebKit/Chrome 版本支持的 action 集合不同，逐项失败不能影响其他按键。
      }
    }
    setHandler('play', resume)
    setHandler('pause', () => a?.pause())
    setHandler('nexttrack', next)
    setHandler('previoustrack', previousTrack)
    // iOS has limited lock-screen button slots. Advertise track navigation,
    // keep scrubbing via seekto, and do not claim podcast-style skip controls.
    setHandler('seekbackward', null)
    setHandler('seekforward', null)
    setHandler('seekto', (details) => {
      if (details.seekTime != null) seek(details.seekTime)
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
  }, [next, previousTrack, resume, seek])

  return (
    <PlayerContext.Provider
      value={{
        current,
        queue,
        playing,
        playbackError,
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
