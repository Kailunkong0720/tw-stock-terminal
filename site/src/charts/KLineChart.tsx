import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { ActionInfo } from '../lib/contract/types'
import { formatLots, formatPct, formatPrice, formatYi, toneClass } from '../lib/format'
import { useUpDown } from '../lib/prefs'
import { type Candle, type FlowPoint, sma } from '../lib/series'
import { RANGES, type RangeKey, useView } from '../lib/store'
import { alpha, readTheme } from './theme'

export type SubPane = 'volume' | 'foreign' | 'foreignCum'

type Props = {
  candles: Candle[]
  actions: ActionInfo[]
  flows: FlowPoint[] | null
  subPane: SubPane
  range: RangeKey
  adjusted: boolean
  etf: boolean
}

const ACTION_LABEL: Record<string, string> = {
  dividend_cash: '息',
  dividend_stock: '權',
  dividend_both: '權息',
  capital_reduction: '減資',
  par_change: '面額',
  etf_split: '分割',
  etf_reverse_split: '反分割',
}
const MA = [5, 20, 60] as const

type Legend = { c: Candle; prev: Candle | null; ma: (number | null)[]; flow: FlowPoint | null; cum: number | null }

export function KLineChart({ candles, actions, flows, subPane, range, adjusted, etf }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const candle = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const maSeries = useRef<ISeriesApi<'Line'>[]>([])
  const sub = useRef<ISeriesApi<'Histogram'> | ISeriesApi<'Line'> | null>(null)
  const markers = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const updown = useUpDown()
  const focusDate = useView((s) => s.focusDate)
  const [legend, setLegend] = useState<Legend | null>(null)

  const ma = useMemo(() => MA.map((n) => sma(candles.map((c) => c.close), n)), [candles])
  const byTime = useMemo(() => new Map(candles.map((c, j) => [c.time, j])), [candles])
  const flowByTime = useMemo(() => new Map((flows ?? []).map((f) => [f.time, f])), [flows])
  const cumForeign = useMemo(() => {
    const m = new Map<string, number>()
    let s = 0
    for (const f of flows ?? []) {
      s += f.foreignValue / 100 // 百萬元 → 億元
      m.set(f.time, s)
    }
    return m
  }, [flows])

  const legendAt = (j: number): Legend | null => {
    const c = candles[j]
    if (!c) return null
    return {
      c,
      prev: candles[j - 1] ?? null,
      ma: ma.map((s) => s[j] ?? null),
      flow: flowByTime.get(c.time) ?? null,
      cum: cumForeign.get(c.time) ?? null,
    }
  }

  // 建立圖表（只做一次）
  useEffect(() => {
    if (!box.current) return
    const t = readTheme()
    const c = createChart(box.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: t.panel },
        textColor: t.text3,
        fontFamily: "'IBM Plex Mono', 'Noto Sans TC Variable', monospace",
        fontSize: 11,
        attributionLogo: false,
        panes: { separatorColor: t.line, separatorHoverColor: t.lineStrong, enableResize: true },
      },
      localization: { locale: 'zh-TW', dateFormat: 'yyyy-MM-dd' },
      grid: { vertLines: { visible: false }, horzLines: { color: alpha(t.line, 0.9) } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: t.text3, style: LineStyle.Dashed, width: 1, labelBackgroundColor: t.raised },
        horzLine: { color: t.text3, style: LineStyle.Dashed, width: 1, labelBackgroundColor: t.raised },
      },
      rightPriceScale: { borderColor: t.line, scaleMargins: { top: 0.08, bottom: 0.04 } },
      timeScale: { borderColor: t.line, rightOffset: 4, minBarSpacing: 0.4, barSpacing: 6 },
    })
    chart.current = c
    candle.current = c.addSeries(CandlestickSeries, {
      borderVisible: false,
      priceLineVisible: false,
      lastValueVisible: true,
    })
    maSeries.current = [t.s1, t.s2, t.s3].map((color) =>
      c.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      }),
    )
    markers.current = createSeriesMarkers(candle.current, [])

    const onRange = () => {
      const lr = c.timeScale().getVisibleLogicalRange()
      const data = candle.current?.data() ?? []
      if (!lr || data.length === 0) return
      const from = data[Math.max(0, Math.ceil(lr.from))]
      const to = data[Math.min(data.length - 1, Math.floor(lr.to))]
      if (from && to) useView.getState().setVisible({ from: String(from.time), to: String(to.time) })
    }
    c.timeScale().subscribeVisibleLogicalRangeChange(onRange)
    return () => {
      c.timeScale().unsubscribeVisibleLogicalRangeChange(onRange)
      c.remove()
      // 所有序列都屬於這個圖表，一起清掉（React StrictMode 會重建一次圖表）
      chart.current = null
      candle.current = null
      maSeries.current = []
      sub.current = null
      markers.current = null
    }
  }, [])

  // 價格格式（還原價與 ETF 用不同的小數位）
  useEffect(() => {
    chart.current?.applyOptions({ localization: { priceFormatter: (p: number) => formatPrice(p, { etf, adjusted }) } })
  }, [etf, adjusted])

  // 主圖資料與顏色
  useEffect(() => {
    const t = readTheme()
    const cs = candle.current
    if (!cs) return
    cs.applyOptions({ upColor: t.up, downColor: t.down, wickUpColor: t.up, wickDownColor: t.down })
    cs.setData(candles.map((c) => ({ time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close })))
    maSeries.current.forEach((s, k) =>
      s.setData(
        candles.flatMap((c, j) => (ma[k]![j] == null ? [] : [{ time: c.time as Time, value: ma[k]![j]! }])),
      ),
    )
    // 公司行動標記：分割、減資、面額變更用文字標在 K 線上方；除權息用小點標在下方
    const ms: SeriesMarker<Time>[] = []
    for (const a of actions) {
      const j = byTime.get(a.ex_date) ?? candles.findIndex((c) => c.time >= a.ex_date)
      const c = candles[j]
      if (!c) continue
      const big = !a.type.startsWith('dividend')
      ms.push(
        big
          ? { time: c.time as Time, position: 'aboveBar', shape: 'square', color: t.warn, text: ACTION_LABEL[a.type] ?? a.type, size: 0.6 }
          : { time: c.time as Time, position: 'belowBar', shape: 'circle', color: t.text3, size: 0.35 },
      )
    }
    markers.current?.setMarkers(ms.sort((a, b) => String(a.time).localeCompare(String(b.time))))
    setLegend(legendAt(candles.length - 1))
  }, [candles, actions, ma, byTime, updown])

  // 副圖
  useEffect(() => {
    const c = chart.current
    if (!c) return
    const t = readTheme()
    if (sub.current) {
      c.removeSeries(sub.current)
      sub.current = null
    }
    if (subPane === 'foreignCum') {
      const s = c.addSeries(
        LineSeries,
        { color: t.text1, lineWidth: 1, priceLineVisible: false, lastValueVisible: true, priceFormat: { type: 'price', precision: 0, minMove: 1 } },
        1,
      )
      s.setData(
        candles.flatMap((cd) => {
          const v = cumForeign.get(cd.time)
          return v == null ? [] : [{ time: cd.time as Time, value: v }]
        }),
      )
      sub.current = s
    } else {
      const s = c.addSeries(
        HistogramSeries,
        { priceLineVisible: false, lastValueVisible: false, priceFormat: { type: 'volume' } },
        1,
      )
      if (subPane === 'volume') {
        s.setData(
          candles.map((cd, j) => {
            const up = j === 0 ? cd.close >= cd.open : cd.close >= candles[j - 1]!.close
            return { time: cd.time as Time, value: cd.volume, color: alpha(up ? t.up : t.down, 0.45) }
          }),
        )
      } else {
        s.setData(
          candles.flatMap((cd) => {
            const f = flowByTime.get(cd.time)
            return f ? [{ time: cd.time as Time, value: f.foreign, color: alpha(f.foreign >= 0 ? t.up : t.down, 0.7) }] : []
          }),
        )
      }
      sub.current = s
    }
    const panes = c.panes()
    panes[0]?.setStretchFactor(3)
    panes[1]?.setStretchFactor(1)
  }, [subPane, candles, flowByTime, cumForeign, updown])

  // 時間區間
  useEffect(() => {
    const c = chart.current
    if (!c || candles.length === 0) return
    const days = RANGES.find((r) => r.key === range)?.days
    if (days == null) c.timeScale().fitContent()
    else c.timeScale().setVisibleLogicalRange({ from: Math.max(0, candles.length - days), to: candles.length + 3 })
  }, [range, candles.length])

  // 其他面板要求聚焦某一天（例如點擊大波動日）
  useEffect(() => {
    const c = chart.current
    if (!c || !focusDate) return
    const j = byTime.get(focusDate) ?? candles.findIndex((cd) => cd.time >= focusDate)
    if (j >= 0) {
      c.timeScale().setVisibleLogicalRange({ from: j - 45, to: j + 25 })
      c.setCrosshairPosition(candles[j]!.close, candles[j]!.time as Time, candle.current!)
      setLegend(legendAt(j))
    }
    useView.getState().focus(null)
  }, [focusDate, byTime])

  // 十字線 → 圖例與跨面板高亮
  useEffect(() => {
    const c = chart.current
    if (!c) return
    const handler = (p: { time?: Time }) => {
      if (p.time == null) {
        setLegend(legendAt(candles.length - 1))
        useView.getState().setHover(null)
        return
      }
      const j = byTime.get(String(p.time))
      if (j != null) {
        setLegend(legendAt(j))
        useView.getState().setHover(String(p.time))
      }
    }
    c.subscribeCrosshairMove(handler)
    return () => c.unsubscribeCrosshairMove(handler)
  }, [candles, byTime, ma, flowByTime, cumForeign])

  return (
    <div className="relative h-full min-h-72 w-full">
      <div ref={box} className="absolute inset-0" />
      {legend && <ChartLegend l={legend} etf={etf} adjusted={adjusted} subPane={subPane} />}
    </div>
  )
}

