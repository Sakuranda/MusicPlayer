import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'
import type { Song } from '../types'

interface PlayerState {
  current: Song | null
  queue: Song[]
  playing: boolean
  time: number
  duration: number
  volume: number
  playSong: (song: Song, queue?: Song[]) => void
  toggle: () => void
  next: () => void
  prev: () => void
  seek: (t: number) => void
  setVolume: (v: number) => void
  playQueue: (songs: Song[], index?: number) => void
}

const Ctx = createContext<PlayerState | null>(null)

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [queue, setQueue] = useState<Song[]>([])
  const [index, setIndex] = useState(-1)
  const [current, setCurrent] = useState<Song | null>(null)
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.8)

  useEffect(() => {
    const a = new Audio()
    a.preload = 'metadata'
    audioRef.current = a
    const onTime = () => setTime(a.currentTime)
    const onDur = () => setDuration(a.duration || 0)
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    const onEnded = () => setIndex((i) => {
      if (queue.length === 0) return i
      const n = (i + 1) % queue.length
      const next = queue[n]
      if (next) {
        a.src = api.streamUrl(next.id)
        setCurrent(next)
        a.play().catch(() => {})
      }
      return n
    })
    const onError = () => setPlaying(false)
    a.addEventListener('timeupdate', onTime)
    a.addEventListener('durationchange', onDur)
    a.addEventListener('play', onPlay)
    a.addEventListener('pause', onPause)
    a.addEventListener('ended', onEnded)
    a.addEventListener('error', onError)
    return () => {
      a.pause()
      a.removeEventListener('timeupdate', onTime)
      a.removeEventListener('durationchange', onDur)
      a.removeEventListener('play', onPlay)
      a.removeEventListener('pause', onPause)
      a.removeEventListener('ended', onEnded)
      a.removeEventListener('error', onError)
      a.src = ''
    }
  }, [queue])

  const start = useCallback((song: Song, songs: Song[], i: number) => {
    setQueue(songs)
    setIndex(i)
    setCurrent(song)
    setTime(0)
    const a = audioRef.current
    if (!a) return
    a.src = api.streamUrl(song.id)
    a.play().catch(() => setPlaying(false))
  }, [])

  const playSong = useCallback((song: Song, songs?: Song[]) => {
    const a = audioRef.current
    if (!a) return
    if (current?.id === song.id) {
      if (a.paused) a.play().catch(() => {})
      else a.pause()
      return
    }
    const q = songs && songs.length ? songs : queue.length ? queue : [song]
    start(song, q, Math.max(0, q.findIndex((s) => s.id === song.id)))
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
    const n = (index + 1) % queue.length
    start(queue[n], queue, n)
  }, [queue, index, start])

  const prev = useCallback(() => {
    const a = audioRef.current
    if (!queue.length) return
    if (a && a.currentTime > 3) {
      a.currentTime = 0
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
    <Ctx.Provider
      value={{ current, queue, playing, time, duration, volume, playSong, toggle, next, prev, seek, setVolume, playQueue }}
    >
      {children}
    </Ctx.Provider>
  )
}

export function usePlayer(): PlayerState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('usePlayer must be used within PlayerProvider')
  return ctx
}
