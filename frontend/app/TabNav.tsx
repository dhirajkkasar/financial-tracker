import { NAV_TABS } from '@/constants'
import { TabNavClient } from './TabNavClient'

export function TabNav() {
  return (
    <nav className="border-b border-border bg-card" style={{ boxShadow: '0 1px 0 0 var(--border)' }}>
      <div className="mx-auto max-w-7xl px-4">
        <div className="flex items-center gap-1 overflow-x-auto py-2.5">
          <span className="mr-5 font-serif text-base font-normal tracking-tight text-primary">
            Portfolio
          </span>
          <TabNavClient tabs={NAV_TABS} />
        </div>
      </div>
    </nav>
  )
}
