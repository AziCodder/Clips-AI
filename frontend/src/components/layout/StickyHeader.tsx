import { Link, useLocation } from 'react-router-dom'

const NAV_ITEMS = [
  { path: '/topics', label: 'Тематики' },
  { path: '/videos', label: 'Видео' },
  { path: '/clips', label: 'Клипы' },
  { path: '/socials', label: 'Соцсети' },
  { path: '/publications', label: 'Публикации' },
]

export function StickyHeader() {
  const { pathname } = useLocation()

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
  }

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-neutral-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/videos" className="flex items-center gap-2">
            <span className="text-lg font-bold text-neutral-900 tracking-tight">Clips AI</span>
          </Link>

          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  pathname.startsWith(item.path)
                    ? 'bg-neutral-900 text-white'
                    : 'text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <button
            onClick={handleLogout}
            className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
          >
            Выйти
          </button>
        </div>
      </div>
    </header>
  )
}
