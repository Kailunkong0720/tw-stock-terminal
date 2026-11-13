import {
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import { useUpDown } from '../lib/prefs'
import { alpha, readTheme } from './theme'

type Props = {
  /** [日期, 收盤] */
  line: { time: string; value: number }[]
  /** 副圖直方圖（例如外資買賣超億元），可省略 */
  bars?: { time: string; value: number }[]
  markers?: { time: string; up: boolean; text?: string }[]
  lineLabel?: string
  barLabel?: string
}

/** 指數走勢（加權指數）＋可選的副圖直方圖。市場總覽與資金流向頁用。 */
export function IndexChart({ line, bars, markers = [] }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const updown = useUpDown()

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
        panes: { separatorColor: t.line, separatorHoverColor: t.lineStrong },
      },
      localization: { locale: 'zh-TW', dateFormat: 'yyyy-MM-dd' },
      grid: { vertLines: { visible: false }, horzLines: { color: t.line } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: t.text3, style: LineStyle.Dashed, labelBackgroundColor: t.raised },
        horzLine: { color: t.text3, style: LineStyle.Dashed, labelBackgroundColor: t.raised },
      },
      rightPriceScale: { borderColor: t.line },
      timeScale: { borderColor: t.line, minBarSpacing: 0.3 },
    })
    chart.current = c
    const ls = c.addSeries(LineSeries, { color: t.text1, lineWidth: 1, priceLineVisible: false })
    ls.setData(line.map((p) => ({ time: p.time as Time, value: p.value })))
    if (markers.length) {
      const ms: SeriesMarker<Time>[] = markers
        .filter((m) => line.some((p) => p.time === m.time))
        .map((m) =>
          m.up
            ? { time: m.time as Time, position: 'belowBar', shape: 'arrowUp', color: t.up, size: 0.5 }
            : { time: m.time as Time, position: 'aboveBar', shape: 'arrowDown', color: t.down, size: 0.5 },
        )
      createSeriesMarkers(ls, ms)
    }
    if (bars && bars.length) {
      const hs = c.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 1)
      hs.setData(bars.map((b) => ({ time: b.time as Time, value: b.value, color: alpha(b.value >= 0 ? t.up : t.down, 0.65) })))
      c.panes()[0]?.setStretchFactor(2)
      c.panes()[1]?.setStretchFactor(1)
    }
    c.timeScale().fitContent()
    return () => {
      c.remove()
      chart.current = null
    }
  }, [line, bars, markers, updown])

  return <div ref={box} className="h-full w-full" />
}
