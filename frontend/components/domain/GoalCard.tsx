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
    <div className="rounded-xl border bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <Link href={`/goals/${goal.id}`} className="font-medium text-indigo-600 hover:underline">
          {goal.name}
        </Link>
        <span className="text-xs text-gray-400">By {formatDate(goal.target_date)}</span>
      </div>

      <div className="mt-3 space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Target</span>
          <span className="font-semibold">{formatINR(goal.target_amount_inr)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Current</span>
          <span>{formatINR(goal.current_value_inr)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Remaining</span>
          <span className={goal.remaining_inr > 0 ? 'text-red-500' : 'text-green-600'}>
            {goal.remaining_inr > 0 ? formatINR(goal.remaining_inr) : 'Goal met!'}
          </span>
        </div>
      </div>

      <div className="mt-4">
        <ProgressBar value={pct} />
        <p className="mt-1 text-xs text-gray-400">{pct.toFixed(1)}% of target · {goal.allocations.length} investment{goal.allocations.length !== 1 ? 's' : ''}</p>
      </div>
    </div>
  )
}
