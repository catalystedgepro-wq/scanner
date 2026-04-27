import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'

export type BeamRect = {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

export type PulseBeamSpec = {
  id: string
  from: BeamRect | null
  to: BeamRect | null
  color?: string
  width?: number
  label?: string
}

type PulseBeamsProps = {
  beams: PulseBeamSpec[]
}

function centerPoint(rect: BeamRect) {
  return {
    x: rect.left + rect.width * 0.5,
    y: rect.top + rect.height * 0.5,
  }
}

function beamPath(from: BeamRect, to: BeamRect) {
  const start = centerPoint(from)
  const end = centerPoint(to)
  const deltaX = end.x - start.x
  const bend = Math.max(120, Math.abs(deltaX) * 0.28)
  const cp1x = start.x + Math.max(72, bend * 0.42)
  const cp1y = start.y - bend * 0.18
  const cp2x = end.x - Math.max(72, bend * 0.5)
  const cp2y = end.y + bend * 0.14
  return {
    start,
    end,
    d: `M ${start.x} ${start.y} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${end.x} ${end.y}`,
  }
}

export function PulseBeams({ beams }: PulseBeamsProps) {
  const reduceMotion = useReducedMotion()
  const readyBeams = beams.filter(beam => beam.from && beam.to)

  if (readyBeams.length === 0) return null

  return (
    <svg
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        overflow: 'visible',
        pointerEvents: 'none',
        zIndex: 250,
        mixBlendMode: 'screen',
      }}
    >
      <defs>
        {readyBeams.map(beam => {
          const color = beam.color || '#72e5ff'
          return (
            <linearGradient key={beam.id} id={`beam-${beam.id}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={color} stopOpacity="0" />
              <stop offset="22%" stopColor={color} stopOpacity="0.38" />
              <stop offset="50%" stopColor="#ffffff" stopOpacity="0.92" />
              <stop offset="78%" stopColor={color} stopOpacity="0.38" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          )
        })}
      </defs>

      {readyBeams.map(beam => {
        const color = beam.color || '#72e5ff'
        const width = beam.width || 2.2
        const { start, end, d } = beamPath(beam.from as BeamRect, beam.to as BeamRect)
        return (
          <g key={beam.id}>
            <motion.path
              d={d}
              fill="none"
              stroke={color}
              strokeWidth={width * 4}
              strokeOpacity={0.08}
              strokeLinecap="round"
              animate={reduceMotion ? undefined : { opacity: [0.05, 0.14, 0.05] }}
              transition={reduceMotion ? undefined : { repeat: Infinity, duration: 2.8, ease: 'easeInOut' }}
            />
            <motion.path
              d={d}
              fill="none"
              stroke={`url(#beam-${beam.id})`}
              strokeWidth={width}
              strokeLinecap="round"
              strokeDasharray="10 18"
              animate={reduceMotion ? undefined : { strokeDashoffset: [0, -56], opacity: [0.42, 0.88, 0.42] }}
              transition={reduceMotion ? undefined : { repeat: Infinity, duration: 1.25, ease: 'linear' }}
            />
            <motion.circle
              cx={end.x}
              cy={end.y}
              r={5.5}
              fill={color}
              animate={reduceMotion ? undefined : { opacity: [0.16, 0.72, 0.16], scale: [0.88, 1.18, 0.88] }}
              transition={reduceMotion ? undefined : { repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
            />
            <motion.circle
              cx={start.x}
              cy={start.y}
              r={4}
              fill="#ffffff"
              animate={reduceMotion ? undefined : { opacity: [0.12, 0.48, 0.12] }}
              transition={reduceMotion ? undefined : { repeat: Infinity, duration: 1.1, ease: 'easeInOut' }}
            />
            {beam.label ? (
              <text
                x={(start.x + end.x) * 0.5}
                y={(start.y + end.y) * 0.5 - 10}
                fill="rgba(215, 233, 255, 0.78)"
                fontSize="10"
                letterSpacing="0.28em"
                textAnchor="middle"
                style={{ textTransform: 'uppercase', fontFamily: "'IBM Plex Mono', monospace" }}
              >
                {beam.label}
              </text>
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

export default PulseBeams
