import type {
  AutoscaleInfo,
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts'

import { alpha } from './theme'

type Target = Parameters<IPrimitivePaneRenderer['draw']>[0]

export type ConeData = {
  /** 基準日與基準收盤（錐的起點） */
  baseTime: string
  baseClose: number
  /** 預測的各交易日，與 p05… 等陣列等長 */
  times: string[]
  p05: number[]
  p25: number[]
  p50: number[]
  p75: number[]
  p95: number[]
  /** 各條取樣路徑 */
  paths: number[][]
}

export type ConeColors = { band: string; median: string; path: string }

/**
 * K 線右側的預測錐：第 5–95 與第 25–75 百分位兩層帶狀區域，加上中位數虛線。
 * progress 從 0 到 1：前段逐條畫出取樣路徑，後段路徑淡出、帶狀區域淡入。
 */
export class ForecastCone implements ISeriesPrimitive<Time> {
  private chart: IChartApiBase<Time> | null = null
  private series: ISeriesApi<SeriesType, Time> | null = null
  private request: (() => void) | null = null
  private data: ConeData | null = null
  private progress = 1
  private colors: ConeColors

  constructor(colors: ConeColors) {
    this.colors = colors
  }

  attached(p: SeriesAttachedParameter<Time>) {
    this.chart = p.chart
    this.series = p.series
    this.request = p.requestUpdate
  }

  detached() {
    this.chart = null
    this.series = null
    this.request = null
  }

  setData(d: ConeData | null) {
    this.data = d
    this.request?.()
  }

  setProgress(p: number) {
    this.progress = Math.max(0, Math.min(1, p))
    this.request?.()
  }

  setColors(c: ConeColors) {
    this.colors = c
    this.request?.()
  }

  autoscaleInfo(): AutoscaleInfo | null {
    const d = this.data
    if (!d || d.p05.length === 0) return null
    return { priceRange: { minValue: Math.min(...d.p05, d.baseClose), maxValue: Math.max(...d.p95, d.baseClose) } }
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [{ zOrder: () => 'top', renderer: () => ({ draw: (t: Target) => this.draw(t) }) }]
  }

  private draw(target: Target) {
    const d = this.data
    const chart = this.chart
    const series = this.series
    if (!d || !chart || !series) return
    const ts = chart.timeScale()
    const x = (t: string) => ts.timeToCoordinate(t as Time)
    const y = (p: number) => series.priceToCoordinate(p)
    const x0 = x(d.baseTime)
    const y0 = y(d.baseClose)
    if (x0 == null || y0 == null) return
    const xs = d.times.map(x)
    if (xs.some((v) => v == null)) return

    const pathPhase = Math.min(1, this.progress / 0.55)
    const bandPhase = Math.max(0, (this.progress - 0.45) / 0.55)
    const c = this.colors

    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.save()
      // 取樣路徑：逐條畫出
      if (bandPhase < 1 && d.paths.length) {
        ctx.lineWidth = 1
        ctx.strokeStyle = alpha(c.path, 0.38 * (1 - bandPhase))
        const steps = Math.max(1, Math.round(pathPhase * d.times.length))
        for (const path of d.paths) {
          ctx.beginPath()
          ctx.moveTo(x0, y0)
          for (let k = 0; k < steps; k++) {
            const py = y(path[k]!)
            if (py != null) ctx.lineTo(xs[k]!, py)
          }
          ctx.stroke()
        }
      }

      if (bandPhase > 0) {
        const band = (lo: number[], hi: number[], a: number) => {
          ctx.beginPath()
          ctx.moveTo(x0, y0)
          hi.forEach((v, k) => ctx.lineTo(xs[k]!, y(v)!))
          for (let k = lo.length - 1; k >= 0; k--) ctx.lineTo(xs[k]!, y(lo[k]!)!)
          ctx.closePath()
          ctx.fillStyle = alpha(c.band, a * bandPhase)
          ctx.fill()
        }
        band(d.p05, d.p95, 0.13)
        band(d.p25, d.p75, 0.22)
        // 中位數
        ctx.setLineDash([4, 3])
        ctx.lineWidth = 1.25
        ctx.strokeStyle = alpha(c.median, 0.9 * bandPhase)
        ctx.beginPath()
        ctx.moveTo(x0, y0)
        d.p50.forEach((v, k) => ctx.lineTo(xs[k]!, y(v)!))
        ctx.stroke()
        ctx.setLineDash([])
      }
      // 起點
      ctx.fillStyle = c.median
      ctx.beginPath()
      ctx.arc(x0, y0, 2.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    })
  }
}