function ChartLegend({ l, etf, adjusted, subPane }: { l: Legend; etf: boolean; adjusted: boolean; subPane: SubPane }) {
  const { c, prev } = l
  const chg = prev ? c.close / prev.close - 1 : null
  const p = (v: number) => formatPrice(v, { etf, adjusted })
  const tone = toneClass(chg)
  return (
    <div className="pointer-events-none absolute left-2 top-1.5 z-10 flex max-w-[calc(100%-5rem)] flex-wrap items-baseline gap-x-3 gap-y-0.5 text-2xs">
      <span className="num text-text-1">{c.time}</span>
      <span className="text-text-3">
        開 <span className={`num ${tone}`}>{p(c.open)}</span>
      </span>
      <span className="text-text-3">
        高 <span className={`num ${tone}`}>{p(c.high)}</span>
      </span>
      <span className="text-text-3">
        低 <span className={`num ${tone}`}>{p(c.low)}</span>
      </span>
      <span className="text-text-3">
        收 <span className={`num ${tone}`}>{p(c.close)}</span>
      </span>
      <span className={`num ${tone}`}>{formatPct(chg)}</span>
      <span className="text-text-3">
        量 <span className="num text-text-2">{formatLots(c.volume)}</span>
      </span>
      {MA.map((n, k) => (
        <span key={n} className="text-text-3">
          MA{n}{' '}
          <span className="num" style={{ color: `var(--series-${k + 1})` }}>
            {l.ma[k] == null ? '—' : p(l.ma[k]!)}
          </span>
        </span>
      ))}
      {subPane !== 'volume' && (
        <span className="text-text-3">
          外資{' '}
          <span className={`num ${toneClass(l.flow?.foreign)}`}>{l.flow ? `${formatLots(l.flow.foreign, true)} 張` : '—'}</span>
          {subPane === 'foreignCum' && l.cum != null && (
            <span className="num text-text-2">（累計 {formatYi(l.cum)}）</span>
          )}
        </span>
      )}
    </div>
  )
}
