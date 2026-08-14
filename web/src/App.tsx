import { useEffect, useState } from 'react'
import { api } from './lib/api'
import { PlayerProvider } from './hooks/usePlayer'
import Sidebar from './components/Sidebar'
import LibraryView from './components/LibraryView'
import ImportView from './components/ImportView'
import SettingsView from './components/SettingsView'
import PlayerBar from './components/PlayerBar'
import type { Song } from './types'

export type View = 'library' | 'import' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('library')
  const [songs, setSongs] = useState<Song[]>([])
  const [serverOk, setServerOk] = useState<boolean | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let alive = true
    api.health()
      .then(() => alive && setServerOk(true))
      .catch(() => alive && setServerOk(false))
    return () => { alive = false }
  }, [refreshKey])

  useEffect(() => {
    if (!serverOk) return
    let alive = true
    api.songs()
      .then((s) => alive && setSongs(s))
      .catch(() => alive && setServerOk(false))
    return () => { alive = false }
  }, [serverOk, refreshKey])

  return (
    <PlayerProvider>
      <div className="flex h-full">
        <Sidebar view={view} setView={setView} serverOk={serverOk} />
        <main className="flex-1 min-w-0 overflow-y-auto pb-28">
          {view === 'library' && (
            <LibraryView
              songs={songs}
              serverOk={serverOk}
              onRefresh={() => setRefreshKey((k) => k + 1)}
              onGoImport={() => setView('import')}
            />
          )}
          {view === 'import' && (
            <ImportView
              onImported={() => {
                setRefreshKey((k) => k + 1)
                setView('library')
              }}
              onViewLibrary={() => setView('library')}
            />
          )}
          {view === 'settings' && (
            <SettingsView
              onSaved={() => setRefreshKey((k) => k + 1)}
            />
          )}
        </main>
        <PlayerBar />
      </div>
    </PlayerProvider>
  )
}
