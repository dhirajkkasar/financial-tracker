interface StatCardProps {
  label: string
  value: string
  sub?: string
  highlight?: 'positive' | 'negative' | 'neutral'
}

const BORDER_COLOR = {
  positive: 'border-l-gain',
  negative: 'border-l-loss',
  neutral: 'border-l-border',
} as const

const VALUE_COLOR = {
  positive: 'text-gain',
  negative: 'text-loss',
  neutral: 'text-primary',
} as const

const SUB_COLOR = {
  positive: 'text-gain',
  negative: 'text-loss',
  neutral: 'text-tertiary',
} as const

const TREND_ICON = {
  positive: '↑',
  negative: '↓',
  neutral: null,
} as const

export function StatCard({ label, value, sub, highlight = 'neutral' }: StatCardProps) {
  const trend = TREND_ICON[highlight]

  return (
    <div
      className={`anim-card rounded-xl border border-border border-l-4 ${BORDER_COLOR[highlight]} bg-card p-5`}
      style={{ boxShadow: 'var(--shadow-card)' }}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
        {label}
      </p>
      <p className={`mt-2 font-mono text-2xl font-medium num-transition ${VALUE_COLOR[highlight]}`}>
        {trend && <span className="mr-1 text-lg">{trend}</span>}
        {value}
      </p>
      {sub && (
        <p className={`mt-1 font-mono text-xs num-transition ${SUB_COLOR[highlight]}`}>
          {sub}
        </p>
      )}
    </div>
  )
}
