import { Disc3, Download, Library, Settings } from 'lucide-react'
import type { View } from '../App'

interface Props {
  view: View
  setView: (v: View) => void
  serverOk: boolean | null
}

const items: { key: View; label: string; icon: typeof Library }[] = [
  { key: 'library', label: '曲库', icon: Library },
  { key: 'import', label: '导入收藏夹', icon: Download },
  { key: 'settings', label: '设置', icon: Settings },
]

export default function Sidebar({ view, setView, serverOk }: Props) {
  return (
    <aside className="w-56 shrink-0 border-r border-line bg-bg2 flex flex-col">
      <div className="flex items-center gap-2.5 px-5 pt-6 pb-8">
        <div className="w-9 h-9 rounded-xl bg-accent-dim flex items-center justify-center">
          <Disc3 size={20} className="text-accent" />
        </div>
        <div>
          <div className="font-semibold text-[15px] leading-tight tracking-tight">MusicPlayer</div>
          <div className="text-[11px] text-faint">B站收藏夹曲库</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {items.map(({ key, label, icon: Icon }) => {
          const active = view === key
          return (
            <button
              key={key}
              onClick={() => setView(key)}
              className={[
                'flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition-colors text-left',
                active
                  ? 'bg-panel text-ink font-medium'
                  : 'text-muted hover:text-ink hover:bg-panel/60',
              ].join(' ')}
            >
              <Icon size={17} className={active ? 'text-accent' : ''} />
              {label}
            </button>
          )
        })}
      </nav>

      <div className="mt-auto px-5 pb-5">
        <div className="flex items-center gap-2 text-[11px] text-faint">
          <span
            className={[
              'w-2 h-2 rounded-full',
              serverOk === null ? 'bg-faint' : serverOk ? 'bg-emerald-500' : 'bg-danger',
            ].join(' ')}
          />
          {serverOk === null ? '连接中…' : serverOk ? '服务器已连接' : '服务器未连接'}
        </div>
      </div>
    </aside>
  )
}
