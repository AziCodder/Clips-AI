import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  register: (email: string, password: string, telegram_id?: number) =>
    api.post('/auth/register', { email, password, telegram_id }),
  me: () => api.get('/auth/me'),
}

// ── Topics ────────────────────────────────────────────────────────────────────
export const topicsApi = {
  list: () => api.get('/topics'),
  create: (data: object) => api.post('/topics', data),
  update: (id: string, data: object) => api.patch(`/topics/${id}`, data),
  delete: (id: string) => api.delete(`/topics/${id}`),
}

// ── Videos ────────────────────────────────────────────────────────────────────
export const videosApi = {
  list: (params?: object) => api.get('/videos', { params }),
  get: (id: string) => api.get(`/videos/${id}`),
  addManual: (url: string, topic_id?: string, auto_approve?: boolean) =>
    api.post('/videos/manual', { url, topic_id, auto_approve: auto_approve ?? false }),
  upload: (file: File, title: string, topic_id: string, auto_process: boolean, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    form.append('topic_id', topic_id)
    form.append('auto_process', String(auto_process))
    return api.post('/videos/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => { if (onProgress && e.total) onProgress(Math.round(e.loaded * 100 / e.total)) },
    })
  },
  requestAnalysis: (id: string) =>
    api.post(`/videos/${id}/request-analysis`),
  recomputeHighlights: (id: string) =>
    api.post(`/videos/${id}/recompute-highlights`),
  refreshMetadata: (id: string) =>
    api.post(`/videos/${id}/refresh-metadata`),
  /** @param videoId — id видео (не approval), для которого выносится решение */
  approve: (videoId: string, status: 'approved' | 'rejected') =>
    api.post(`/approvals/${videoId}`, { status }),
  /** Удалить всё: видео, нарезки, тексты. Либо только видео/текст/описание, нарезки остаются. */
  delete: (id: string, scope: 'all' | 'video_only') =>
    api.delete(`/videos/${id}`, { params: { scope } }),
}

// ── Media ─────────────────────────────────────────────────────────────────────
export const mediaApi = {
  presigned: (video_id: string, asset_type: string, clip_id?: string) =>
    api.get('/media/presigned', { params: { video_id, asset_type, clip_id } }),
  transcript: (video_id: string) =>
    api.get(`/media/videos/${video_id}/transcript`),
  highlights: (video_id: string) =>
    api.get(`/media/videos/${video_id}/highlights`),
  clips: (video_id: string) =>
    api.get(`/media/videos/${video_id}/clips`),
}
