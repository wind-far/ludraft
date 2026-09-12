import clsx from 'clsx'

interface ProgressBarProps {
  value: number // 0-100
  color?: 'blue' | 'green' | 'red' | 'purple' | 'cyan' | 'orange'
  size?: 'sm' | 'md' | 'lg'
  animated?: boolean
  showLabel?: boolean
  label?: string
  className?: string
}

const colorClasses = {
  blue:   'bg-blue-500',
  green:  'bg-emerald-500',
  red:    'bg-red-500',
  purple: 'bg-purple-500',
  cyan:   'bg-cyan-500',
  orange: 'bg-brand',
}

const sizeClasses = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
}

export default function ProgressBar({
  value,
  color = 'blue',
  size = 'md',
  animated = true,
  showLabel,
  label,
  className,
}: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className={clsx('w-full', className)}>
      {(showLabel || label) && (
        <div className="mb-1.5 flex items-center justify-between text-xs">
          {label && <span className="text-gray-400">{label}</span>}
          {showLabel && <span className="font-medium text-gray-600">{pct}%</span>}
        </div>
      )}
      <div className={clsx('overflow-hidden rounded-full bg-gray-100', sizeClasses[size])}>
        <div
          className={clsx(
            'rounded-full',
            colorClasses[color],
            animated && 'transition-all duration-700 ease-out'
          )}
          style={{ width: `${pct}%`, height: '100%' }}
        />
      </div>
    </div>
  )
}
