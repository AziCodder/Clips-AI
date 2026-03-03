export function SocialsPlaceholderPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-neutral-100 mb-4">
        <svg className="w-8 h-8 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
        </svg>
      </div>
      <h1 className="text-lg font-semibold text-neutral-900 mb-2">Соцсети</h1>
      <p className="text-neutral-500 text-sm">
        Интеграция с социальными сетями будет доступна в следующей версии
      </p>
      <span className="inline-block mt-4 px-3 py-1 bg-neutral-100 text-neutral-500 text-xs rounded-full">
        Coming soon
      </span>
    </div>
  )
}
