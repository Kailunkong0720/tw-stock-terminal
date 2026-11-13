import { ColorType, CrosshairMode, LineSeries, createChart, type IChartApi } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import { readTheme } from './theme'

export type CompareLine = { name: string; color: 'accent' | 'text2' | 's2' | 's3'; points: { time: string; value: number }[] }

/** 幾條序列以第一個共同點 = 100 比較相對表現（金融股專區：金融保險類 vs 加權）。 */
export function CompareChart({ lines }: { lines: CompareLine[] }) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!box.current) return
    const t = readTheme()
    const colors = { accent: t.accent, text2: t.text2, s2: t.s2, s3: t.s3 }
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: t.panel }, textColor: t.text3, fontSize: 11 },
      grid: { vertLines: { color: t.line }, horzLines: { color: t.line } },
      rightPriceScale: { borderColor: t.line },
      timeScale: { borderColor: t.line },
      crosshair: { mode: CrosshairMode.Normal },
    })
    chart.current = c
    const start = lines.map((l) => l.points[0]?.time ?? '').sort().at(-1) ?? ''
    for (const l of lines) {
      const pts = l.points.filter((p) => p.time >= start)
      const base = pts[0]?.value
      if (!base) continue
      const s = c.addSeries(LineSeries, {
        color: colors[l.color],
        lineWidth: 2,
        title: l.name,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      s.setData(pts.map((p) => ({ time: p.time, value: (p.value / base) * 100 })))
    }
    c.timeScale().fitContent()
    return () => {
      c.remove()
      chart.current = null
    }
  }, [lines])

  return <div ref={box} className="h-full w-full" />
}
