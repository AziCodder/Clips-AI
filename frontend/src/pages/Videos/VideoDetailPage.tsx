import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { videosApi, mediaApi } from '../../lib/api/client'
import type { VideoDetail, Transcript, Highlight, Clip } from '../../lib/types/api'
import { VIDEO_STATUS_LABELS, STATUS_COLORS } from '../../lib/types/api'
import { VideoPlayerPanel } from '../../components/video/VideoPlayerPanel'

// ── Pipeline stages ────────────────────────────────────────────────────────
const PIPELINE_STAGES: { key: string; label: string }[] = [
  { key: 'approved',        label: 'Одобрено' },
  { key: 'downloading',     label: 'Скачивание' },
  { key: 'audio_ready',     label: 'Аудио' },
  { key: 'queued_gpu',      label: 'Очередь GPU' },
  { key: 'transcribing',    label: 'Транскрипция' },
  { key: 'transcribed',     label: 'Транскрибировано' },
  { key: 'analyzing',       label: 'Анализ ИИ' },
  { key: 'analyzed',        label: 'Проанализировано' },
  { key: 'clips_rendering', label: 'Нарезка' },
  { key: 'clips_ready',     label: 'Клипы готовы' },
]
const STAGE_ORDER = PIPELINE_STAGES.map(s => s.key)

