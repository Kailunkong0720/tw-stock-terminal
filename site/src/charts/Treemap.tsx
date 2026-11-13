import { hierarchy, treemap, treemapSquarify } from 'd3-hierarchy'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { HeatItem } from '../lib/contract/types'
import { useUpDown } from '../lib/prefs'

type Leaf = HeatItem & { value: number }
type Props = {
  items: HeatItem[]
  /** 與 items 對齊的數值（漲跌 %、或外資買賣超億元） */
  values: (number | null)[]
  /** 色階的飽和點（|值| ≥ scale 時顏色最深） */
  scale: number
  format: (v: number | null) => string
  onPick: (symbol: string) => void
  focusIndustry: string | null
  onIndustry: (ind: string | null) => void
}

/** 漲跌 → 顏色：與 token 一致的紅漲綠跌（或使用者選的綠漲紅跌），用透明度表示強弱。 */
function fill(v: number | null, scale: number, upHex: string, downHex: string): string {
  if (v == null || Number.isNaN(v)) return 'var(--bg-raised)'
  const t = Math.min(1, Math.abs(v) / scale)
  const hex = v >= 0 ? upHex : downHex
  const n = parseInt(hex.replace('#', ''), 16)
  const mix = (c: number) => Math.round(26 + (c - 26) * (0.18 + 0.82 * t)) // 從面板底色往漲跌色混
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

/**
 * 市值熱力圖（PLAN.md 7.5 第 4 項）：面積是市值、依產業分組；點產業放大、點個股進入終端。
 * 版面只依市值計算，播放時間軸時只有顏色變化（CSS transition 讓顏色連續流動）。
 */
export function Treemap({ items, values, scale, format, onPick, focusIndustry, onIndustry }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 800, h: 480 })
  const [hover, setHover] = useState<number | null>(null)
  useUpDown()
  const cs = getComputedStyle(document.documentElement)
  const upHex = cs.getPropertyValue('--up').trim()
  const downHex = cs.getPropertyValue('--down').trim()

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e!.contentRect.width, h: e!.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const layout = useMemo(() => {
    const idx = new Map(items.map((it, i) => [it.symbol, i]))
    const groups = new Map<string, Leaf[]>()
    for (const it of items) {
      if (focusIndustry && it.industry !== focusIndustry) continue
      const arr = groups.get(it.industry) ?? []
      arr.push({ ...it, value: it.cap })
      groups.set(it.industry, arr)
    }
    type Node = { name: string; children?: Node[] } & Partial<Leaf>
    const root = hierarchy<Node>({ name: 'root', children: [...groups].map(([name, children]) => ({ name, children })) })
      .sum((d) => d.value ?? 0)
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
    treemap<Node>().tile(treemapSquarify).size([size.w, size.h]).paddingTop(focusIndustry ? 0 : 16).paddingInner(1).round(true)(root)
    return { root, idx }
  }, [items, size, focusIndustry])

  const groups = layout.root.children ?? []
  const hovered = hover != null ? items[hover] : null

  return (
    <div ref={box} className="relative h-full w-full select-none overflow-hidden">
      <svg width={size.w} height={size.h} className="block">
        {groups.map((g) => {
          const gx = g as unknown as { x0: number; y0: number; x1: number; y1: number }
          return (
            <g key={g.data.name}>
              {!focusIndustry && (
                <text
                  x={gx.x0 + 3}
                  y={gx.y0 + 11}
                  fontSize={10}
                  fill="var(--text-2)"
                  className="cursor-pointer"
                  onClick={() => onIndustry(g.data.name)}
                >
                  {gx.x1 - gx.x0 > 40 ? g.data.name : ''}
                </text>
              )}
              {(g.children ?? []).map((leaf) => {
                const l = leaf as unknown as { x0: number; y0: number; x1: number; y1: number; data: Leaf }
                const i = layout.idx.get(l.data.symbol)!
                const v = values[i] ?? null
                const w = l.x1 - l.x0
                const h = l.y1 - l.y0
                const big = w > 46 && h > 26
                return (
                  <g
                    key={l.data.symbol}
                    transform={`translate(${l.x0},${l.y0})`}
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => (focusIndustry || !groups.length ? onPick(l.data.symbol) : onPick(l.data.symbol))}
                    className="cursor-pointer"
                  >
                    <rect
                      width={Math.max(0, w)}
                      height={Math.max(0, h)}
                      style={{ fill: fill(v, scale, upHex, downHex), transition: 'fill 450ms ease' }}
                      stroke={hover === i ? 'var(--text-1)' : 'var(--bg-canvas)'}
                      strokeWidth={hover === i ? 1.5 : 0.5}
                    />
                    {big && (
                      <>
                        <text x={4} y={13} fontSize={Math.min(13, Math.max(9, w / 7))} fill="var(--text-1)" fontWeight={500}>
                          {l.data.name}
                        </text>
                        {h > 34 && (
                          <text x={4} y={26} fontSize={10} className="num" fill="var(--text-1)" opacity={0.85}>
                            {format(v)}
                          </text>
                        )}
                      </>
                    )}
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>
      {hovered && (
        <div className="pointer-events-none absolute right-2 top-2 rounded-control border border-line-strong bg-panel/95 px-2.5 py-1.5 text-xs">
          <div className="flex items-baseline gap-2">
            <span className="num text-text-2">{hovered.symbol}</span>
            <span className="text-text-1">{hovered.name}</span>
            <span className="text-2xs text-text-3">{hovered.industry}</span>
          </div>
          <div className="num text-text-1">{format(values[hover!] ?? null)}</div>
          <div className="text-2xs text-text-3">市值 {Math.round(hovered.cap).toLocaleString()} 億</div>
        </div>
      )}
    </div>
  )
}
