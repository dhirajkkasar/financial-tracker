'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { AllocationResponse } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useAllocation() {
  const { selectedMemberIds } = useMembers()
  const [data, setData] = useState<AllocationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.returns.allocation(selectedMemberIds)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberKey])

  return { data, loading, error }
}
