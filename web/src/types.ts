export interface Song {
  id: number
  bvid: string
  job_id: string
  title: string
  artist: string
  album: string
  duration: number | null
  raw_title: string
  uploader: string
  tags: string[]
  cover_url: string | null
  cover: string | null
  file_path: string | null
  lyrics: string | null
  lrc: string | null
  lyrics_source: string | null
  status: 'pending' | 'downloading' | 'ready' | 'error'
  error: string | null
  created_at: string
}

export interface Job {
  id: string
  url: string
  media_id: string
  title: string
  status: 'parsed' | 'downloading' | 'done' | 'error'
  total: number
  done: number
  failed: number
  message: string | null
  created_at: string
}

export interface JobDetail {
  job: Job
  songs: Song[]
}
