'use client'
import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Goal } from '@/types'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatDate } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { ASSET_TYPE_LABELS } from '@/constants'

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const thClass = 'pb-2.5 pr-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'

function GoalDetailContent() {
  const { formatINR } = usePrivateMoney()
  const searchParams = useSearchParams()
  const goalId = parseInt(searchParams.get('id') ?? '0')
  const [goal, setGoal] = useState<Goal | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!goalId) return
    api.goals.get(goalId)
      .then(setGoal)
      .finally(() => setLoading(false))
  }, [goalId])

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    )
  }

  if (!goal) return <p className="text-loss">Goal not found</p>

  const pct = goal.progress_pct

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link href="/goals" className="text-xs text-tertiary hover:text-secondary">← Goals</Link>
        <h1 className="mt-1 text-2xl text-primary">{goal.name}</h1>
        <p className="mt-0.5 text-sm text-secondary">Target by {formatDate(goal.target_date)}</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className={card} style={cardStyle}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Target</p>
          <p className="mt-1 text-xl font-semibold text-primary">{formatINR(goal.target_amount_inr)}</p>
        </div>
        <div className={card} style={cardStyle}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Current</p>
          <p className="mt-1 text-xl font-semibold text-primary">{formatINR(goal.current_value_inr)}</p>
        </div>
        <div className={`${card} col-span-2 sm:col-span-1`} style={cardStyle}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Remaining</p>
          <p className={`mt-1 text-xl font-semibold ${goal.remaining_inr > 0 ? 'text-loss' : 'text-gain'}`}>
            {goal.remaining_inr > 0 ? formatINR(goal.remaining_inr) : 'Goal met!'}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className={card} style={cardStyle}>
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Progress</p>
          <p className="text-sm font-semibold text-primary">{pct.toFixed(1)}%</p>
        </div>
        <ProgressBar value={pct} />
      </div>

      {/* Allocations table */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-5 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          Linked Investments ({goal.allocations.length})
        </h2>

        {goal.allocations.length === 0 ? (
          <p className="py-10 text-center text-sm text-tertiary">No investments linked to this goal yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className={thClass}>Investment</th>
                  <th className={thClass}>Type</th>
                  <th className={`${thClass} text-right`}>Allocation</th>
                  <th className={`${thClass} text-right`}>Current Value</th>
                  <th className={`${thClass} text-right pr-0`}>Toward Goal</th>
                </tr>
              </thead>
              <tbody>
                {goal.allocations.map((alloc) => (
                  <tr key={alloc.id} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                    <td className="py-2.5 pr-3">
                      <Link
                        href={`/assets/detail?id=${alloc.asset_id}`}
                        className="text-sm text-primary hover:text-indigo-600 hover:underline"
                      >
                        {alloc.asset_name}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-secondary">
                      {ASSET_TYPE_LABELS[alloc.asset_type] ?? alloc.asset_type}
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono text-sm text-secondary">
                      {alloc.allocation_pct}%
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono text-sm text-secondary">
                      {alloc.current_value_inr != null ? formatINR(alloc.current_value_inr) : '—'}
                    </td>
                    <td className="py-2.5 text-right font-mono text-sm text-primary">
                      {alloc.value_toward_goal != null ? formatINR(alloc.value_toward_goal) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border">
                  <td colSpan={4} className="py-2.5 pr-3 text-xs font-semibold uppercase tracking-wide text-tertiary">
                    Total toward goal
                  </td>
                  <td className="py-2.5 text-right font-mono text-sm font-semibold text-primary">
                    {formatINR(goal.current_value_inr)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {goal.notes && (
        <div className={`${card} border-l-4 border-l-gold`} style={cardStyle}>
          <p className="text-sm text-secondary">{goal.notes}</p>
        </div>
      )}
    </div>
  )
}

export default function GoalDetailPage() {
  return (
    <Suspense fallback={
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    }>
      <GoalDetailContent />
    </Suspense>
  )
}
