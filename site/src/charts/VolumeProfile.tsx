import { useMemo } from 'react'

import { formatLots, formatPrice } from '../lib/format'
import type { Candle } from '../lib/series'
import { useView } from '../lib/store'

const BINS = 24

/**
 * 價量分布：K 線可視區間內，每個價位區間累積的成交量。
 * 每根 K 線的量平均分攤到它的最高價與最低價之間涵蓋的區間。
 */
export function VolumeProfile({ candles, etf, adjusted }: { candles: Candle[]; etf: boolean; adjusted: boolean }) {
  const visible = useView((s) => s.visible)
  const hover = useView((s) => s.hoverDate)

  const prof = useMemo(() => {
    const rows = visible ? candles.filter((c) => c.time >= visible.from && c.time <= visible.to) : candles
    if (rows.length === 0) return null
    let lo = Infinity
    let hi = -Infinity
    for (const c of rows) {
      lo = Math.min(lo, c.low)
      hi = Math.max(hi, c.high)
    }
    if (!(hi > lo)) hi = lo * 1.001 + 0.01
    const step = (hi - lo) / BINS
    const vol = new Array<number>(BINS).fill(0)
    for (const c of rows) {
      const a = Math.min(BINS - 1, Math.floor((c.low - lo) / step))
      const b = Math.min(BINS - 1, Math.floor((c.high - lo) / step))
      const share = c.volume / (b - a + 1)
      for (let k = a; k <= b; k++) vol[k] = vol[k]! + share
    }
    const max = Math.max(...vol)
    const poc = vol.indexOf(max)
    const last = rows[rows.length - 1]!
    const lastBin = Math.min(BINS - 1, Math.floor((last.close - lo) / step))
    return { lo, step, vol, max, poc, last, lastBin, n: rows.length, from: rows[0]!.time, to: last.time }
  }, [candles, visible])

  const hoverBin = useMemo(() => {
    if (!prof || !hover) return null
    const c = candles.find((x) => x.time === hover)
    if (!c) return null
    return Math.min(BINS - 1, Math.max(0, Math.floor((c.close - prof.lo) / prof.step)))
  }, [hover, candles, prof])

  if (!prof) return null
  const p = (v: number) => formatPrice(v, { etf, adjusted })
  const bins = prof.vol.map((v, k) => ({ k, v })).reverse()

  return (
    <div className="flex h-full flex-col px-3 pb-2 pt-1.5">
      <div className="mb-1 flex justify-between text-2xs text-text-3">
        <span className="num">
          {prof.from} – {prof.to}
        </span>
        <span>{prof.n} 日</span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col justify-between">
        {bins.map(({ k, v }) => {
          const isPoc = k === prof.poc
          const isLast = k === prof.lastBin
          const isHover = k === hoverBin
          return (
            <div key={k} className="group relative flex min-h-0 flex-1 items-center gap-2" title={`${p(prof.lo + k * prof.step)} – ${p(prof.lo + (k + 1) * prof.step)}：${formatLots(Math.round(v))} 張`}>
              <span className={`num w-12 shrink-0 text-right text-2xs ${isLast ? 'text-text-1' : 'text-text-3'}`}>
                {p(prof.lo + (k + 0.5) * prof.step)}
              </span>
              <div className="relative h-[70%] min-h-px flex-1">
                <div
                  className={`absolute inset-y-0 left-0 rounded-[1px] transition-[width] duration-300 ${
                    isPoc ? 'bg-text-2' : isHover ? 'bg-text-3' : 'bg-line-strong'
                  }`}
                  style={{ width: `${(v / prof.max) * 100}%` }}
                />
              </div>
              {isLast && <span className="absolute -left-1 h-full w-0.5 rounded bg-text-1" aria-hidden="true" />}
            </div>
          )
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-2xs text-text-3">
        <span>
          成交最密集 <span className="num text-text-2">{p(prof.lo + (prof.poc + 0.5) * prof.step)}</span>
        </span>
        <span>
          最新 <span className="num text-text-1">{p(prof.last.close)}</span>
        </span>
      </div>
    </div>
  )
}
