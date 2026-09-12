import clsx from 'clsx'

interface CardProps {
  className?: string
  children: React.ReactNode
  hover?: boolean
  padding?: boolean
  onClick?: () => void
}

export function Card({ className, children, hover = true, padding, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'rounded-2xl border border-gray-100 bg-white shadow-card transition-all',
        hover && 'hover:shadow-card-hover',
        padding && 'p-5',
        onClick && 'cursor-pointer',
        className
      )}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('flex items-center justify-between px-6 py-4', className)}>
      {children}
    </div>
  )
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('flex items-center gap-2.5 text-[15px] font-semibold text-gray-900', className)}>
      {children}
    </div>
  )
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('px-6 py-5', className)}>{children}</div>
}

export function CardDivider() {
  return <div className="mx-6 h-px bg-gray-100" />
}
