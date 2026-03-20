'use client'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  totalPages: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  return (
    <div className="flex items-center justify-between pt-3 text-sm text-secondary">
      <span className="text-xs text-tertiary">
        {total} {total === 1 ? 'entry' : 'entries'}
      </span>
      <div className="flex items-center gap-3">
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="rounded border border-border bg-card px-2 py-1 text-xs text-primary"
        >
          {[10, 25, 50].map((s) => (
            <option key={s} value={s}>
              {s} / page
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1">
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="rounded px-2 py-1 text-xs disabled:opacity-40 hover:bg-accent-subtle"
          >
            ←
          </button>
          <span className="px-2 text-xs">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="rounded px-2 py-1 text-xs disabled:opacity-40 hover:bg-accent-subtle"
          >
            →
          </button>
        </div>
      </div>
    </div>
  )
}
