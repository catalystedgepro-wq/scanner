'use client'

import React, { Suspense, forwardRef, useCallback, useRef } from 'react'
import * as THREE from 'three'

const ForceGraph3D = React.lazy(() =>
  import('react-force-graph-3d').then(mod => ({ default: mod.default as React.ComponentType<any> })),
)

type CognitiveTopologyProps = {
  graphData: any
  onNodeClick?: (node: any) => void
  onNodeHover?: (node: any) => void
  onNodeDrag?: (node: any) => void
  onNodeDragEnd?: (node: any) => void
  onBackgroundClick?: () => void
  nodeLabel?: any
  linkVisibility?: any
  linkColor?: (link: any) => string
  linkWidth?: number | ((link: any) => number)
  className?: string
  backgroundColor?: string
}

const SECTOR_NODE_COLORS: Record<string, string> = {
  tech: '#38bdf8', semis: '#818cf8', biotech: '#34d399',
  financials: '#fbbf24', energy: '#fb923c', materials: '#a3e635',
  industrials: '#60a5fa', consumer: '#f472b6', staples: '#2dd4bf',
  comms: '#c084fc', utilities: '#a78bfa', real_estate: '#f59e0b',
  unknown: '#94a3b8', other: '#94a3b8',
}

function resolveNodeColor(node: any) {
  // Primary hue = sector, posture shifts brightness
  const sector = String(node?.sector || 'unknown').toLowerCase()
  return SECTOR_NODE_COLORS[sector] || SECTOR_NODE_COLORS.unknown
}

function resolveLinkColor(link: any) {
  const sectorColors: Record<string, string> = {
    Technology: 'rgba(56, 189, 248, 0.4)',
    Healthcare: 'rgba(167, 139, 250, 0.4)',
    Energy: 'rgba(250, 204, 21, 0.4)',
    Financials: 'rgba(52, 211, 153, 0.4)',
    'Consumer Cyclical': 'rgba(244, 114, 182, 0.4)',
  }

  const aliases: Record<string, string> = {
    tech: 'Technology',
    technology: 'Technology',
    semis: 'Technology',
    biotech: 'Healthcare',
    healthcare: 'Healthcare',
    energy: 'Energy',
    financials: 'Financials',
    consumer: 'Consumer Cyclical',
    'consumer cyclical': 'Consumer Cyclical',
  }

  const rawSector = String(
    link?.sector
      || link?.sympathySector
      || (typeof link?.source === 'object' ? link?.source?.sector : '')
      || (typeof link?.target === 'object' ? link?.target?.sector : '')
      || '',
  ).trim()

  if (sectorColors[rawSector]) return sectorColors[rawSector]

  const normalized = aliases[rawSector.toLowerCase()] || ''
  return normalized ? sectorColors[normalized] : 'rgba(255, 255, 255, 0.05)'
}

export const CognitiveTopology = forwardRef<any, CognitiveTopologyProps>(function CognitiveTopology(
  {
    graphData,
    onNodeClick,
    onNodeHover,
    onNodeDrag,
    onNodeDragEnd,
    onBackgroundClick,
    nodeLabel = 'name',
    linkVisibility,
    linkColor: linkColorProp,
    linkWidth: linkWidthProp,
    className,
    backgroundColor = 'rgba(0,0,0,0)',
  },
  forwardedRef,
) {
  const internalRef = useRef<any>(null)

  const attachRef = useCallback((instance: any) => {
    internalRef.current = instance
    if (typeof forwardedRef === 'function') {
      forwardedRef(instance)
    } else if (forwardedRef && 'current' in forwardedRef) {
      ;(forwardedRef as React.MutableRefObject<any>).current = instance
    }
  }, [forwardedRef])

  const handleNodeClick = useCallback((node: any) => {
    onNodeClick?.(node)
    if (onNodeClick || !internalRef.current || !Number.isFinite(node?.x) || !Number.isFinite(node?.y) || !Number.isFinite(node?.z)) {
      return
    }
    const distance = 40
    const distRatio = 1 + distance / Math.max(1, Math.hypot(node.x || 0, node.y || 0, node.z || 0))
    internalRef.current.cameraPosition(
      { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
      node,
      1500,
    )
  }, [onNodeClick])

  const getNodeThreeObject = useCallback((node: any) => {
    const color = resolveNodeColor(node)
    const radius = Math.max(2, Number(node?.val || node?.gravity || 2))
    const material = new THREE.MeshLambertMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.8,
      transparent: true,
      opacity: 0.9,
    })
    return new THREE.Mesh(new THREE.SphereGeometry(radius, 16, 16), material)
  }, [])

  return (
    <div className={className || 'absolute inset-0 h-full w-full cursor-crosshair'}>
      <Suspense fallback={null}>
        <ForceGraph3D
          ref={attachRef}
          graphData={graphData}
          nodeLabel={nodeLabel}
          nodeThreeObject={getNodeThreeObject}
          d3AlphaDecay={0.018}
          d3VelocityDecay={0.16}
          linkColor={linkColorProp || resolveLinkColor}
          linkWidth={linkWidthProp ?? 0.5}
          linkOpacity={0.3}
          linkCurvature={link => (link?.kind === 'sympathy_bleed' ? 0.08 : 0.02)}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={1.2}
          linkDirectionalParticleSpeed={0.005}
          linkVisibility={linkVisibility}
          onNodeHover={onNodeHover}
          onNodeDrag={onNodeDrag}
          onNodeDragEnd={onNodeDragEnd}
          onNodeClick={handleNodeClick}
          onBackgroundClick={onBackgroundClick}
          backgroundColor={backgroundColor}
          showNavInfo={false}
          enableNodeDrag={true}
        />
      </Suspense>
    </div>
  )
})

export default CognitiveTopology
