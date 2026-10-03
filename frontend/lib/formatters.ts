export const formatINR = (amount: number): string =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)

export const formatINR2 = (amount: number): string =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)

/** Compact INR for chart axes/tooltips: ₹1.50Cr / ₹12.50L / ₹8.5K / ₹950 */
export const formatINRCompact = (n: number): string => {
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)}Cr`
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)}L`
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(1)}K`
  return `₹${n.toFixed(0)}`
}

export const formatPct = (value: number, signed = true): string =>
  `${signed && value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`

export const formatXIRR = (value: number | null): string =>
  value === null ? '—' : formatPct(value)

/**
 * absolute_return_pct from /overview/gainers is already in percent points
 * (e.g. 15.2 means +15.2%), NOT a decimal. Do not multiply by 100.
 * Null (no computable return) renders as '—', never '+undefined%'.
 */
export const formatAbsolutePct = (value: number | null | undefined, signed = true): string => {
  if (value === null || value === undefined) return '—'
  return `${signed && value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export const formatDate = (iso: string): string => {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(iso + 'T00:00:00') : new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    timeZone: 'Asia/Kolkata',
  })
}

export const formatGain = (gain: number | null): string =>
  gain === null ? '—' : formatPct(gain)

/** Strip mfapi.in scheme_category prefix and return the sub-type label.
 *  "Equity Scheme - Large Cap Fund" → "Large Cap Fund"
 *  "Debt Scheme - Liquid Fund"      → "Liquid Fund"
 *  null / undefined                 → "—"
 */
export function formatMFCategory(raw: string | null | undefined): string {
  if (!raw) return '—'
  const match = raw.match(/^[^-]+-\s*(.+)$/)
  return match ? match[1].trim() : raw
}
