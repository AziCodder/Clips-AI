import { useEffect, useState } from 'react'
import { topicsApi } from '../../lib/api/client'
import type { Topic } from '../../lib/types/api'

interface TopicFormData {
  name: string
  keywords: string
  enabled: boolean
  clips_per_video: number
  prompt_for_highlights: string
}

const emptyForm: TopicFormData = {
  name: '',
  keywords: '',
  enabled: true,
  clips_per_video: 3,
  prompt_for_highlights: '',
}

export function TopicsPage() {
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<TopicFormData>(emptyForm)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await topicsApi.list()
      setTopics(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => { setEditingId(null); setForm(emptyForm); setShowForm(true) }

  const openEdit = (t: Topic) => {
    setEditingId(t.id)
    setForm({
      name: t.name,
      keywords: t.keywords.join(', '),
      enabled: t.enabled,
      clips_per_video: t.clips_per_video,
      prompt_for_highlights: t.prompt_for_highlights,
    })
    setShowForm(true)
  }

  const handleSave = async () => {
    setSaving(true)
    const payload = {
      name: form.name,
      keywords: form.keywords.split(',').map(k => k.trim()).filter(Boolean),
      enabled: form.enabled,
      clips_per_video: form.clips_per_video,
      prompt_for_highlights: form.prompt_for_highlights,
    }
    try {
      if (editingId) {
        await topicsApi.update(editingId, payload)
      } else {
        await topicsApi.create(payload)
      }
      setShowForm(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Удалить тематику?')) return
    await topicsApi.delete(id)
    load()
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-neutral-900">Тематики</h1>
        <button onClick={openCreate}
          className="bg-neutral-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors">
          + Добавить тематику
        </button>
      </div>

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl border border-neutral-200 w-full max-w-lg p-6 space-y-4">
            <h2 className="text-base font-semibold text-neutral-900">
              {editingId ? 'Редактировать тематику' : 'Новая тематика'}
            </h2>

            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Название</label>
              <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900" />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">
                Ключевые слова <span className="font-normal text-neutral-400">(через запятую)</span>
              </label>
              <input value={form.keywords} onChange={e => setForm({ ...form, keywords: e.target.value })}
                placeholder="marketing, growth hacking, startup"
                className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Клипов с видео</label>
                <input type="number" min={1} max={20} value={form.clips_per_video}
                  onChange={e => setForm({ ...form, clips_per_video: parseInt(e.target.value) || 3 })}
                  className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900" />
              </div>
              <div className="flex items-end pb-0.5">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })}
                    className="w-4 h-4 rounded border-neutral-300" />
                  <span className="text-sm text-neutral-700">Активна</span>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Промпт для выделения моментов</label>
              <textarea value={form.prompt_for_highlights}
                onChange={e => setForm({ ...form, prompt_for_highlights: e.target.value })}
                rows={4}
                placeholder="Найди самые эмоциональные и ценные моменты..."
                className="w-full border border-neutral-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900 resize-none" />
            </div>

            <div className="flex gap-3 justify-end pt-2">
              <button onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-neutral-600 hover:text-neutral-900 transition-colors">
                Отмена
              </button>
              <button onClick={handleSave} disabled={saving || !form.name}
                className="bg-neutral-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-50 transition-colors">
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-neutral-400 text-sm py-12 text-center">Загрузка...</div>
      ) : topics.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-neutral-400 text-sm mb-4">Тематик пока нет</p>
          <button onClick={openCreate}
            className="bg-neutral-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-neutral-800">
            Добавить первую тематику
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {topics.map(t => (
            <div key={t.id} className="bg-white border border-neutral-200 rounded-xl p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-neutral-900">{t.name}</h3>
                    {!t.enabled && (
                      <span className="text-xs bg-neutral-100 text-neutral-500 px-2 py-0.5 rounded-full">Неактивна</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {t.keywords.map((kw, i) => (
                      <span key={i} className="text-xs bg-neutral-100 text-neutral-600 px-2 py-0.5 rounded-full">
                        {kw}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-neutral-500">{t.clips_per_video} клипов с видео</p>
                  {t.prompt_for_highlights && (
                    <p className="text-xs text-neutral-400 mt-1 line-clamp-1">{t.prompt_for_highlights}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => openEdit(t)}
                    className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors px-2 py-1 rounded hover:bg-neutral-100">
                    Изменить
                  </button>
                  <button onClick={() => handleDelete(t.id)}
                    className="text-sm text-red-500 hover:text-red-700 transition-colors px-2 py-1 rounded hover:bg-red-50">
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
