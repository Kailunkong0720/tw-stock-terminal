import { Link } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'

import { alpha, type ChartTheme } from '../../charts/theme'
import { Panel } from '../../design/Panel'
import { Provenance } from '../../design/Provenance'
import type { GlobeArc, GlobePoint, GlobeRing, GlobeTag, GlobeView } from '../../globe/GlobeCanvas'
import type { GlobeOvernight } from '../../lib/contract/types'
import { formatDate, formatPct } from '../../lib/format'

// 紐約 → 台北的大圓航線經過白令海峽附近，鏡頭往北傾才能讓弧線落在畫面中間
export const OVERNIGHT_HOME: GlobeView = { lat: 56, lng: -162, altitude: 2.15 }
const SHORT: Record<string, string> = {
  'GLOBAL:SOX': '費半',
  'GLOBAL:TSM_ADR': '台積電 ADR',
  'GLOBAL:NASDAQ': '那斯達克',
  'GLOBAL:SP500': '標普 500',
  'GLOBAL:US10Y': '美債 10 年',
}
const SOX_BIG = 0.03
const WINDOW = 250

export function fmtChange(v: number | null | undefined, unit: string): string {
  if (v == null || !Number.isFinite(v)) return '—'
  if (unit === 'bp') return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}bp`
  return formatPct(v, 1)
}

function std(v: (number | null)[]): number {
  const x = v.filter((a): a is number => a != null)
  if (x.length < 2) return 1
  const m = x.reduce((a, b) => a + b, 0) / x.length
  return Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / (x.length - 1)) || 1
}

/** y 對 x 的迴歸斜率與相關係數（截至 end，往前 n 個有效樣本）。 */
export function regress(x: (number | null)[], y: (number | null)[], end: number, n = WINDOW) {
  const xs: number[] = []
  const ys: number[] = []
  for (let i = end; i >= 0 && xs.length < n; i--) {
    const a = x[i]
    const b = y[i]
    if (a != null && b != null) {
      xs.push(a)
      ys.push(b)
    }
  }
  if (xs.length < 30) return null
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length
  const my = ys.reduce((a, b) => a + b, 0) / ys.length
  let sxy = 0
  let sxx = 0
  let syy = 0
  for (let k = 0; k < xs.length; k++) {
    sxy += (xs[k]! - mx) * (ys[k]! - my)
    sxx += (xs[k]! - mx) ** 2
    syy += (ys[k]! - my) ** 2
  }
  return { beta: sxy / sxx, rho: sxy / Math.sqrt(sxx * syy), n: xs.length }
}

const tone = (v: number | null | undefined) => (v == null ? 'muted' : v > 0 ? 'up' : v < 0 ? 'down' : 'muted')
const row = (label: string, v: number | null | undefined, unit: string) =>
  `<div style="display:flex;justify-content:space-between;gap:12px"><span>${label}</span><span class="num ${tone(v)}">${fmtChange(v, unit)}</span></div>`

/** 使用者選的股票：弧線（半導體類的美股序列）落在它的所在地，報酬與日曆對齊。 */
export type PickedStock = { symbol: string; name: string; lat: number; lng: number; place: string; ret: (number | null)[] }

export function useOvernight(
  data: GlobeOvernight | undefined,
  dates: string[] | undefined,
  t: ChartTheme,
  stock: PickedStock | null,
) {
  const range = useMemo(() => {
    if (!data) return null
    let lo = -1
    let hi = -1
    for (let i = 0; i < data.taiex.length; i++) {
      if (data.series.some((s) => s.values[i] != null)) {
        if (lo < 0) lo = i
        hi = i
      }
    }
    return lo < 0 ? null : { lo, hi }
  }, [data])
  const stockRet = stock?.ret ?? data?.tsmc
  const stds = useMemo(
    () =>
      data && stockRet
        ? { series: data.series.map((s) => std(s.values)), taiex: std(data.taiex), stock: std(stockRet) }
        : null,
    [data, stockRet],
  )
  const [pos, setPos] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [fast, setFast] = useState(false)
  const i = pos ?? range?.hi ?? 0

  useEffect(() => {
    if (!playing || !range) return
    const id = window.setInterval(() => setPos((p) => Math.min((p ?? range.hi) + 1, range.hi)), fast ? 90 : 380)
    return () => window.clearInterval(id)
  }, [playing, fast, range])
  useEffect(() => {
    if (playing && range && i >= range.hi) setPlaying(false)
  }, [playing, range, i])

  const togglePlay = () => {
    if (!range) return
    if (!playing && i >= range.hi) setPos(range.lo)
    setPlaying(!playing)
  }
  const step = (d: number) => {
    if (!range) return
    setPlaying(false)
    setPos(Math.max(range.lo, Math.min(range.hi, i + d)))
  }

  const sox = data?.series.find((s) => s.id === 'GLOBAL:SOX')
  const ticks = useMemo(() => {
    if (!sox) return []
    const out: { i: number; v: number }[] = []
    sox.values.forEach((v, k) => {
      if (v != null && Math.abs(v) >= SOX_BIG) out.push({ i: k, v })
    })
    return out
  }, [sox])
  const shocks = useMemo(() => {
    if (!data || !stds) return []
    const out: { i: number; z: number; lead: number }[] = []
    for (let k = 0; k < data.taiex.length; k++) {
      let z = 0
      let lead = -1
      data.series.forEach((s, j) => {
        const v = s.values[k]
        if (v != null && Math.abs(v) / stds.series[j]! > z) {
          z = Math.abs(v) / stds.series[j]!
          lead = j
        }
      })
      if (lead >= 0) out.push({ i: k, z, lead })
    }
    return out.sort((a, b) => b.z - a.z).slice(0, 12)
  }, [data, stds])

  const layers = useMemo(() => {
    const empty = { arcs: [] as GlobeArc[], points: [] as GlobePoint[], rings: [] as GlobeRing[], tags: [] as GlobeTag[] }
    if (!data || !stds || !stockRet) return empty
    const land: Record<string, number[]> = {
      ...(data.landing as Record<string, number[]>),
      ...(stock ? { tsmc: [stock.lat, stock.lng] } : {}),
    }
    const stockName = stock?.name ?? '台積電'
    const color = (v: number | null | undefined) => (v == null || v === 0 ? t.flat : v > 0 ? t.up : t.down)
    const arcs: GlobeArc[] = []
    const points: GlobePoint[] = []
    data.series.forEach((s, k) => {
      const v = s.values[i]
      const [lat, lng] = land[s.target] ?? [25, 121.5]
      points.push({ id: s.id, lat: s.lat, lng: s.lng, color: color(v), radius: 0.35, label: `${s.name}（${s.place}）` })
      if (v == null) return
      const z = Math.abs(v) / stds.series[k]!
      const c = color(v)
      arcs.push({
        id: s.id,
        startLat: s.lat,
        startLng: s.lng,
        endLat: lat!,
        endLng: lng!,
        color: [alpha(c, 0.2), c],
        stroke: 0.2 + Math.min(z, 5) * 0.28,
        dashTime: Math.round(5200 / (1 + z)),
        altitude: 0.28 + k * 0.045,
        label: `${s.name}　${fmtChange(v, s.unit)}（${z.toFixed(1)} 個標準差）`,
      })
    })
    const rings: GlobeRing[] = []
    for (const [key, arr, sd, name] of [
      ['taiex', data.taiex, stds.taiex, '加權指數'],
      ['tsmc', stockRet, stds.stock, stockName],
    ] as const) {
      const v = arr[i]
      const [lat, lng] = land[key] ?? [25, 121.5]
      points.push({ id: key, lat: lat!, lng: lng!, color: color(v), radius: 0.3, label: name })
      if (v == null) continue
      const z = Math.abs(v) / sd
      rings.push({ id: key, lat: lat!, lng: lng!, color: color(v), maxR: 1 + Math.min(z, 5) * 0.9, speed: 1.2 + z * 0.6, period: 900 })
    }
    const us = data.series.map((s) => row(SHORT[s.id] ?? s.name, s.values[i], s.unit)).join('')
    const tw = row('加權指數', data.taiex[i], 'pct') + row(stockName, stockRet[i], 'pct')
    const tags: GlobeTag[] = [
      { id: 'us', lat: 47, lng: -66, html: `<div class="muted">美股前一晚</div>${us}` },
      { id: 'tw', lat: 28.5, lng: 126, html: `<div class="muted">台股 ${dates?.[data.start + i]?.slice(5) ?? ''}</div>${tw}` },
    ]
    return { arcs, points, rings, tags }
  }, [data, stds, i, t, dates, stock, stockRet])

  return { range, i, setPos, playing, togglePlay, step, fast, setFast, ticks, shocks, layers, date: dates?.[(data?.start ?? 0) + i] }
}

export type OvernightModel = ReturnType<typeof useOvernight>

type Props = {
  data: GlobeOvernight
  m: OvernightModel
  dates: string[]
  stock: PickedStock | null
  options: { symbol: string; name: string }[]
  onPick: (symbol: string) => void
}

export function OvernightSide({ data, m, dates, stock, options, onPick }: Props) {
  const i = m.i
  const sox = data.series.find((s) => s.id === 'GLOBAL:SOX')
  const adr = data.series.find((s) => s.id === 'GLOBAL:TSM_ADR')
  const nas = data.series.find((s) => s.id === 'GLOBAL:NASDAQ')
  const name = stock?.name ?? '台積電'
  const ret = stock?.ret ?? data.tsmc
  const fits = [
    { x: sox, y: ret, label: `費半 → ${name}` },
    { x: nas, y: ret, label: `那斯達克 → ${name}` },
    ...(stock?.symbol === '2330' || !stock ? [{ x: adr, y: ret, label: '台積電 ADR → 台積電' }] : []),
    { x: sox, y: data.taiex, label: '費半 → 加權指數' },
    { x: nas, y: data.taiex, label: '那斯達克 → 加權指數' },
  ].map((f) => ({ ...f, r: f.x ? regress(f.x.values, f.y, i) : null }))

  return (
    <>
      <Panel title={`${formatDate(m.date, true)} 的隔夜傳導`} bodyClassName="space-y-3 p-3 text-xs">
        <label className="flex items-center gap-2">
          <span className="shrink-0 text-2xs text-text-3">看哪一檔</span>
          <select
            value={stock?.symbol ?? '2330'}
            onChange={(e) => onPick(e.target.value)}
            className="num min-w-0 flex-1 rounded-control border border-line bg-raised px-1.5 py-1 text-xs text-text-1"
            aria-label="選擇股票"
          >
            {options.map((o) => (
              <option key={o.symbol} value={o.symbol}>
                {o.symbol} {o.name}
              </option>
            ))}
          </select>
        </label>
        {stock && <p className="-mt-1.5 text-2xs text-text-3">弧線落在 {stock.place}（{name}）</p>}
        <table className="w-full">
          <thead>
            <tr className="text-2xs text-text-3">
              <th className="pb-1 text-left font-normal">美股前一晚</th>
              <th className="pb-1 text-right font-normal">變動</th>
            </tr>
          </thead>
          <tbody>
            {data.series.map((s) => {
              const v = s.values[i]
              return (
                <tr key={s.id} className="border-t border-line/60">
                  <td className="py-1 text-text-2">{s.name}</td>
                  <td className={`num py-1 text-right ${v == null ? 'text-text-3' : v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-flat'}`}>
                    {fmtChange(v, s.unit)}
                  </td>
                </tr>
              )
            })}
            {[
              ['加權指數（當天）', data.taiex[i]],
              [`${name}（當天）`, ret[i]],
            ].map(([label, v]) => (
              <tr key={label as string} className="border-t border-line-strong">
                <td className="py-1 text-text-1">{label as string}</td>
                <td className={`num py-1 text-right ${v == null ? 'text-text-3' : (v as number) > 0 ? 'text-up' : (v as number) < 0 ? 'text-down' : 'text-flat'}`}>
                  {fmtChange(v as number | null, 'pct')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="space-y-1">
          <h3 className="text-2xs text-text-3">傳導強度（截至這天的近 {WINDOW} 個交易日）</h3>
          <ul className="space-y-0.5">
            {fits.map((f) => (
              <li key={f.label} className="flex justify-between gap-2">
                <span className="text-text-2">{f.label}</span>
                <span className="num text-text-1">{f.r ? `β ${f.r.beta.toFixed(2)}　ρ ${f.r.rho.toFixed(2)}` : '—'}</span>
              </li>
            ))}
          </ul>
          <p className="text-2xs leading-relaxed text-text-3">
            β：美股前一晚每變動 1%，台股當天平均同向變動的百分比；ρ：相關係數。這是統計上的連動，不代表因果。
          </p>
        </div>
        <div className="flex gap-3 text-2xs">
          <Link to="/stock/$symbol" params={{ symbol: stock?.symbol ?? '2330' }} className="text-accent hover:underline">
            {name}個股終端
          </Link>
          <Link to="/explain" className="text-accent hover:underline">
            漲跌解析
          </Link>
        </div>
        <Provenance ids={['overnight']} className="border-t border-line pt-2" />
      </Panel>
      <Panel title="最大的隔夜衝擊" className="min-h-0 flex-1" bodyClassName="overflow-auto">
        <ul className="text-xs">
          {m.shocks.map((s) => {
            const ser = data.series[s.lead]!
            const v = ser.values[s.i]
            return (
              <li key={s.i}>
                <button
                  type="button"
                  onClick={() => {
                    m.setPos(s.i)
                  }}
                  className={`grid w-full grid-cols-[auto_1fr_auto] gap-2 px-3 py-1.5 text-left hover:bg-hover ${s.i === i ? 'bg-raised' : ''}`}
                >
                  <span className="num text-text-2">{dates[data.start + s.i]}</span>
                  <span className="truncate text-text-3">{ser.name}</span>
                  <span className={`num ${v != null && v > 0 ? 'text-up' : 'text-down'}`}>{fmtChange(v, ser.unit)}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </Panel>
    </>
  )
}
