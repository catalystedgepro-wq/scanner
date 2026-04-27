import * as React from 'react'
import { cn } from '@/lib/utils'

type BackgroundGradientAnimationProps = {
  children?: React.ReactNode
  className?: string
  containerClassName?: string
  gradientBackgroundStart?: string
  gradientBackgroundEnd?: string
  firstColor?: string
  secondColor?: string
  thirdColor?: string
  fourthColor?: string
  fifthColor?: string
  pointerColor?: string
  size?: string
  blendingValue?: React.CSSProperties['mixBlendMode']
}

const orbStyle = (
  color: string,
  size: string,
  mixBlendMode: React.CSSProperties['mixBlendMode'],
): React.CSSProperties => ({
  background: `radial-gradient(circle, rgba(${color}, 0.52) 0%, rgba(${color}, 0.18) 32%, rgba(${color}, 0) 68%)`,
  width: size,
  height: size,
  mixBlendMode,
})

export function BackgroundGradientAnimation({
  children,
  className,
  containerClassName,
  gradientBackgroundStart = 'rgb(5, 5, 10)',
  gradientBackgroundEnd = 'rgb(10, 15, 25)',
  firstColor = '16, 185, 129',
  secondColor = '244, 63, 94',
  thirdColor = '14, 165, 233',
  fourthColor = '20, 20, 20',
  fifthColor = '139, 92, 246',
  pointerColor = '255, 255, 255',
  size = '100%',
  blendingValue = 'screen',
}: BackgroundGradientAnimationProps) {
  return (
    <div className={cn('relative isolate overflow-hidden', className)}>
      <div
        className={cn('pointer-events-none absolute inset-0 -z-50', containerClassName)}
        style={{
          background: `linear-gradient(180deg, ${gradientBackgroundStart} 0%, ${gradientBackgroundEnd} 100%)`,
        }}
      >
        <div
          className="absolute inset-0 opacity-80"
          style={{
            background:
              'radial-gradient(circle at 50% 20%, rgba(255,255,255,0.07), transparent 30%), radial-gradient(circle at 50% 80%, rgba(255,255,255,0.04), transparent 30%)',
          }}
        />
        <div
          className="absolute -left-[18%] -top-[24%] animate-first rounded-full blur-3xl"
          style={orbStyle(firstColor, size, blendingValue)}
        />
        <div
          className="absolute -right-[14%] top-[6%] animate-second rounded-full blur-3xl"
          style={orbStyle(secondColor, size, blendingValue)}
        />
        <div
          className="absolute left-[18%] bottom-[-22%] animate-third rounded-full blur-3xl"
          style={orbStyle(thirdColor, size, blendingValue)}
        />
        <div
          className="absolute right-[12%] bottom-[-18%] animate-fourth rounded-full blur-3xl"
          style={orbStyle(fourthColor, size, blendingValue)}
        />
        <div
          className="absolute left-[42%] top-[18%] animate-fifth rounded-full blur-3xl"
          style={orbStyle(fifthColor, size, blendingValue)}
        />
        <div
          className="absolute left-1/2 top-1/2 h-[28rem] w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl"
          style={{
            background: `radial-gradient(circle, rgba(${pointerColor}, 0.14) 0%, rgba(${pointerColor}, 0.08) 25%, rgba(${pointerColor}, 0) 68%)`,
            mixBlendMode: blendingValue,
          }}
        />
      </div>
      <div className="relative z-10">{children}</div>
    </div>
  )
}
