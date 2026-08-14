import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Disc3,
  ListMusic,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  X,
} from 'lucide-react'
import { usePlayer } from '../hooks/usePlayer'
import { api } from '../lib/api'
import { currentLineIndex, fmtTime, lrcToPlain, parseLrc } from '../lib/lrc'

export default function PlayerBar() {
  const { current, playing, time, duration, volume, toggle, next, prev, seek, setVolume, queue } =
    usePlayer()
  const [expanded, setExpanded] = useState(false)
  const [lyrics, setLyrics] = useState<string | null>(null)
  const lyricBoxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!current) {
      setLyrics(null)
      return
    }
    let alive = true
    api.song(current.id)
      .then((s) => alive && setLyrics(s.lrc || s.lyrics || null))
      .catch(() => alive && setLyrics(null))
    return () => { alive = false }
  }, [current?.id])

  const lrcLines = useMemo(() => parseLrc(lyrics), [lyrics])
  const plain = useMemo(() => (lyrics && !lrcLines.length ? lrcToPlain(lyrics) : ''), [lyrics, lrcLines])
  const activeLine = useMemo(() => currentLineIndex(lrcLines, time), [lrcLines, time])

  useEffect(() => {
    if (!expanded || !lrcLines.length) return
    const box = lyricBoxRef.current
    if (!box) return
    const el = box.querySelector<HTMLElement>(`[data-line="${activeLine}"]`)
    if (el) {
      box.scrollTo({ top: el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2, behavior: 'smooth' })
    }
  }, [activeLine, expanded, lrcLines])

  if (!current) return null

  const pct = duration > 0 ? (time / duration) * 100 : 0
  const volPct = volume * 100

  const sliderStyle = (p: number) =>
    ({ '--range-bg': `linear-gradient(to right, #d97757 ${p}%, #3a362f ${p}%)` }) as React.CSSProperties

  const Cover = ({ className, spin }: { className?: string; spin?: boolean }) => {
    const url = api.coverUrl(current)
    if (!url) {
      return (
        <div className={`flex items-center justify-center bg-panel2 ${className ?? ''}`}>
          <Disc3 size={24} className="text-faint" />
        </div>
      )
    }
    return <img src={url} alt="" className={`object-cover ${spin ? 'spin-slow rounded-full' : ''} ${className ?? ''}`} />
  }

  return (
    <>
      {/* 底部播放条 */}
      <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-line bg-bg2/90 backdrop-blur-xl">
        <div className="max-w-[1400px] mx-auto px-4 h-[76px] flex items-center gap-4">
          <div className="flex items-center gap-3 w-72 min-w-0">
            <Cover className="w-12 h-12 rounded-lg shrink-0" />
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">{current.title}</div>
              <div className="text-xs text-muted truncate">{current.artist}</div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 mx-auto">
            <button onClick={prev} className="p-2 rounded-full text-muted hover:text-ink transition-colors">
              <SkipBack size={19} fill="currentColor" />
            </button>
            <button
              onClick={toggle}
              className="w-11 h-11 rounded-full bg-accent hover:bg-accent-soft text-white flex items-center justify-center transition-colors"
            >
              {playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" className="ml-0.5" />}
            </button>
            <button onClick={next} className="p-2 rounded-full text-muted hover:text-ink transition-colors">
              <SkipForward size={19} fill="currentColor" />
            </button>
          </div>

          <div className="flex-1 max-w-xl flex items-center gap-3">
            <span className="text-[11px] text-faint tabular-nums w-9 text-right">{fmtTime(time)}</span>
            <input
              type="range"
              min={0}
              max={duration || 1}
              step={0.5}
              value={time}
              onChange={(e) => seek(Number(e.target.value))}
              className="flex-1"
              style={sliderStyle(pct)}
            />
            <span className="text-[11px] text-faint tabular-nums w-9">{fmtTime(duration)}</span>
          </div>

          <div className="hidden md:flex items-center gap-2 w-40">
            <Volume2 size={16} className="text-faint shrink-0" />
            <input
              type="range"
              min={0}
              max={1}
              step={0.02}
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              className="w-20"
              style={sliderStyle(volPct)}
            />
          </div>

          <button
            onClick={() => setExpanded((v) => !v)}
            className="p-2 rounded-lg text-muted hover:text-ink transition-colors"
            title={expanded ? '收起' : '展开播放器（歌词）'}
          >
            {expanded ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
          </button>
        </div>
      </div>

      {/* 展开的全屏播放器 + 歌词 */}
      {expanded && (
        <div className="fixed inset-0 z-50 bg-bg/97 backdrop-blur-2xl flex flex-col fade-in-up">
          <div className="flex items-center justify-between px-8 pt-6">
            <div className="flex items-center gap-2 text-sm text-muted">
              <ListMusic size={15} className="text-accent" />
              {queue.length > 1 ? `播放队列 ${queue.length} 首` : '单曲播放'}
            </div>
            <button
              onClick={() => setExpanded(false)}
              className="p-2.5 rounded-xl bg-panel border border-line text-muted hover:text-ink transition-colors"
            >
              <X size={17} />
            </button>
          </div>

          <div className="flex-1 min-h-0 flex items-center justify-center gap-16 px-12 py-8 max-w-6xl mx-auto w-full">
            {/* 封面 */}
            <div className="hidden md:flex flex-col items-center gap-8">
              <div className={`w-72 h-72 rounded-full overflow-hidden shadow-2xl ${playing ? '' : 'spin-slow-paused'}`}>
                <Cover className="w-full h-full" spin />
              </div>
              <div className="text-center">
                <div className="text-xl font-semibold">{current.title}</div>
                <div className="text-sm text-muted mt-1">{current.artist}</div>
                {current.album && <div className="text-xs text-faint mt-1">{current.album}</div>}
              </div>
            </div>

            {/* 歌词 */}
            <div className="flex-1 min-w-0 max-w-xl h-full flex flex-col">
              <div className="flex-1 min-h-0 overflow-y-auto py-16" ref={lyricBoxRef}>
                {lrcLines.length > 0 ? (
                  <div className="flex flex-col items-center gap-3.5">
                    {lrcLines.map((line, i) => {
                      const active = i === activeLine
                      return (
                        <button
                          key={`${line.time}-${i}`}
                          data-line={i}
                          onClick={() => seek(line.time)}
                          className={`lyric-line text-center transition-all ${
                            active
                              ? 'text-ink text-2xl font-medium scale-105'
                              : 'text-muted text-lg hover:text-ink/80'
                          }`}
                        >
                          {line.text || '♪'}
                        </button>
                      )
                    })}
                  </div>
                ) : plain ? (
                  <p className="whitespace-pre-wrap text-center text-muted leading-loose text-base">{plain}</p>
                ) : (
                  <p className="text-center text-faint text-sm pt-20">这首歌没有找到歌词</p>
                )}
              </div>

              {/* 控制区 */}
              <div className="flex flex-col items-center gap-4 pb-2">
                <div className="flex items-center gap-3 w-full max-w-md">
                  <span className="text-[11px] text-faint tabular-nums w-9 text-right">{fmtTime(time)}</span>
                  <input
                    type="range"
                    min={0}
                    max={duration || 1}
                    step={0.5}
                    value={time}
                    onChange={(e) => seek(Number(e.target.value))}
                    className="flex-1"
                    style={sliderStyle(pct)}
                  />
                  <span className="text-[11px] text-faint tabular-nums w-9">{fmtTime(duration)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={prev} className="p-3 rounded-full text-muted hover:text-ink transition-colors">
                    <SkipBack size={22} fill="currentColor" />
                  </button>
                  <button
                    onClick={toggle}
                    className="w-14 h-14 rounded-full bg-accent hover:bg-accent-soft text-white flex items-center justify-center transition-colors"
                  >
                    {playing ? (
                      <Pause size={24} fill="currentColor" />
                    ) : (
                      <Play size={24} fill="currentColor" className="ml-1" />
                    )}
                  </button>
                  <button onClick={next} className="p-3 rounded-full text-muted hover:text-ink transition-colors">
                    <SkipForward size={22} fill="currentColor" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
