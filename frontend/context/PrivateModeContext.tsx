'use client'
import { createContext, useContext, useState, useEffect } from 'react'

interface PrivateModeContextValue {
  isPrivate: boolean
  toggle: () => void
}

const PrivateModeContext = createContext<PrivateModeContextValue>({
  isPrivate: false,
  toggle: () => {},
})

export function PrivateModeProvider({ children }: { children: React.ReactNode }) {
  const [isPrivate, setIsPrivate] = useState(false)

  useEffect(() => {
    setIsPrivate(localStorage.getItem('privateMode') === 'true')
  }, [])

  function toggle() {
    if (isPrivate) {
      const confirmed = window.confirm('Exit private mode? Your portfolio values will be visible.')
      if (!confirmed) return
      setIsPrivate(false)
      localStorage.setItem('privateMode', 'false')
    } else {
      setIsPrivate(true)
      localStorage.setItem('privateMode', 'true')
    }
  }

  return (
    <PrivateModeContext.Provider value={{ isPrivate, toggle }}>
      {children}
    </PrivateModeContext.Provider>
  )
}

export function usePrivateMode() {
  return useContext(PrivateModeContext)
}
