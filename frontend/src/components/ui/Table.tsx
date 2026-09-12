import clsx from 'clsx'

interface Column<T> {
  key: string
  title: string
  render?: (row: T) => React.ReactNode
  className?: string
  width?: string
}

interface TableProps<T> {
  columns: Column<T>[]
  data: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  compact?: boolean
}

export default function Table<T>({ columns, data, rowKey, onRowClick, compact }: TableProps<T>) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-100">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-50/80">
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  'text-left text-[11px] font-medium uppercase tracking-wider text-gray-400',
                  compact ? 'px-4 py-2.5' : 'px-5 py-3',
                  col.className
                )}
                style={col.width ? { width: col.width } : undefined}
              >
                {col.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={clsx(
                'transition-colors duration-150',
                i < data.length - 1 && 'border-b border-gray-50',
                onRowClick && 'cursor-pointer',
                'hover:bg-gray-50/50'
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={clsx(
                    'text-[13px] text-gray-600',
                    compact ? 'px-4 py-2.5' : 'px-5 py-3.5'
                  )}
                >
                  {col.render ? col.render(row) : (row as Record<string, unknown>)[col.key] as React.ReactNode}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
