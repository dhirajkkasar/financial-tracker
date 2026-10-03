'use client'

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-loss/30 bg-loss-subtle/40 px-4 py-3 text-sm">
      <p className="text-loss">{message}</p>
      <button
        onClick={onRetry ?? (() => window.location.reload())}
        className="shrink-0 rounded-lg border border-loss/40 px-3 py-1 text-xs font-medium text-loss hover:bg-loss/10 transition-colors"
      >
        Retry
      </button>
    </div>
  )
}
