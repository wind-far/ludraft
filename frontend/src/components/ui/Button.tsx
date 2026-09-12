import clsx from 'clsx'
import { forwardRef } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'outline'
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: React.ReactNode
  fullWidth?: boolean
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:   'bg-brand text-white shadow-sm hover:bg-brand-dark active:bg-brand-dark',
  secondary: 'bg-gray-50 border border-gray-200 text-gray-700 hover:bg-gray-100 active:bg-gray-150',
  ghost:     'text-gray-500 hover:text-gray-900 hover:bg-gray-50 active:bg-gray-100',
  danger:    'bg-red-50 border border-red-100 text-red-600 hover:bg-red-100',
  success:   'bg-emerald-50 border border-emerald-100 text-emerald-600 hover:bg-emerald-100',
  outline:   'border border-gray-200 text-gray-600 hover:border-brand hover:text-brand hover:bg-brand-50',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm:   'px-3 py-1.5 text-xs gap-1.5 rounded-lg',
  md:   'px-4 py-2.5 text-sm gap-2 rounded-xl',
  lg:   'px-6 py-3 text-sm gap-2.5 rounded-xl font-medium',
  icon: 'p-2.5 rounded-xl',
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  fullWidth,
  className,
  children,
  disabled,
  ...props
}, ref) => {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center font-medium transition-all duration-200',
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && 'w-full',
        (disabled || loading) && 'opacity-50 cursor-not-allowed pointer-events-none',
        className
      )}
      {...props}
    >
      {loading ? (
        <>
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current/30 border-t-current" />
          {children && <span>{children}</span>}
        </>
      ) : (
        <>
          {icon && <span className="flex-shrink-0">{icon}</span>}
          {children}
        </>
      )}
    </button>
  )
})

Button.displayName = 'Button'
export default Button
