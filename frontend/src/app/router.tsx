import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { StickyHeader } from '../components/layout/StickyHeader'
import { LoginPage } from '../pages/Auth/LoginPage'
import { RegisterPage } from '../pages/Auth/RegisterPage'
import { TopicsPage } from '../pages/Topics/TopicsPage'
import { VideosPage } from '../pages/Videos/VideosPage'
import { VideoDetailPage } from '../pages/Videos/VideoDetailPage'
import { ClipsPlaceholderPage } from '../pages/Clips/ClipsPlaceholderPage'
import { SocialsPlaceholderPage } from '../pages/Socials/SocialsPlaceholderPage'
import { PublicationsPlaceholderPage } from '../pages/Publications/PublicationsPlaceholderPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('access_token')
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-neutral-50">
      <StickyHeader />
      <main>{children}</main>
    </div>
  )
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route path="/" element={<RequireAuth><Layout><Navigate to="/videos" replace /></Layout></RequireAuth>} />

        <Route path="/topics" element={
          <RequireAuth><Layout><TopicsPage /></Layout></RequireAuth>
        } />

        <Route path="/videos" element={
          <RequireAuth><Layout><VideosPage /></Layout></RequireAuth>
        } />

        <Route path="/videos/:id" element={
          <RequireAuth><Layout><VideoDetailPage /></Layout></RequireAuth>
        } />

        <Route path="/clips" element={
          <RequireAuth><Layout><ClipsPlaceholderPage /></Layout></RequireAuth>
        } />

        <Route path="/socials" element={
          <RequireAuth><Layout><SocialsPlaceholderPage /></Layout></RequireAuth>
        } />

        <Route path="/publications" element={
          <RequireAuth><Layout><PublicationsPlaceholderPage /></Layout></RequireAuth>
        } />

        <Route path="*" element={<Navigate to="/videos" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
