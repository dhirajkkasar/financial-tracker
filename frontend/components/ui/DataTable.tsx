import React from 'react'

interface Column<T> {
  key: string
  header: string
  render: (row: T) => React.ReactNode
  numeric?: boolean  // applies font-mono tabular alignment to cell
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  emptyMessage?: string
}

export function DataTable<T extends { id: number }>({ columns, rows, emptyMessage = 'No data' }: DataTableProps<T>) {
  if (rows.length === 0) {
    return <p className="py-10 text-center text-sm text-tertiary">{emptyMessage}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {columns.map((c) => (
              <th
                key={c.key}
                className={`pb-2.5 pr-4 text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary ${c.numeric ? 'text-right' : 'text-left'}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border last:border-0 transition-colors hover:bg-accent-subtle/30">
              {columns.map((c) => (
                <td key={c.key} className={`py-3 pr-4 ${c.numeric ? 'text-right font-mono' : ''}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
