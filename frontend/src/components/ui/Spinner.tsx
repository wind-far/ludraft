import clsx from 'clsx'

interface SpinnerProps {
  size?: number | 'sm' | 'md' | 'lg'
  color?: 'brand' | 'white' | 'current'
  className?: string
}

const sizeMap = { sm: 16, md: 24, lg: 40 }
const colorMap = {
  brand: 'border-gray-200 border-t-brand',
  white: 'border-white/30 border-t-white',
  current: 'border-current/20 border-t-current',
}

export default function Spinner({ size = 'md', color = 'brand', className }: SpinnerProps) {
  const px = typeof size === 'number' ? size : sizeMap[size]
  return (
    <div
      className={clsx(
        'animate-spin rounded-full border-2',
        colorMap[color],
        className
      )}
      style={{ width: px, height: px }}
    />
  )
}

export function PageLoader({ text }: { text?: string }) {
  return (
    <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
      <Spinner size="lg" />
      {text && <p className="text-sm text-gray-400 animate-pulse">{text}</p>}
    </div>
  )
}
