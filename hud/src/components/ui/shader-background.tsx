import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'

type ShaderBackgroundProps = {
  accent?: string
  secondary?: string
  tertiary?: string
  opacity?: number
}

const BASE_NOISE =
  'radial-gradient(circle at 20% 18%, rgba(255,255,255,0.08) 0, rgba(255,255,255,0) 34%),' +
  'radial-gradient(circle at 78% 24%, rgba(164,132,255,0.08) 0, rgba(164,132,255,0) 22%),' +
  'radial-gradient(circle at 55% 55%, rgba(83,164,255,0.06) 0, rgba(83,164,255,0) 28%),' +
  'radial-gradient(circle at 80% 72%, rgba(255,255,255,0.04) 0, rgba(255,255,255,0) 20%)'

export function ShaderBackground({
  accent = 'rgba(104, 218, 255, 0.36)',
  secondary = 'rgba(161, 117, 255, 0.26)',
  tertiary = 'rgba(91, 255, 208, 0.18)',
  opacity = 1,
}: ShaderBackgroundProps) {
  const reduceMotion = useReducedMotion()

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        zIndex: -10,
        opacity,
        background: '#040913',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: BASE_NOISE,
          opacity: 0.9,
          mixBlendMode: 'screen',
        }}
      />

      <motion.div
        style={{
          position: 'absolute',
          inset: '-16%',
          background: `
            radial-gradient(circle at 50% 50%, ${accent} 0%, rgba(10,18,35,0.02) 24%, rgba(4,9,19,0) 64%),
            conic-gradient(from 0deg at 50% 50%, rgba(104,218,255,0.06), rgba(161,117,255,0.18), rgba(91,255,208,0.08), rgba(104,218,255,0.06))
          `,
          filter: 'blur(44px)',
          transformOrigin: '50% 50%',
          mixBlendMode: 'screen',
        }}
        animate={reduceMotion ? undefined : { rotate: 360 }}
        transition={reduceMotion ? undefined : { repeat: Infinity, duration: 42, ease: 'linear' }}
      />

      <motion.div
        style={{
          position: 'absolute',
          left: '-18%',
          top: '16%',
          width: '54%',
          height: '54%',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${secondary} 0%, rgba(9,15,28,0.06) 42%, rgba(4,9,19,0) 76%)`,
          filter: 'blur(34px)',
          mixBlendMode: 'screen',
        }}
        animate={reduceMotion ? undefined : { x: [0, 80, -20, 0], y: [0, 24, -18, 0], scale: [1, 1.08, 0.96, 1] }}
        transition={reduceMotion ? undefined : { repeat: Infinity, duration: 18, ease: 'easeInOut' }}
      />

      <motion.div
        style={{
          position: 'absolute',
          right: '-12%',
          bottom: '-8%',
          width: '46%',
          height: '46%',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${tertiary} 0%, rgba(7,18,26,0.06) 34%, rgba(4,9,19,0) 74%)`,
          filter: 'blur(36px)',
          mixBlendMode: 'screen',
        }}
        animate={reduceMotion ? undefined : { x: [0, -42, 18, 0], y: [0, -22, 14, 0], scale: [1, 1.04, 0.98, 1] }}
        transition={reduceMotion ? undefined : { repeat: Infinity, duration: 20, ease: 'easeInOut' }}
      />

      <motion.div
        style={{
          position: 'absolute',
          inset: 0,
          background: `
            radial-gradient(circle at 50% 50%, rgba(255,255,255,0.06) 0 1px, transparent 1px),
            radial-gradient(circle at 20% 80%, rgba(255,255,255,0.08) 0 1px, transparent 1px),
            radial-gradient(circle at 82% 16%, rgba(255,255,255,0.07) 0 1px, transparent 1px)
          `,
          backgroundSize: '180px 180px, 240px 240px, 200px 200px',
          opacity: 0.34,
        }}
        animate={reduceMotion ? undefined : { x: [0, 12, -10, 0], y: [0, -8, 14, 0] }}
        transition={reduceMotion ? undefined : { repeat: Infinity, duration: 26, ease: 'easeInOut' }}
      />

      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(circle at center, rgba(255,255,255,0) 0%, rgba(5,10,18,0.22) 58%, rgba(3,6,12,0.74) 100%)',
        }}
      />
    </div>
  )
}

export default ShaderBackground
