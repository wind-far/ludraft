import clsx from 'clsx'

type ColorVariant = 'blue' | 'green' | 'purple' | 'orange' | 'cyan' | 'yellow' | 'red'

interface MetricCardProps {
  icon: React.ReactNode
  value: string | number
  label: string
  color: ColorVariant
  change?: { value: string; positive: boolean }
  onClick?: () => void
}

const colorConfig: Record<ColorVariant, { iconBg: string; accent: string }> = {
  blue:   { iconBg: 'bg-blue-50 text-blue-600',      accent: 'text-blue-600' },
  green:  { iconBg: 'bg-emerald-50 text-emerald-600', accent: 'text-emerald-600' },
  purple: { iconBg: 'bg-purple-50 text-purple-600',   accent: 'text-purple-600' },
  orange: { iconBg: 'bg-brand-50 text-brand',          accent: 'text-brand' },
  cyan:   { iconBg: 'bg-cyan-50 text-cyan-600',       accent: 'text-cyan-600' },
  yellow: { iconBg: 'bg-amber-50 text-amber-600',     accent: 'text-amber-600' },
  red:    { iconBg: 'bg-red-50 text-red-600',          accent: 'text-red-600' },
}

export default function MetricCard({ icon, value, label, color, change, onClick }: MetricCardProps) {
  const c = colorConfig[color]
  return (
    <div
      onClick={onClick}
      className={clsx(
        'group rounded-2xl border border-gray-100 bg-white p-5 shadow-card transition-all hover:shadow-card-hover',
        onClick && 'cursor-pointer'
      )}
    >
      <div className={clsx('mb-3 flex h-10 w-10 items-center justify-center rounded-xl text-[20px]', c.iconBg)}>
        {icon}
      </div>
      <div className="text-[28px] font-bold tracking-tight text-gray-900">{value}</div>
      <div className="mt-0.5 flex items-center gap-2">
        <span className="text-[12px] text-gray-400">{label}</span>
        {change && (
          <span className={clsx(
            'text-[11px] font-medium',
            change.positive ? 'text-emerald-600' : 'text-red-600'
          )}>
            {change.positive ? '↑' : '↓'} {change.value}
          </span>
        )}
      </div>
    </div>
  )
}
