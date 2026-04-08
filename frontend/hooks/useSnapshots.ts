'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { PortfolioSnapshot } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useSnapshots(from?: string, to?: string) {
  const { selectedMemberIds } = useMembers()
  const [data, setData] = useState<PortfolioSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.snapshots
      .list(from, to, selectedMemberIds)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to, memberKey])

  return { data, loading, error }
}
