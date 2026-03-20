export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-border ${className}`} />
}

export function StatCardSkeleton() {
  return (
    <div
      className="anim-card rounded-xl border border-border border-l-4 border-l-border bg-card p-5"
      style={{ boxShadow: 'var(--shadow-card)' }}
    >
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-3 h-7 w-28" />
    </div>
  )
}