function PipelineProgress({
  status,
  errorMessage,
  downloadProgressPct,
}: {
  status: string
  errorMessage?: string | null
  downloadProgressPct?: number | null
}) {
  if (['pending_approval', 'found', 'rejected'].includes(status)) return null
  const failed = status === 'failed'
  const currentIdx = failed ? -1 : STAGE_ORDER.indexOf(status)
  const safePct = Math.max(0, Math.min(100, Number(downloadProgressPct ?? 0)))

  return (
    <div className="bg-white border border-neutral-200 rounded-xl p-4">
      <h3 className="text-xs font-semibold text-neutral-500 uppercase tracking-wide mb-3">
        Этапы обработки
      </h3>
      <div className="space-y-1.5">
        {PIPELINE_STAGES.map((stage, idx) => {
          const done   = !failed && currentIdx > idx
          const active = !failed && currentIdx === idx

          return (
            <div key={stage.key} className="flex items-center gap-2.5">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-xs font-bold
                ${done    ? 'bg-emerald-500 text-white'
                : active  ? 'bg-blue-500 text-white animate-pulse'
                : 'bg-neutral-200 text-neutral-400'}`}>
                {done ? '✓' : idx + 1}
              </div>
              <span className={`text-xs ${done ? 'text-emerald-700 font-medium' : active ? 'text-blue-700 font-semibold' : 'text-neutral-400'}`}>
                {stage.label}
              </span>
              {active && (
                <span className="text-xs text-blue-400 ml-auto">● сейчас</span>
              )}
            </div>
          )
        })}
        {failed && (
          <div className="mt-1 space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center shrink-0 text-xs font-bold">✕</div>
              <span className="text-xs text-red-600 font-semibold">Ошибка обработки</span>
            </div>
            {errorMessage && (
              <p className="text-xs text-red-700 bg-red-50 rounded p-2 mt-1 break-words">{errorMessage}</p>
            )}
          </div>
        )}
      </div>
      {status === 'downloading' && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-blue-700 mb-1">
            <span className="font-medium">Скачивание видео</span>
            <span>{safePct}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-blue-100 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${safePct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function VideoDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [video, setVideo] = useState<VideoDetail | null>(null)
  const [presignedUrl, setPresignedUrl] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'transcript' | 'highlights' | 'clips'>('transcript')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [refreshMetaLoading, setRefreshMetaLoading] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  const TERMINAL_STATUSES = ['transcribed', 'analyzed', 'clips_ready', 'failed', 'rejected', 'pending_approval']
  const isProcessing = (s: string) => !TERMINAL_STATUSES.includes(s) && s !== 'approved'

  const loadAll = useCallback(async (initial = false) => {
    if (!id) return
    if (initial) setLoading(true)
    const presignedPromise =
      !initial && presignedUrl
        ? Promise.resolve(null)
        : mediaApi.presigned(id, 'master_video').catch(() => null)
    const [videoRes, presRes, transcRes, hlRes, clipRes] = await Promise.all([
      videosApi.get(id),
      presignedPromise,
      mediaApi.transcript(id).catch(() => null),
      mediaApi.highlights(id).catch(() => null),
      mediaApi.clips(id).catch(() => null),
    ])
    setVideo(videoRes.data)
    const nextPresigned = presRes?.data?.url ?? null
    setPresignedUrl((prev) => prev ?? nextPresigned)
    setTranscript(transcRes?.data ?? null)
    setHighlights(hlRes?.data ?? [])
    setClips(clipRes?.data ?? [])
    if (initial) setLoading(false)
    return videoRes.data.status
  }, [id, presignedUrl])

  // Initial load
  useEffect(() => {
    loadAll(true)
  }, [loadAll])

  // Auto-refresh every 8s while video is being processed
  useEffect(() => {
    if (!video) return
    if (!isProcessing(video.status)) return
    const intervalMs = video.status === 'downloading' ? 2000 : 8000
    const timer = setInterval(async () => {
      const newStatus = await loadAll()
      if (newStatus && !isProcessing(newStatus)) clearInterval(timer)
    }, intervalMs)
    return () => clearInterval(timer)
  }, [video?.status, loadAll])

  const handleRequestAnalysis = async () => {
    if (!id) return
    setAnalysisLoading(true)
    try {
      await videosApi.requestAnalysis(id)
      const res = await videosApi.get(id)
      setVideo(res.data)
    } finally {
      setAnalysisLoading(false)
    }
  }

  const handleRecompute = async () => {
    if (!id) return
    setAnalysisLoading(true)
    try {
      await videosApi.recomputeHighlights(id)
      const hlRes = await mediaApi.highlights(id)
      setHighlights(hlRes.data)
    } finally {
      setAnalysisLoading(false)
    }
  }

  const handleRefreshMetadata = async () => {
    if (!id) return
    setRefreshMetaLoading(true)
    try {
      const res = await videosApi.refreshMetadata(id)
      setVideo(res.data)
    } finally {
      setRefreshMetaLoading(false)
    }
  }

  const seekTo = (sec: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = sec
      videoRef.current.play()
    }
  }

  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-center text-neutral-400 text-sm">
        Загрузка...
      </div>
    )
  }

  if (!video) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-center">
        <p className="text-neutral-500">Видео не найдено</p>
        <Link to="/videos" className="text-sm text-neutral-900 underline mt-2 inline-block">← Назад</Link>
      </div>
    )
  }

  const statusLabel = VIDEO_STATUS_LABELS[video.status] ?? video.status
  const statusColor = STATUS_COLORS[video.status] ?? 'bg-neutral-100 text-neutral-600'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-4">
        <Link to="/videos" className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors">
          ← Все видео
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Player + Info */}
        <div className="lg:col-span-2 space-y-4">
          <div ref={videoRef as any}>
            <VideoPlayerPanel presignedUrl={presignedUrl} title={video.title} />
          </div>

          <div>
            <h1 className="text-lg font-semibold text-neutral-900 mb-2">{video.title}</h1>
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColor}`}>
                {statusLabel}
              </span>
              <span className="text-sm text-neutral-500">{video.channel}</span>
              <span className="text-sm text-neutral-400">
                {Math.floor(video.duration_sec / 60)} мин
              </span>
              <span className="text-sm text-neutral-400">
                {video.views.toLocaleString()} просмотров
              </span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-2">
            {presignedUrl && (
              <a href={presignedUrl} download
                className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
                Скачать
              </a>
            )}
            <button
              onClick={handleRequestAnalysis}
              disabled={analysisLoading}
              className="inline-flex items-center gap-1.5 bg-emerald-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors">
              {analysisLoading ? 'Обработка...' : 'ИИ-выжимка'}
            </button>
            <button
              onClick={handleRecompute}
              disabled={analysisLoading}
              className="inline-flex items-center gap-1.5 bg-amber-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-amber-600 disabled:opacity-50 transition-colors">
              Пересчитать
            </button>
            <button
              onClick={handleRefreshMetadata}
              disabled={refreshMetaLoading}
              title="Обновить длительность и просмотры по ссылке"
              className="inline-flex items-center gap-1.5 bg-sky-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-sky-600 disabled:opacity-50 transition-colors">
              {refreshMetaLoading ? 'Обновление...' : 'Обновить статистику'}
            </button>
            <button
              disabled
              title="Редактирование недоступно в MVP"
              className="inline-flex items-center gap-1.5 bg-red-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium opacity-40 cursor-not-allowed">
              Обрезать
            </button>
          </div>

          {video.description && (
            <details className="group">
              <summary className="text-sm text-neutral-500 cursor-pointer hover:text-neutral-900">
                Описание
              </summary>
              <p className="mt-2 text-sm text-neutral-600 leading-relaxed whitespace-pre-wrap">
                {video.description}
              </p>
            </details>
          )}
        </div>

        {/* Right: Pipeline + Tabs */}
        <div className="space-y-4">
          <PipelineProgress
            status={video.status}
            errorMessage={video.error_message}
            downloadProgressPct={video.download_progress_pct}
          />

          <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg">
            {(['transcript', 'highlights', 'clips'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-white text-neutral-900 shadow-sm'
                    : 'text-neutral-500 hover:text-neutral-700'
                }`}>
                {tab === 'transcript' ? 'Транскрипт' : tab === 'highlights' ? 'Моменты' : 'Клипы'}
              </button>
            ))}
          </div>

          <div className="bg-white border border-neutral-200 rounded-xl p-4 max-h-[600px] overflow-y-auto">
            {activeTab === 'transcript' && (
              transcript ? (
                <div className="space-y-2">
                  {transcript.segments.map((seg, i) => (
                    <button key={i} onClick={() => seekTo(seg.start)}
                      className="w-full text-left p-2 rounded-lg hover:bg-neutral-50 transition-colors group">
                      <span className="text-xs text-neutral-400 group-hover:text-neutral-600 block mb-0.5">
                        {formatTime(seg.start)} – {formatTime(seg.end)}
                      </span>
                      <span className="text-sm text-neutral-700">{seg.text}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-400 py-8 text-center">
                  Транскрипт недоступен
                </p>
              )
            )}

            {activeTab === 'highlights' && (
              highlights.length > 0 ? (
                <div className="space-y-3">
                  {highlights.map(h => (
                    <button key={h.id} onClick={() => seekTo(h.start_sec)}
                      className="w-full text-left p-3 rounded-lg border border-neutral-100 hover:border-neutral-200 hover:bg-neutral-50 transition-all">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-neutral-900">{h.title}</span>
                        <span className="text-xs text-neutral-400">
                          {formatTime(h.start_sec)}–{formatTime(h.end_sec)}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-500 line-clamp-2">{h.reason}</p>
                      <div className="mt-1.5">
                        <div className="h-1 bg-neutral-100 rounded-full">
                          <div className="h-1 bg-emerald-500 rounded-full" style={{ width: `${h.score * 100}%` }} />
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-400 py-8 text-center">
                  Моменты не найдены. Запустите ИИ-анализ.
                </p>
              )
            )}

            {activeTab === 'clips' && (
              clips.length > 0 ? (
                <div className="space-y-3">
                  {clips.map(c => (
                    <div key={c.id} className="border border-neutral-100 rounded-lg overflow-hidden">
                      {c.presigned_url && (
                        <video src={c.presigned_url} controls className="w-full aspect-video bg-black" />
                      )}
                      <div className="p-2 flex justify-end">
                        {c.presigned_url && (
                          <a href={c.presigned_url} download
                            className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                            Скачать клип
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-400 py-8 text-center">
                  Клипы ещё не готовы
                </p>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
