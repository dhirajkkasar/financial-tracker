'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NAV_TABS } from '@/constants'
import { usePrivateMode } from '@/context/PrivateModeContext'
import { useDarkMode } from '@/context/DarkModeContext'
import MemberSelector from '@/components/ui/MemberSelector'

type Tab = typeof NAV_TABS[number]

export function TabNavClient({ tabs }: { tabs: readonly Tab[] }) {
  const pathname = usePathname()
  const { isPrivate, toggle } = usePrivateMode()
  const { isDark, toggle: toggleDark } = useDarkMode()

  return (
    <>
      {tabs.map((tab) => {
        const active = tab.href === '/' ? pathname === '/' : pathname.startsWith(tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.08em] transition-colors ${
              active
                ? 'bg-accent/15 text-accent ring-1 ring-accent/30'
                : 'text-secondary hover:bg-border hover:text-primary'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
      <MemberSelector />
      <button
        onClick={toggleDark}
        title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        className="rounded-md px-2 py-1.5 text-secondary transition-colors hover:bg-border hover:text-primary"
      >
        {isDark ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/>
            <line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/>
            <line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        )}
      </button>
      <button
        onClick={toggle}
        title={isPrivate ? 'Exit private mode' : 'Enter private mode'}
        className={`ml-auto rounded-md px-2 py-1.5 transition-colors ${
          isPrivate
            ? 'bg-accent-subtle text-accent'
            : 'text-secondary hover:bg-border hover:text-primary'
        }`}
      >
        {isPrivate ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
            <line x1="1" y1="1" x2="23" y2="23"/>
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        )}
      </button>
    </>
  )
}
