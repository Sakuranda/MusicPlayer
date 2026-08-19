import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'
import type { Song } from '../types'
import { PlayerContext } from './playerContext'

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [queue, setQueue] = useState<Song[]>([])
  const [index, setIndex] = useState(-1)
  const [current, setCurrent] = useState<Song | null>(null)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.8)

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

  // 播放结束自动切下一首（依赖 queue/index 重新绑定）
  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onEnded = () => {
      if (queue.length === 0) {
        setPlaying(false)
        return
      }
      const n = (index + 1) % queue.length
      start(queue[n], queue, n)
    }
    a.addEventListener('ended', onEnded)
    return () => a.removeEventListener('ended', onEnded)
  }, [queue, index, start])

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
    start(queue[(index + 1) % queue.length], queue, (index + 1) % queue.length)
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

  return (
    <PlayerContext.Provider
      value={{ current, queue, playing, time, duration, volume, playSong, toggle, next, prev, seek, setVolume, playQueue }}
    >
      {children}
    </PlayerContext.Provider>
  )
}
