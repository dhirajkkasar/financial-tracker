'use client'
import { Goal } from '@/types'
import { formatDate } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { ProgressBar } from '@/components/ui/ProgressBar'
import Link from 'next/link'

export function GoalCard({ goal }: { goal: Goal }) {
  const { formatINR } = usePrivateMoney()
  const pct = goal.progress_pct
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-start justify-between">
        <Link href={`/goals/detail?id=${goal.id}`} className="font-medium text-accent hover:underline">
          {goal.name}
        </Link>
        <span className="text-xs text-tertiary">By {formatDate(goal.target_date)}</span>
      </div>

      <div className="mt-3 space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-secondary">Target</span>
          <span className="font-semibold text-primary">{formatINR(goal.target_amount_inr)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-secondary">Current</span>
          <span className="text-primary">{formatINR(goal.current_value_inr)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-secondary">Remaining</span>
          <span className={goal.remaining_inr > 0 ? 'text-loss' : 'text-gain'}>
            {goal.remaining_inr > 0 ? formatINR(goal.remaining_inr) : 'Goal met!'}
          </span>
        </div>
      </div>

      <div className="mt-4">
        <ProgressBar value={pct} />
        <p className="mt-1 text-xs text-tertiary">{pct.toFixed(1)}% of target · {goal.allocations.length} investment{goal.allocations.length !== 1 ? 's' : ''}</p>
      </div>
    </div>
  )
}
