'use client'
import { useGoals } from '@/hooks/useGoals'
import { GoalCard } from '@/components/domain/GoalCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export default function GoalsPage() {
  const { goals, loading } = useGoals()
  const { formatINR } = usePrivateMoney()

  const totalTarget = goals.reduce((s, g) => s + g.target_amount_inr, 0)
  const totalCurrent = goals.reduce((s, g) => s + g.current_value_inr, 0)
  const overallPct = totalTarget > 0 ? Math.min(100, (totalCurrent / totalTarget) * 100) : 0
  const totalRemaining = Math.max(0, totalTarget - totalCurrent)
  const barColor = overallPct >= 80 ? 'bg-green-500' : overallPct >= 50 ? 'bg-amber-400' : 'bg-indigo-500'

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-primary">Goals</h1>

      {loading ? (
        <Skeleton className="h-28 w-full" />
      ) : goals.length > 0 ? (
        <div className="rounded-xl border border-border bg-card p-5 shadow-card">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-secondary">Overall Progress</span>
            <span className="text-sm font-semibold text-primary">{overallPct.toFixed(1)}%</span>
          </div>
          <div className="h-3 w-full rounded-full bg-border overflow-hidden">
            <div
              className={`h-3 rounded-full ${barColor} transition-all duration-700`}
              style={{ width: `${overallPct}%` }}
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-secondary">
            <span>{formatINR(totalCurrent)} accumulated</span>
            <span className="text-tertiary">{goals.length} goal{goals.length !== 1 ? 's' : ''} · {formatINR(totalRemaining)} remaining</span>
            <span>{formatINR(totalTarget)} target</span>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : goals.length === 0 ? (
        <p className="text-sm text-tertiary">No goals created yet</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">{goals.map(g => <GoalCard key={g.id} goal={g} />)}</div>
      )}
    </div>
  )
}
