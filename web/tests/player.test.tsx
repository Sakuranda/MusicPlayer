// @vitest-environment jsdom
import { StrictMode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlayerProvider } from '../src/hooks/usePlayer'
import { usePlayer } from '../src/hooks/playerContext'
import type { Song } from '../src/types'

class FakeAudio extends EventTarget {
  static latest: FakeAudio
  constructor() { super(); FakeAudio.latest = this }
  private source = ''
  private position = 0
  set src(value: string) { this.source = value; this.position = 0; this.ended = false; this.duration = NaN }
  get src() { return this.source }
  set currentTime(value: number) { this.position = value; this.ended = false }
  get currentTime() { return this.position }
  paused = true
  ended = false
  duration = NaN
  error: unknown = null
  volume = .8
  playbackRate = 1
  preload = ''
  play = vi.fn(() => { this.paused = false; this.ended = false; this.emit('play'); return Promise.resolve() })
  pause() { this.paused = true; this.emit('pause') }
  load = vi.fn(() => { this.error = null; this.ended = false })
  emit(event: string) { this.dispatchEvent(new Event(event)) }
  finish(time = 300) { this.duration = 300; this.position = time; this.ended = true; this.paused = true; this.emit('ended') }
}
const songs = Array.from({ length: 6 }, (_, id) => ({ id: id + 1, title: `Song ${id}`, artist: 'Artist', duration: 300 }) as Song)
let handlers: Record<string, MediaSessionActionHandler | null>
let session: { setActionHandler: ReturnType<typeof vi.fn>; setPositionState: ReturnType<typeof vi.fn>; metadata: unknown; playbackState: string }
beforeEach(() => {
  localStorage.clear()
  handlers = {}
  session = { setActionHandler: vi.fn((action, handler) => { handlers[action] = handler }), setPositionState: vi.fn(), metadata: null, playbackState: 'none' }
  vi.stubGlobal('Audio', FakeAudio)
  vi.stubGlobal('MediaMetadata', class { constructor(data: object) { Object.assign(this, data) } })
  Object.defineProperty(navigator, 'mediaSession', { configurable: true, value: session })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function setup() {
  return renderHook(usePlayer, { wrapper: ({ children }) => <StrictMode><PlayerProvider>{children}</PlayerProvider></StrictMode> })
}
function action(name: string) { handlers[name]?.({ action: name } as MediaSessionActionDetails) }

describe('background playback and media session', () => {
  it('advances multiple lock-screen commands before React has rendered, keeping handlers and metadata', () => {
    const { result } = setup()
    act(() => result.current.playQueue(songs))
    const calls = session.setActionHandler.mock.calls.length
    act(() => { action('nexttrack'); action('nexttrack'); action('nexttrack') })
    expect(result.current.current?.id).toBe(4)
    expect(session.metadata).toMatchObject({ title: songs[3].title })
    FakeAudio.latest.currentTime = 45
    act(() => action('previoustrack'))
    expect(result.current.current?.id).toBe(3)
    expect(session.setActionHandler.mock.calls.length).toBe(calls)
    expect(handlers.seekforward).toBeNull()
    expect(handlers.seekbackward).toBeNull()
    act(() => action('pause'))
    expect(session.playbackState).toBe('paused')
    act(() => action('play'))
    expect(session.playbackState).toBe('playing')
  })
  it('does not skip on 40-second premature ended, errors, stalls or late events', () => {
    const { result } = setup()
    act(() => result.current.playQueue(songs))
    act(() => FakeAudio.latest.finish(40))
    expect(result.current.current?.id).toBe(1)
    expect(result.current.playbackError).toContain('意外中断')
    act(() => result.current.toggle())
    expect(FakeAudio.latest.load).toHaveBeenCalledOnce()
    act(() => { FakeAudio.latest.emit('loadedmetadata'); FakeAudio.latest.emit('ended'); FakeAudio.latest.emit('stalled') })
    expect(result.current.current?.id).toBe(1)
    expect(FakeAudio.latest.currentTime).toBe(40)
    act(() => FakeAudio.latest.emit('error'))
    expect(result.current.current?.id).toBe(1)
  })
  it('finishes each shuffle cycle once and avoids repetition at the boundary', () => {
    const { result } = setup()
    act(() => { result.current.setPlaybackMode('shuffle'); result.current.playQueue(songs) })
    const visited = [result.current.current!.id]
    for (let i = 1; i < songs.length; i++) {
      act(() => FakeAudio.latest.finish())
      visited.push(result.current.current!.id)
    }
    expect(new Set(visited).size).toBe(songs.length)
    act(() => FakeAudio.latest.finish())
    expect(result.current.current!.id).not.toBe(visited.at(-1))
  })
  it('changes mode without restarting audio and supports repeat-one/manual next', () => {
    const { result } = setup()
    act(() => result.current.playQueue(songs))
    FakeAudio.latest.currentTime = 40
    act(() => result.current.setPlaybackMode('shuffle'))
    expect(FakeAudio.latest.currentTime).toBe(40)
    act(() => result.current.setPlaybackMode('one'))
    act(() => FakeAudio.latest.finish())
    expect(result.current.current?.id).toBe(1)
    expect(FakeAudio.latest.currentTime).toBe(0)
    act(() => action('nexttrack'))
    expect(result.current.current?.id).toBe(2)
  })
  it('does not let a rejected old play promise pause a newer song', async () => {
    const { result } = setup()
    let reject!: (error: Error) => void
    FakeAudio.latest.play.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    act(() => { result.current.playQueue(songs); result.current.next() })
    await act(async () => { reject(new Error('aborted old src')); await Promise.resolve() })
    expect(result.current.current?.id).toBe(2)
    expect(result.current.playing).toBe(true)
    expect(result.current.playbackError).toBeNull()
  })
  it('clamps queue indices and seek values and includes explicitly selected songs', () => {
    const { result } = setup()
    act(() => result.current.playQueue(songs, 999))
    expect(result.current.current?.id).toBe(6)
    FakeAudio.latest.duration = 300
    act(() => { result.current.seek(Infinity); result.current.seek(-5) })
    expect(FakeAudio.latest.currentTime).toBe(0)
    act(() => result.current.seek(500))
    expect(FakeAudio.latest.currentTime).toBe(300)
    const other = { ...songs[0], id: 20 }
    act(() => result.current.playSong(other))
    expect(result.current.queue.map((song) => song.id)).toContain(20)
  })
})
