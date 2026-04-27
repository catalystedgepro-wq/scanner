import React from 'react'
import { motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import { LiquidGlassCard } from '@/components/ui/liquid-glass-card'

type BentoGridProps = {
  children: React.ReactNode
  style?: React.CSSProperties
}

type BentoCardProps = {
  eyebrow?: string
  title: string
  value?: React.ReactNode
  note?: React.ReactNode
  accent?: string
  icon?: LucideIcon
  span?: number
  rowSpan?: number
  children?: React.ReactNode
  align?: 'left' | 'right'
}

const mono = "'IBM Plex Mono', monospace"
const display = "'Space Grotesk', 'Inter', sans-serif"

export function BentoGrid({ children, style }: BentoGridProps) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(12, minmax(0, 1fr))',
        gap: 12,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function BentoCard({
  eyebrow,
  title,
  value,
  note,
  accent = '#72e5ff',
  icon: Icon,
  span = 3,
  rowSpan = 1,
  children,
  align = 'left',
}: BentoCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
      style={{
        gridColumn: `span ${span} / span ${span}`,
        gridRow: `span ${rowSpan} / span ${rowSpan}`,
        minHeight: rowSpan > 1 ? 168 : 104,
        position: 'relative',
        textAlign: align,
      }}
    >
      <LiquidGlassCard
        style={{
          minHeight: rowSpan > 1 ? 168 : 104,
          height: '100%',
          borderRadius: 24,
          border: `1px solid ${accent}1f`,
          background: 'linear-gradient(180deg, rgba(10,18,31,0.10) 0%, rgba(5,10,20,0.035) 100%)',
          boxShadow: `0 12px 30px rgba(0,0,0,0.08), inset 0 0 0 1px rgba(255,255,255,0.02), inset 0 0 24px ${accent}08`,
          padding: 16,
          color: 'var(--hud-text)',
          textAlign: align,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(circle at 100% 0%, ${accent}24 0%, rgba(255,255,255,0) 36%)`,
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: 24,
            background:
              'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0) 24%, rgba(255,255,255,0) 72%, rgba(255,255,255,0.04) 100%)',
            pointerEvents: 'none',
          }}
        />
        <div style={{ position: 'relative', zIndex: 1, display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ display: 'grid', gap: 6 }}>
              {eyebrow ? (
                <div
                  style={{
                    fontFamily: mono,
                    fontSize: 9,
                    letterSpacing: '0.24em',
                    textTransform: 'uppercase',
                    color: 'rgba(176, 194, 214, 0.68)',
                  }}
                >
                  {eyebrow}
                </div>
              ) : null}
              <div
                style={{
                  fontFamily: display,
                  fontSize: 15,
                  fontWeight: 700,
                  letterSpacing: '-0.03em',
                }}
              >
                {title}
              </div>
            </div>
            {Icon ? (
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 14,
                  display: 'grid',
                  placeItems: 'center',
                  border: `1px solid ${accent}26`,
                  background: `linear-gradient(180deg, ${accent}1d 0%, rgba(4,10,20,0.22) 100%)`,
                  color: accent,
                  boxShadow: `0 0 18px ${accent}1f`,
                }}
              >
                <Icon size={18} strokeWidth={1.8} />
              </div>
            ) : null}
          </div>

          {value ? (
            <div
              style={{
                fontFamily: display,
                fontSize: 26,
                fontWeight: 700,
                letterSpacing: '-0.06em',
                color: '#f3f7ff',
              }}
            >
              {value}
            </div>
          ) : null}

          {children}

          {note ? (
            <div
              style={{
                fontSize: 11,
                lineHeight: 1.55,
                color: 'rgba(188, 202, 218, 0.78)',
              }}
            >
              {note}
            </div>
          ) : null}
        </div>
      </LiquidGlassCard>
    </motion.div>
  )
}

export default BentoGrid
