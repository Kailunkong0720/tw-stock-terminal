import type { ActionInfo, Bars, Flows } from './contract/types'

export type Candle = {
  /** 日曆索引 */
  i: number
  time: string
  open: number
  high: number
  low: number
  close: number
  /** 張 */
  volume: number
  /** 千元 */
  value: number
}

/**
 * 每一天的累積調整因子：所有 ex_date 在該日之後的公司行動因子乘積。
 * 與 pipeline/analytics/adjust.py 的 cumulative_factors 相同。
 */
export function cumulativeFactors(dates: string[], actions: ActionInfo[], sharesOnly = false): number[] {
  const acts = actions.filter((a) => !sharesOnly || a.affects_shares).sort((a, b) => a.ex_date.localeCompare(b.ex_date))
  const out = new Array<number>(dates.length).fill(1)
  // 從最後一天往前掃，跨過 ex_date 時把因子乘上去
  let k = acts.length - 1
  let f = 1
  for (let i = dates.length - 1; i >= 0; i--) {
    while (k >= 0 && acts[k]!.ex_date > dates[i]!) {
      f *= acts[k]!.factor
      k--
    }
    out[i] = f
  }
  return out
}

/** 日線 → K 線資料。adjusted 為 true 時用還原價與還原量。沒有成交的日子略過。 */
export function toCandles(bars: Bars, calendar: string[], adjusted: boolean): Candle[] {
  const n = bars.close.length
  const dates = calendar.slice(bars.start, bars.start + n)
  const pf = adjusted ? cumulativeFactors(dates, bars.actions) : null
  const sf = adjusted ? cumulativeFactors(dates, bars.actions, true) : null
  const out: Candle[] = []
  for (let j = 0; j < n; j++) {
    const c = bars.close[j]
    const o = bars.open[j]
    const h = bars.high[j]
    const l = bars.low[j]
    if (c == null || o == null || h == null || l == null) continue
    const k = pf ? pf[j]! : 1
    const s = sf ? sf[j]! : 1
    out.push({
      i: bars.start + j,
      time: dates[j]!,
      open: o * k,
      high: h * k,
      low: l * k,
      close: c * k,
      volume: Math.round(bars.volume[j]! / s),
      value: bars.value[j]!,
    })
  }
  return out
}

/** 簡單移動平均；資料不足時為 null。 */
export function sma(values: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]!
    if (i >= n) sum -= values[i - n]!
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

export type FlowPoint = { time: string; foreign: number; trust: number; dealer: number; foreignValue: number }

export function toFlowPoints(flows: Flows, calendar: string[]): FlowPoint[] {
  const out: FlowPoint[] = []
  for (let j = 0; j < flows.foreign_net.length; j++) {
    out.push({
      time: calendar[flows.start + j]!,
      foreign: flows.foreign_net[j]!,
      trust: flows.trust_net[j]!,
      dealer: flows.dealer_net[j]!,
      foreignValue: flows.foreign_value[j]!,
    })
  }
  return out
}

export type DailyMove = { time: string; ret: number; close: number; volume: number }

/** 還原後的單日報酬，依絕對值排序。 */
export function biggestMoves(candles: Candle[], limit = 12): DailyMove[] {
  const moves: DailyMove[] = []
  for (let j = 1; j < candles.length; j++) {
    const prev = candles[j - 1]!
    const cur = candles[j]!
    moves.push({ time: cur.time, ret: cur.close / prev.close - 1, close: cur.close, volume: cur.volume })
  }
  return moves.sort((a, b) => Math.abs(b.ret) - Math.abs(a.ret)).slice(0, limit)
}

export function sum(values: number[]): number {
  let s = 0
  for (const v of values) s += v
  return s
}
