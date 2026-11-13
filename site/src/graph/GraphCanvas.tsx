import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'

import { alpha, readTheme } from '../charts/theme'
import type { GraphLink, GraphNode } from '../lib/contract/types'

type N = NodeObject<GraphNode & { x?: number; y?: number }>
type L = LinkObject<GraphNode, GraphLink>

type Props = {
  nodes: GraphNode[]
  links: GraphLink[]
  center: string
  /** 要強調的路徑（依序的節點 id）；其餘淡出 */
  path: string[] | null
  selected: string | null
  onSelect: (n: GraphNode) => void
}

const endId = (v: unknown) => (typeof v === 'object' && v ? (v as { id: string }).id : String(v))

/** 力導向的知識圖譜畫布。節點形狀區分類型，解釋路徑上的連線有流動粒子（PLAN.md 7.5 第 5 項）。 */
export function GraphCanvas({ nodes, links, center, path, selected, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const fg = useRef<ForceGraphMethods<N, L> | undefined>(undefined)
  const [size, setSize] = useState({ w: 600, h: 400 })
  const theme = useMemo(() => readTheme(), [])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e!.contentRect.width, h: e!.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // 圖資料：force-graph 會在物件上寫入座標，所以複製一份
  const data = useMemo(
    () => ({ nodes: nodes.map((n) => ({ ...n })) as N[], links: links.map((l) => ({ ...l })) as unknown as L[] }),
    [nodes, links],
  )
  const onPath = useMemo(() => new Set(path ?? []), [path])
  const pathLinks = useMemo(() => {
    const s = new Set<string>()
    if (path) for (let i = 0; i < path.length - 1; i++) s.add(`${path[i]}|${path[i + 1]}`).add(`${path[i + 1]}|${path[i]}`)
    return s
  }, [path])
  const isPathLink = (l: L) => pathLinks.has(`${endId(l.source)}|${endId(l.target)}`)
  const dim = (id: string) => path != null && !onPath.has(id)

  useEffect(() => {
    const f = fg.current
    if (!f) return
    f.d3Force('charge')?.strength?.(-90)
    const link = f.d3Force('link') as { distance?: (d: (l: L) => number) => void } | undefined
    link?.distance?.((l: L) => (l.rel === 'may_affect' || l.rel === 'involves' || l.rel === 'origin' ? 28 : 55))
  }, [data])

  useEffect(() => {
    const t = window.setTimeout(() => fg.current?.zoomToFit(600, 40), 900)
    return () => window.clearTimeout(t)
  }, [data])

  const color = (n: GraphNode): string => {
    switch (n.type) {
      case 'company':
        return n.id === center ? theme.accent : theme.text1
      case 'industry':
        return theme.s2
      case 'concept':
        return theme.s3
      case 'global_company':
        return theme.s1
      case 'indicator':
        return theme.warn
      case 'move':
        return Number(n.attrs.ret) >= 0 ? theme.up : theme.down
      case 'event':
        return n.attrs.level === 'market' ? theme.warn : n.attrs.level === 'media' ? theme.s3 : theme.text2
      default:
        return theme.text2
    }
  }

  const draw = (node: N, ctx: CanvasRenderingContext2D, scale: number) => {
    const n = node as GraphNode
    const x = node.x ?? 0
    const y = node.y ?? 0
    const c = color(n)
    const a = dim(n.id) ? 0.14 : 1
    const isCenter = n.id === center
    const r = isCenter ? 7 : n.type === 'event' || n.type === 'move' ? 2.6 : n.type === 'company' ? 4.5 : 5
    ctx.globalAlpha = a
    ctx.fillStyle = c
    ctx.strokeStyle = c
    ctx.lineWidth = 1.2 / scale
    ctx.beginPath()
    switch (n.type) {
      case 'industry': // 方塊
        ctx.rect(x - r, y - r, r * 2, r * 2)
        ctx.fill()
        break
      case 'concept': // 菱形
        ctx.moveTo(x, y - r * 1.3)
        ctx.lineTo(x + r * 1.3, y)
        ctx.lineTo(x, y + r * 1.3)
        ctx.lineTo(x - r * 1.3, y)
        ctx.closePath()
        ctx.fill()
        break
      case 'indicator': // 三角形
        ctx.moveTo(x, y - r * 1.3)
        ctx.lineTo(x + r * 1.2, y + r)
        ctx.lineTo(x - r * 1.2, y + r)
        ctx.closePath()
        ctx.fill()
        break
      case 'global_company':
      case 'organization':
      case 'country': // 空心
        ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.lineWidth = 1.6 / scale
        ctx.stroke()
        break
      default:
        ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.fill()
    }
    if (isCenter || n.id === selected) {
      ctx.beginPath()
      ctx.arc(x, y, r + 3, 0, Math.PI * 2)
      ctx.strokeStyle = theme.accent
      ctx.lineWidth = 1 / scale
      ctx.stroke()
    }
    // 標籤：非事件節點都畫；事件與波動只在放大或在路徑上時畫
    const showLabel = (n.type !== 'event' && n.type !== 'move') || scale > 2.2 || onPath.has(n.id)
    if (showLabel) {
      const fs = Math.max(9, 11 / Math.sqrt(scale)) / scale
      ctx.font = `${fs * scale > 10 ? 500 : 400} ${fs}px "IBM Plex Sans", "Noto Sans TC Variable", sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = isCenter ? theme.text1 : alpha(theme.text2, 1)
      ctx.fillText(n.name, x, y + r + 2 / scale)
    }
    ctx.globalAlpha = 1
  }

  return (
    <div ref={box} className="absolute inset-0">
      <ForceGraph2D<GraphNode, GraphLink>
        ref={fg as never}
        width={size.w}
        height={size.h}
        graphData={data}
        backgroundColor={theme.panel}
        nodeId="id"
        nodeLabel={(n) => `${(n as GraphNode).name}`}
        nodeCanvasObject={draw as never}
        nodePointerAreaPaint={(node, c, ctx) => {
          ctx.fillStyle = c
          ctx.beginPath()
          ctx.arc(node.x ?? 0, node.y ?? 0, 7, 0, Math.PI * 2)
          ctx.fill()
        }}
        linkColor={(l) => {
          const lk = l as unknown as GraphLink & L
          if (isPathLink(lk)) return theme.accent
          const base = lk.rel === 'may_affect' ? theme.s3 : lk.origin === 'data' ? theme.text3 : theme.lineStrong
          return alpha(base, path ? 0.12 : lk.origin === 'data' ? 0.6 : 0.9)
        }}
        linkWidth={(l) => (isPathLink(l as L) ? 1.8 : (l as unknown as GraphLink).rel === 'may_affect' ? 0.6 + (l as unknown as GraphLink).confidence : 0.8)}
        linkLineDash={(l) => {
          const lk = l as unknown as GraphLink
          return lk.origin === 'llm' ? [4, 3] : lk.origin === 'data' ? [1, 2] : null
        }}
        linkDirectionalArrowLength={(l) => (isPathLink(l as L) ? 3.5 : 0)}
        linkDirectionalArrowRelPos={0.9}
        linkDirectionalParticles={(l) => (isPathLink(l as L) ? 3 : 0)}
        linkDirectionalParticleWidth={2.2}
        linkDirectionalParticleSpeed={0.008}
        linkDirectionalParticleColor={() => theme.accent}
        cooldownTicks={120}
        onNodeClick={(n) => onSelect(n as GraphNode)}
        enableNodeDrag
      />
    </div>
  )
}
