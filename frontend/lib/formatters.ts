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

export const formatPct = (value: number, signed = true): string =>
  `${signed && value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`

export const formatXIRR = (value: number | null): string =>
  value === null ? '—' : formatPct(value)

export const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  })

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
