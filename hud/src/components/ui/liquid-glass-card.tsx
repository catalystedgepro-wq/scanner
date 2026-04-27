import * as React from 'react'
import { cn } from '@/lib/utils'

const LiquidGlassCard = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, style, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'relative overflow-hidden rounded-xl border border-white/5 bg-black/10 backdrop-blur-md shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] transition-all duration-300',
        className,
      )}
      style={style}
      {...props}
    >
      <div className="absolute inset-0 bg-gradient-to-tr from-white/5 via-transparent to-transparent opacity-50 pointer-events-none" />
      <div className="relative z-10">{children}</div>
    </div>
  ),
)

LiquidGlassCard.displayName = 'LiquidGlassCard'

export { LiquidGlassCard }
