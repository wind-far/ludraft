import clsx from 'clsx'
import Button from './Button'

interface EmptyStateProps {
  icon: React.ReactNode
  title: string
  description?: string
  action?: {
    label: string
    onClick: () => void
    variant?: 'primary' | 'secondary'
  }
  compact?: boolean
  className?: string
}

export default function EmptyState({ icon, title, description, action, compact, className }: EmptyStateProps) {
  return (
    <div className={clsx(
      'flex flex-col items-center justify-center text-center',
      compact ? 'py-8' : 'py-16',
      className
    )}>
      <div className={clsx(
        'mb-4 flex items-center justify-center rounded-2xl bg-gray-50',
        compact ? 'h-14 w-14 text-2xl' : 'h-20 w-20 text-4xl'
      )}>
        {icon}
      </div>
      <h3 className={clsx(
        'font-semibold text-gray-900',
        compact ? 'text-[15px]' : 'text-lg'
      )}>
        {title}
      </h3>
      {description && (
        <p className={clsx(
          'mt-2 max-w-sm text-gray-400',
          compact ? 'text-xs' : 'text-sm'
        )}>
          {description}
        </p>
      )}
      {action && (
        <div className="mt-5">
          <Button
            variant={action.variant || 'primary'}
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        </div>
      )}
    </div>
  )
}
