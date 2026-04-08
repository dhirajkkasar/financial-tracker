'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { GainersResponse } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useGainers(n = 5) {
  const { selectedMemberIds } = useMembers()
  const [data, setData] = useState<GainersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.returns.gainers(n, selectedMemberIds)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, memberKey])

  return { data, loading, error }
}
