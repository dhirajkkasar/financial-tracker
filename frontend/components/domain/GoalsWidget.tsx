'use client'
import Link from 'next/link'
import { useGoals } from '@/hooks/useGoals'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { ProgressBar } from '@/components/ui/ProgressBar'

export function GoalsWidget() {
  const { goals, loading } = useGoals()
  const { formatINR } = usePrivateMoney()

  return (
    <div
      className="rounded-xl border border-border bg-card p-5"
      style={{ boxShadow: 'var(--shadow-card)' }}
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Goals</h2>
        <Link href="/goals" className="text-xs text-accent hover:underline">
          View all →
        </Link>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse space-y-2">
              <div className="h-3.5 w-1/3 rounded bg-border" />
              <div className="h-2 rounded-full bg-border" />
            </div>
          ))}
        </div>
      ) : goals.length === 0 ? (
        <p className="py-6 text-center text-sm text-tertiary">
          No goals set up yet.{' '}
          <Link href="/goals" className="text-accent hover:underline">
            Add one →
          </Link>
        </p>
      ) : (
        <div className="space-y-4">
          {goals.map((goal) => (
            <div key={goal.id}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3">
                <Link
                  href={`/goals/detail?id=${goal.id}`}
                  className="truncate text-sm font-medium text-accent hover:underline"
                >
                  {goal.name}
                </Link>
                <span className="shrink-0 font-mono text-xs text-secondary">
                  {goal.progress_pct.toFixed(0)}%
                  <span className="ml-1.5 text-tertiary">
                    {formatINR(goal.current_value_inr)} of {formatINR(goal.target_amount_inr)}
                  </span>
                </span>
              </div>
              <ProgressBar value={goal.progress_pct} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
