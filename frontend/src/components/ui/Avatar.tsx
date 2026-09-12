import clsx from 'clsx'

interface AvatarProps {
  icon?: React.ReactNode
  name?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  color?: 'blue' | 'green' | 'purple' | 'orange' | 'cyan' | 'pink' | 'indigo'
  status?: 'online' | 'busy' | 'offline'
  className?: string
}

const sizeClasses = {
  sm: 'h-8 w-8 text-sm',
  md: 'h-10 w-10 text-lg',
  lg: 'h-14 w-14 text-2xl',
  xl: 'h-20 w-20 text-4xl',
}

const bgClasses = {
  blue:   'bg-blue-50 text-blue-600',
  green:  'bg-emerald-50 text-emerald-600',
  purple: 'bg-purple-50 text-purple-600',
  orange: 'bg-brand-50 text-brand',
  cyan:   'bg-cyan-50 text-cyan-600',
  pink:   'bg-pink-50 text-pink-600',
  indigo: 'bg-indigo-50 text-indigo-600',
}

const statusColors = {
  online:  'bg-emerald-500',
  busy:    'bg-amber-400',
  offline: 'bg-gray-300',
}

export default function Avatar({ icon, name, size = 'md', color = 'blue', status, className }: AvatarProps) {
  return (
    <div className={clsx('relative inline-flex items-center justify-center rounded-full', sizeClasses[size], bgClasses[color], className)}>
      {icon || (name ? name[0] : '?')}
      {status && (
        <span
          className={clsx(
            'absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-white',
            size === 'sm' ? 'h-2.5 w-2.5' : 'h-3 w-3',
            statusColors[status]
          )}
        />
      )}
    </div>
  )
}
