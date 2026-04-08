'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { AssetType, OverviewReturns } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useOverview(types?: AssetType[]) {
  const { selectedMemberIds } = useMembers()
  const [data, setData] = useState<OverviewReturns | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const typeKey = types?.join(',') ?? ''
  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.returns.overview(types, selectedMemberIds)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeKey, memberKey])

  return { data, loading, error }
}
