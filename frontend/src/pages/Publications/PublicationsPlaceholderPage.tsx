export function PublicationsPlaceholderPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-neutral-100 mb-4">
        <svg className="w-8 h-8 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
        </svg>
      </div>
      <h1 className="text-lg font-semibold text-neutral-900 mb-2">Публикации</h1>
      <p className="text-neutral-500 text-sm">
        Автопостинг и планировщик публикаций будут доступны в следующей версии
      </p>
      <span className="inline-block mt-4 px-3 py-1 bg-neutral-100 text-neutral-500 text-xs rounded-full">
        Coming soon
      </span>
    </div>
  )
}
