'use client'

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { api } from '@/lib/api'
import { Member } from '@/constants'

interface MemberContextType {
  members: Member[]
  selectedMemberIds: number[]
  setSelectedMemberIds: (ids: number[]) => void
  loading: boolean
}

const MemberContext = createContext<MemberContextType>({
  members: [],
  selectedMemberIds: [],
  setSelectedMemberIds: () => {},
  loading: true,
})

const STORAGE_KEY = 'selectedMemberIds'

export function MemberProvider({ children }: { children: ReactNode }) {
  const [members, setMembers] = useState<Member[]>([])
  const [selectedMemberIds, setSelectedMemberIdsState] = useState<number[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.members
      .list()
      .then((data) => {
        setMembers(data)
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          try {
            const ids = JSON.parse(stored) as number[]
            const valid = ids.filter((id) => data.some((m) => m.id === id))
            setSelectedMemberIdsState(valid.length > 0 ? valid : data.map((m) => m.id))
          } catch {
            setSelectedMemberIdsState(data.map((m) => m.id))
          }
        } else {
          setSelectedMemberIdsState(data.map((m) => m.id))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const setSelectedMemberIds = useCallback((ids: number[]) => {
    setSelectedMemberIdsState(ids)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  }, [])

  return (
    <MemberContext.Provider value={{ members, selectedMemberIds, setSelectedMemberIds, loading }}>
      {children}
    </MemberContext.Provider>
  )
}

export function useMembers() {
  return useContext(MemberContext)
}
