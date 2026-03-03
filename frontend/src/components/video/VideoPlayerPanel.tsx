import { useEffect, useRef } from 'react'

interface Props {
  presignedUrl: string | null
  title?: string  // reserved for future use (aria-label, etc.)
}

export function VideoPlayerPanel({ presignedUrl, title: _title }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (videoRef.current && presignedUrl) {
      videoRef.current.src = presignedUrl
    }
  }, [presignedUrl])

  if (!presignedUrl) {
    return (
      <div className="aspect-video bg-neutral-100 rounded-xl flex items-center justify-center text-neutral-400">
        <div className="text-center">
          <svg className="w-12 h-12 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm">Видео недоступно</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl overflow-hidden bg-black">
      <video
        ref={videoRef}
        controls
        className="w-full aspect-video"
        preload="metadata"
      >
        <source src={presignedUrl} type="video/mp4" />
        Ваш браузер не поддерживает видео.
      </video>
    </div>
  )
}
