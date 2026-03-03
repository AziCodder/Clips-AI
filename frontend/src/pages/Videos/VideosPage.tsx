import { useEffect, useState } from 'react'
import { videosApi, topicsApi } from '../../lib/api/client'
import type { Topic, Video, VideoListResponse } from '../../lib/types/api'
import { VideoCard } from '../../components/video/VideoCard'
import { VIDEO_STATUS_LABELS } from '../../lib/types/api'

export function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [topicFilter, setTopicFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [query, setQuery] = useState('')
  const [manualUrl, setManualUrl] = useState('')
  const [manualTopicId, setManualTopicId] = useState('')
  const [manualAutoApprove, setManualAutoApprove] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')
  const [addInfo, setAddInfo] = useState('')

  const PAGE_SIZE = 20

  const load = async (pg = 1) => {
    setLoading(true)
    setLoadError(null)
    try {
      const res = await videosApi.list({
        topic_id: topicFilter || undefined,
        status: statusFilter || undefined,
        q: query || undefined,
        page: pg,
        page_size: PAGE_SIZE,
      })
      const data: VideoListResponse = res.data
      setVideos(data.items)
      setTotal(data.total)
    } catch (err: any) {
      const d = err.response?.data?.detail
      const msg = typeof d === 'string' ? d : (d ? JSON.stringify(d) : null)
      setLoadError(msg || err.message || 'Не удалось загрузить список видео')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { topicsApi.list().then(r => setTopics(r.data)) }, [])
  useEffect(() => { load(1); setPage(1) }, [topicFilter, statusFilter, query])

  const handleAddManual = async (e: React.FormEvent) => {
    e.preventDefault()
    setAdding(true)
    setAddError('')
    setAddInfo('')
    try {
      const res = await videosApi.addManual(manualUrl, manualTopicId || undefined, manualAutoApprove)
      if (res.data?.already_exists) {
        setAddInfo('Это видео уже есть в вашем списке')
      } else {
        setManualUrl('')
        if (manualAutoApprove) {
          setAddInfo('Видео одобрено, запущено скачивание и транскрипция')
        }
      }
      load(1)
    } catch (err: any) {
      const d = err.response?.data?.detail
      const msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('. ') : (d && typeof d === 'object' ? JSON.stringify(d) : null)
      setAddError(msg || err.message || 'Ошибка добавления')
    } finally {
      setAdding(false)
    }
  }

  const statuses = Object.entries(VIDEO_STATUS_LABELS)

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <h1 className="text-xl font-semibold text-neutral-900">Видео</h1>
        <span className="text-sm text-neutral-500">{total} видео</span>
      </div>

      {/* Manual add form */}
      <form onSubmit={handleAddManual}
        className="bg-white border border-neutral-200 rounded-xl p-4 mb-6 flex flex-col sm:flex-row gap-3">
        <input
          type="url"
          value={manualUrl}
          onChange={e => setManualUrl(e.target.value)}
          placeholder="YouTube URL..."
          className="flex-1 border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900"
          required
        />
        <select value={manualTopicId} onChange={e => setManualTopicId(e.target.value)}
          className="border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 bg-white">
          <option value="">Без тематики</option>
          {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm text-neutral-600 whitespace-nowrap cursor-pointer">
          <input type="checkbox" checked={manualAutoApprove} onChange={e => setManualAutoApprove(e.target.checked)}
            className="rounded border-neutral-300" />
          Сразу запустить
        </label>
        <button type="submit" disabled={adding}
          className="bg-neutral-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-50 whitespace-nowrap transition-colors">
          {adding ? 'Добавление...' : 'Добавить'}
        </button>
        {addError && <p className="text-red-500 text-xs mt-1">{addError}</p>}
        {addInfo && <p className="text-blue-600 text-xs mt-1">{addInfo}</p>}
      </form>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Поиск..."
          className="border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 w-48" />
        <select value={topicFilter} onChange={e => setTopicFilter(e.target.value)}
          className="border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 bg-white">
          <option value="">Все тематики</option>
          {topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 bg-white">
          <option value="">Все статусы</option>
          {statuses.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
        </select>
      </div>

      {loadError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 flex items-center justify-between gap-4">
          <p className="text-red-600 text-sm">{loadError}</p>
          <button
            onClick={() => load(page)}
            className="shrink-0 text-sm font-medium text-red-700 hover:text-red-900 underline underline-offset-2"
          >
            Повторить
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-neutral-400 text-sm">Загрузка...</div>
      ) : videos.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-neutral-400 text-sm">Видео не найдено</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {videos.map(v => (
              <VideoCard key={v.id} video={v} onDeleted={() => load(page)} />
            ))}
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-3 mt-8">
              <button onClick={() => { setPage(p => p - 1); load(page - 1) }}
                disabled={page === 1}
                className="px-4 py-2 border border-neutral-200 rounded-lg text-sm text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
                Назад
              </button>
              <span className="text-sm text-neutral-500">{page} / {Math.ceil(total / PAGE_SIZE)}</span>
              <button onClick={() => { setPage(p => p + 1); load(page + 1) }}
                disabled={page >= Math.ceil(total / PAGE_SIZE)}
                className="px-4 py-2 border border-neutral-200 rounded-lg text-sm text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 transition-colors">
                Вперёд
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
