export interface Part {
  cid: number
  page: number
  part: string
  duration: number
}

export interface Song {
  id: number
  bvid: string
  job_id: string
  title: string
  artist: string
  album: string
  duration: number | null
  cid: number | null
  part_index: number | null
  part_title: string | null
  parts: Part[] | null
  source_url: string | null
  downloaded_cid: number | null
  raw_title: string
  uploader: string
  tags: string[]
  cover_url: string | null
  cover: string | null
  file_path: string | null
  lyrics: string | null
  lrc: string | null
  lyrics_source: string | null
  lyrics_enabled: boolean
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
