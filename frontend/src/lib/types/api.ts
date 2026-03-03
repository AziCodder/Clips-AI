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
  found: 'Найдено',
  pending_approval: 'На подтверждении',
  approved: 'Одобрено',
  rejected: 'Отклонено',
  downloading: 'Скачивается',
  downloaded: 'Скачано',
  audio_ready: 'Аудио готово',
  queued_gpu: 'В очереди GPU',
  transcribing: 'Транскрибируется',
  transcribed: 'Транскрибировано',
  analyzing: 'Анализируется',
  analyzed: 'Проанализировано',
  clips_rendering: 'Нарезка клипов',
  clips_ready: 'Клипы готовы',
  failed: 'Ошибка',
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
  clips_ready: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}
