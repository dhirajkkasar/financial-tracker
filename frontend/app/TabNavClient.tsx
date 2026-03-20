'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NAV_TABS } from '@/constants'

type Tab = typeof NAV_TABS[number]

export function TabNavClient({ tabs }: { tabs: readonly Tab[] }) {
  const pathname = usePathname()
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
                ? 'bg-accent-subtle text-accent'
                : 'text-secondary hover:bg-border hover:text-primary'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
    </>
  )
}
