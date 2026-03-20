'use client'
import { useGoals } from '@/hooks/useGoals'
import { GoalCard } from '@/components/domain/GoalCard'
import { Skeleton } from '@/components/ui/Skeleton'

export default function GoalsPage() {
  const { goals, loading } = useGoals()
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-800">Goals</h1>
      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : goals.length === 0 ? (
        <p className="text-sm text-gray-400">No goals created yet</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">{goals.map(g => <GoalCard key={g.id} goal={g} />)}</div>
      )}
    </div>
  )
}
