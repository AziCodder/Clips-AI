import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { videosApi } from '../../lib/api/client'
import type { Video } from '../../lib/types/api'
import { STATUS_COLORS, VIDEO_STATUS_LABELS } from '../../lib/types/api'

interface Props {
  video: Video
  onDeleted?: () => void
}

function formatDuration(sec: number) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatViews(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toString()
}

export function VideoCard({ video, onDeleted }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [deleting, setDeleting] = useState<'all' | 'video_only' | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [menuOpen])

  const handleDelete = async (scope: 'all' | 'video_only') => {
    setDeleting(scope)
    try {
      await videosApi.delete(video.id, scope)
      setMenuOpen(false)
      onDeleted?.()
    } finally {
      setDeleting(null)
    }
  }

  const statusLabel = VIDEO_STATUS_LABELS[video.status] ?? video.status
  const statusColor = STATUS_COLORS[video.status] ?? 'bg-neutral-100 text-neutral-600'

  return (
    <div className="relative bg-white border border-neutral-200 rounded-xl overflow-hidden hover:border-neutral-300 hover:shadow-sm transition-all">
      {/* Кнопка меню — три точки справа */}
      <div className="absolute top-2 right-2 z-10" ref={menuRef}>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setMenuOpen((v) => !v)
          }}
          className="p-1.5 rounded-lg bg-white/90 hover:bg-white shadow-sm border border-neutral-200 text-neutral-600 hover:text-neutral-900 transition-colors"
          aria-label="Меню"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="6" r="1.5" />
            <circle cx="12" cy="12" r="1.5" />
            <circle cx="12" cy="18" r="1.5" />
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 w-48 py-1 bg-white border border-neutral-200 rounded-lg shadow-lg z-20">
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleDelete('all')
              }}
              disabled={deleting !== null}
              className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {deleting === 'all' ? 'Удаление…' : 'Удалить всё'}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                handleDelete('video_only')
              }}
              disabled={deleting !== null}
              className="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"
            >
              {deleting === 'video_only' ? 'Удаление…' : 'Удалить видео'}
            </button>
          </div>
        )}
      </div>

      <Link to={`/videos/${video.id}`} className="group block">
        <div className="relative aspect-video bg-neutral-100 overflow-hidden">
          {video.thumbnail_url ? (
            <img
              src={video.thumbnail_url}
              alt={video.title}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-neutral-400">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M15 10l4.553-2.277A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
            </div>
          )}
          <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
            {formatDuration(video.duration_sec)}
          </div>
        </div>

        <div className="p-3">
          <h3 className="text-sm font-medium text-neutral-900 line-clamp-2 leading-snug mb-1.5">
            {video.title || 'Без названия'}
          </h3>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-neutral-500 truncate">{video.channel}</span>
            <span className="text-xs text-neutral-400 shrink-0">{formatViews(video.views)}</span>
          </div>
          <div className="mt-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColor}`}>
              {statusLabel}
            </span>
          </div>
        </div>
      </Link>
    </div>
  )
}
