interface ProgressBarProps {
  value: number  // 0-100
}
export function ProgressBar({ value }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const color = clamped >= 80 ? 'bg-green-500' : clamped >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="h-2 w-full rounded-full bg-border">
      <div className={`h-2 rounded-full ${color} transition-all`} style={{ width: `${clamped}%` }} />
    </div>
  )
}
