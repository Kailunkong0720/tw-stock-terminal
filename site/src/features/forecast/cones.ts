import type { ConeData } from '../../charts/forecastCone'
import type { BacktestPoint, Forecast } from '../../lib/contract/types'

export function coneFromForecast(f: Forecast): ConeData {
  return {
    baseTime: f.base_date,
    baseClose: f.base_close,
    times: f.future_dates,
    p05: f.steps.map((s) => s.p05),
    p25: f.steps.map((s) => s.p25),
    p50: f.steps.map((s) => s.p50),
    p75: f.steps.map((s) => s.p75),
    p95: f.steps.map((s) => s.p95),
    paths: f.paths,
  }
}

/**
 * 回測某個基準日的預測錐。回測的價格是「基準日當下」的還原尺度；
 * 畫在目前的還原 K 線上時要乘上 scale（基準日之後才發生的公司行動）。
 */
export function coneFromBacktest(p: BacktestPoint, calendar: string[], adjusted: boolean): ConeData | null {
  const i = calendar.indexOf(p.base_date)
  if (i < 0) return null
  const times = calendar.slice(i + 1, i + 1 + p.steps.length)
  if (times.length < p.steps.length) return null
  const k = adjusted ? p.scale : 1
  return {
    baseTime: p.base_date,
    baseClose: p.base_close * k,
    times,
    p05: p.steps.map((s) => s.p05 * k),
    p25: p.steps.map((s) => s.p25 * k),
    p50: p.steps.map((s) => s.p50 * k),
    p75: p.steps.map((s) => s.p75 * k),
    p95: p.steps.map((s) => s.p95 * k),
    paths: [],
  }
}
