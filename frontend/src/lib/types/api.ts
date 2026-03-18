export interface Topic {
  id: string
  name: string
  keywords: string[]
  enabled: boolean
  clips_per_video: number
  prompt_for_highlights: string
  created_at: string
  updated_at: string
}

export interface Video {
  id: string
  topic_id: string | null
  source: string
  source_id: string
  url: string
  title: string
  channel: string
  views: number
  duration_sec: number
  status: string
  download_progress_pct?: number | null
  error_message?: string | null
  thumbnail_url: string
  created_at: string
}

export interface VideoDetail extends Video {
  description: string
  likes: number
  publish_date: string | null
}

export interface VideoListResponse {
  items: Video[]
  total: number
  page: number
  page_size: number
}

export interface Highlight {
  id: string
  video_id: string
  start_sec: number
  end_sec: number
  score: number
  title: string
  reason: string
  created_at: string
}

export interface Clip {
  id: string
  highlight_id: string
  status: string
  s3_clip_key: string
  created_at: string
  presigned_url: string | null
}

export interface WordEntry {
  word: string
  start: number
  end: number
}

export interface SegmentEntry {
  start: number
  end: number
  text: string
}

export interface Transcript {
  text: string
  words: WordEntry[]
  segments: SegmentEntry[]
  language: string | null
  job_id: string | null
}

export interface PresignedUrl {
  url: string
  expires_in_sec: number
  asset_type: string
}

export interface User {
  id: string
  email: string
  telegram_id: number | null
  role: string
  is_active: boolean
}
export const VIDEO_STATUS_LABELS: Record<string, string> = {
  found: '\u041d\u0430\u0439\u0434\u0435\u043d\u043e',
  pending_approval: '\u041d\u0430 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0438',
  approved: '\u041e\u0434\u043e\u0431\u0440\u0435\u043d\u043e',
  rejected: '\u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u043e',
  downloading: '\u0421\u043a\u0430\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f',
  downloaded: '\u0421\u043a\u0430\u0447\u0430\u043d\u043e',
  audio_ready: '\u0410\u0443\u0434\u0438\u043e \u0433\u043e\u0442\u043e\u0432\u043e',
  queued_gpu: '\u0412 \u043e\u0447\u0435\u0440\u0435\u0434\u0438 GPU',
  transcribing: '\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u0443\u0435\u0442\u0441\u044f',
  transcribed: '\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u043e\u0432\u0430\u043d\u043e',
  analyzing: '\u0410\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0435\u0442\u0441\u044f',
  analyzed: '\u041f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u043e',
  clips_rendering: '\u041d\u0430\u0440\u0435\u0437\u043a\u0430 \u043a\u043b\u0438\u043f\u043e\u0432',
  uploaded: '\u0417\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e',
  clips_ready: '\u041a\u043b\u0438\u043f\u044b \u0433\u043e\u0442\u043e\u0432\u044b',
  failed: '\u041e\u0448\u0438\u0431\u043a\u0430',
}

export const STATUS_COLORS: Record<string, string> = {
  found: 'bg-neutral-100 text-neutral-600',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  downloading: 'bg-blue-100 text-blue-800',
  downloaded: 'bg-blue-100 text-blue-800',
  audio_ready: 'bg-blue-100 text-blue-800',
  queued_gpu: 'bg-purple-100 text-purple-800',
  transcribing: 'bg-purple-100 text-purple-800',
  transcribed: 'bg-indigo-100 text-indigo-800',
  analyzing: 'bg-indigo-100 text-indigo-800',
  analyzed: 'bg-indigo-100 text-indigo-800',
  clips_rendering: 'bg-orange-100 text-orange-800',
  uploaded: 'bg-sky-100 text-sky-800',
  clips_ready: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}
