import clsx from 'clsx'

type BadgeColor = 'blue' | 'green' | 'purple' | 'yellow' | 'orange' | 'cyan' | 'red' | 'pink' | 'indigo' | 'gray'
type BadgeSize = 'sm' | 'md' | 'lg'
type BadgeVariant = 'soft' | 'outline' | 'solid' | 'dot'

interface BadgeProps {
  color?: BadgeColor
  size?: BadgeSize
  variant?: BadgeVariant
  children: React.ReactNode
  className?: string
  icon?: React.ReactNode
}

const colorClasses: Record<BadgeColor, Record<BadgeVariant, string>> = {
  blue:   { soft: 'bg-blue-50 text-blue-600',     outline: 'border-blue-200 text-blue-600',     solid: 'bg-blue-600 text-white',     dot: 'text-blue-600' },
  green:  { soft: 'bg-emerald-50 text-emerald-600', outline: 'border-emerald-200 text-emerald-600', solid: 'bg-emerald-600 text-white',  dot: 'text-emerald-600' },
  purple: { soft: 'bg-purple-50 text-purple-600',   outline: 'border-purple-200 text-purple-600',   solid: 'bg-purple-600 text-white',   dot: 'text-purple-600' },
  yellow: { soft: 'bg-amber-50 text-amber-600',     outline: 'border-amber-200 text-amber-600',     solid: 'bg-amber-500 text-white',    dot: 'text-amber-500' },
  orange: { soft: 'bg-brand-50 text-brand',          outline: 'border-brand-100 text-brand',          solid: 'bg-brand text-white',        dot: 'text-brand' },
  cyan:   { soft: 'bg-cyan-50 text-cyan-600',       outline: 'border-cyan-200 text-cyan-600',       solid: 'bg-cyan-600 text-white',     dot: 'text-cyan-600' },
  red:    { soft: 'bg-red-50 text-red-600',          outline: 'border-red-200 text-red-600',          solid: 'bg-red-600 text-white',      dot: 'text-red-600' },
  pink:   { soft: 'bg-pink-50 text-pink-600',       outline: 'border-pink-200 text-pink-600',       solid: 'bg-pink-600 text-white',     dot: 'text-pink-600' },
  indigo: { soft: 'bg-indigo-50 text-indigo-600',   outline: 'border-indigo-200 text-indigo-600',   solid: 'bg-indigo-600 text-white',   dot: 'text-indigo-600' },
  gray:   { soft: 'bg-gray-100 text-gray-600',      outline: 'border-gray-200 text-gray-600',       solid: 'bg-gray-600 text-white',     dot: 'text-gray-500' },
}

const dotBg: Record<BadgeColor, string> = {
  blue: 'bg-blue-500', green: 'bg-emerald-500', purple: 'bg-purple-500', yellow: 'bg-amber-400',
  orange: 'bg-brand', cyan: 'bg-cyan-500', red: 'bg-red-500', pink: 'bg-pink-500',
  indigo: 'bg-indigo-500', gray: 'bg-gray-400',
}

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-[10px]',
  md: 'px-2.5 py-1 text-[11px]',
  lg: 'px-3 py-1.5 text-xs',
}

export default function Badge({
  color = 'blue',
  size = 'md',
  variant = 'soft',
  children,
  className,
  icon,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full font-medium',
        sizeClasses[size],
        variant === 'outline' && 'border',
        variant === 'dot' && 'gap-1.5',
        colorClasses[color]?.[variant] || colorClasses.blue.soft,
        className
      )}
    >
      {variant === 'dot' && (
        <span className={clsx('inline-block h-1.5 w-1.5 rounded-full', dotBg[color])} />
      )}
      {icon}
      {children}
    </span>
  )
}
