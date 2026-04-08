'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { AssetTypeBreakdownEntry } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useBreakdown() {
  const { selectedMemberIds } = useMembers()
  const [breakdown, setBreakdown] = useState<AssetTypeBreakdownEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.returns.breakdown(selectedMemberIds)
      .then((r) => setBreakdown(r.breakdown))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberKey])

  return { breakdown, loading, error }
}
