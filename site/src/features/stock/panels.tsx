import { useMemo } from 'react'

import { EmptyState } from '../../design/Panel'
import type { ActionInfo, Flows, MoveOut } from '../../lib/contract/types'
import { formatDate, formatLots, formatPct, formatPrice, formatYi, toneClass } from '../../lib/format'
import { type Candle, type FlowPoint, biggestMoves, sum } from '../../lib/series'
import { useView } from '../../lib/store'

/**
 * 大波動日：有因子拆解時列出可視區間內「個股特有」波動最大的異常日（扣除大盤、類股、隔夜美股）；
 * 沒有時退回單純的還原漲跌幅排名。
 */
export function BigMoves({
  candles,
  etf,
  adjusted,
  moves: anomalies,
}: {
  candles: Candle[]
  etf: boolean
  adjusted: boolean
  moves?: MoveOut[]
}) {
  const visible = useView((s) => s.visible)
  const hover = useView((s) => s.hoverDate)
  const focus = useView((s) => s.focus)
  const select = useView((s) => s.selectMove)
  const byTime = useMemo(() => new Map(candles.map((c) => [c.time, c])), [candles])
  const residual = Boolean(anomalies && anomalies.length)
  const moves = useMemo(() => {
    const inView = (t: string) => !visible || (t >= visible.from && t <= visible.to)
    if (anomalies && anomalies.length) {
      return anomalies
        .filter((m) => inView(m.date) && m.idio != null)
        .sort((a, b) => Math.abs(b.idio!) - Math.abs(a.idio!))
        .slice(0, 14)
        .map((m) => ({ time: m.date, ret: m.ret, close: byTime.get(m.date)?.close ?? 0, volume: 0, idio: m.idio }))
    }
    const rows = visible ? candles.filter((c) => inView(c.time)) : candles
    return biggestMoves(rows, 14).map((m) => ({ ...m, idio: null as number | null }))
  }, [candles, visible, anomalies, byTime])

  if (moves.length === 0) return <EmptyState title="可視區間內沒有異常波動" />
  return (
    <div className="flex h-full flex-col">
      <p className="px-3 pb-1 pt-1.5 text-2xs text-text-3">
        {residual ? '可視區間內個股特有波動最大的異常日（點擊看解析）' : `可視區間內單日漲跌幅前 ${moves.length} 名（未扣除大盤）`}
      </p>
      <ul className="min-h-0 flex-1 overflow-auto">
        {moves.map((m) => (
          <li key={m.time}>
            <button
              type="button"
              onClick={() => {
                focus(m.time)
                if (residual) select(m.time)
              }}
              className={`grid w-full grid-cols-[auto_1fr_auto] items-center gap-2 whitespace-nowrap px-3 py-1 text-left text-xs transition-colors hover:bg-hover ${
                hover === m.time ? 'bg-hover' : ''
              }`}
            >
              <span className="num text-text-2">{m.time}</span>
              <span className="num truncate text-right text-text-3">{formatPrice(m.close, { etf, adjusted })}</span>
              <span className={`num w-14 text-right ${toneClass(m.ret)}`}>{formatPct(m.ret, 1)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Stat({ label, children, sub }: { label: string; children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-2xs text-text-3">{label}</div>
      <div className="num truncate text-xs text-text-1">{children}</div>
      {sub && <div className="num truncate text-2xs text-text-3">{sub}</div>}
    </div>
  )
}

/** 右欄：外資動向摘要。 */
export function FlowSummary({ flows, points }: { flows: Flows | undefined; points: FlowPoint[] }) {
  if (!flows || points.length === 0) return <EmptyState title="無法人買賣資料" />
  const last = (n: number) => points.slice(-n)
  const f = (n: number) => sum(last(n).map((p) => p.foreign))
  const fv = (n: number) => sum(last(n).map((p) => p.foreignValue))
  const t20 = sum(last(20).map((p) => p.trust))

  // 連續買超或賣超的天數
  let streak = 0
  for (let j = points.length - 1; j >= 0; j--) {
    const v = points[j]!.foreign
    if (v === 0) break
    if (streak === 0) streak = v > 0 ? 1 : -1
    else if ((v > 0) === streak > 0) streak += streak > 0 ? 1 : -1
    else break
  }

  const pct = flows.foreign_pct
  const pctNow = pct[pct.length - 1]
  const pct1y = pct.length > 52 ? pct[pct.length - 53] : pct[0]

  const lastDate = points[points.length - 1]!.time
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3 p-3">
      <p className="col-span-2 -mb-1 text-2xs text-text-3">
        截至 <span className="num">{lastDate}</span>
      </p>
      {[5, 20, 60].map((n) => (
        <Stat key={n} label={`外資 近 ${n} 日`} sub={formatYi(fv(n), 'M')}>
          <span className={toneClass(f(n))}>{formatLots(f(n), true)} 張</span>
        </Stat>
      ))}
      <Stat label="外資連續">
        <span className={toneClass(streak)}>{streak === 0 ? '—' : `${streak > 0 ? '買超' : '賣超'} ${Math.abs(streak)} 日`}</span>
      </Stat>
      <Stat label="投信 近 20 日">
        <span className={toneClass(t20)}>{formatLots(t20, true)} 張</span>
      </Stat>
      <Stat
        label="外資持股比率"
        sub={pctNow != null && pct1y != null ? `一年 ${formatPct(pctNow - pct1y, 2, false).replace('%', ' 個百分點')}` : undefined}
      >
        {pctNow == null ? '—' : `${pctNow.toFixed(2)}%`}
      </Stat>
    </div>
  )
}

const ACTION_NAME: Record<string, string> = {
  dividend_cash: '除息',
  dividend_stock: '除權',
  dividend_both: '除權息',
  capital_reduction: '減資',
  par_change: '變更面額',
  etf_split: 'ETF 分割',
  etf_reverse_split: 'ETF 反分割',
}

export function ActionsTable({ actions }: { actions: ActionInfo[] }) {
  const focus = useView((s) => s.focus)
  if (actions.length === 0) return <EmptyState title="資料期間內沒有除權息、減資或分割" />
  const rows = [...actions].sort((a, b) => b.ex_date.localeCompare(a.ex_date))
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-panel text-2xs text-text-3">
        <tr className="border-b border-line">
          <th className="px-3 py-1.5 text-left font-normal">日期</th>
          <th className="px-3 py-1.5 text-left font-normal">類型</th>
          <th className="px-3 py-1.5 text-right font-normal">前收</th>
          <th className="px-3 py-1.5 text-right font-normal">參考價</th>
          <th className="px-3 py-1.5 text-right font-normal">價格調整</th>
          <th className="hidden px-3 py-1.5 text-left font-normal md:table-cell">說明</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((a) => (
          <tr
            key={`${a.ex_date}-${a.type}`}
            onClick={() => focus(a.ex_date)}
            className="cursor-pointer border-b border-line/60 transition-colors hover:bg-hover"
          >
            <td className="num px-3 py-1 text-text-2">{formatDate(a.ex_date)}</td>
            <td className={`px-3 py-1 ${a.type.startsWith('dividend') ? 'text-text-2' : 'text-warn'}`}>
              {ACTION_NAME[a.type] ?? a.type}
            </td>
            <td className="num px-3 py-1 text-right text-text-2">{formatPrice(a.prev_close, { etf: true })}</td>
            <td className="num px-3 py-1 text-right text-text-1">{formatPrice(a.ref_price, { etf: true })}</td>
            <td className="num px-3 py-1 text-right text-text-2">{formatPct(a.factor - 1)}</td>
            <td className="hidden truncate px-3 py-1 text-text-3 md:table-cell">{a.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function FlowTable({ points }: { points: FlowPoint[] }) {
  const focus = useView((s) => s.focus)
  const rows = points.slice(-60).reverse()
  if (rows.length === 0) return <EmptyState title="無法人買賣資料" />
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-panel text-2xs text-text-3">
        <tr className="border-b border-line">
          <th className="px-3 py-1.5 text-left font-normal">日期</th>
          <th className="px-3 py-1.5 text-right font-normal">外資（張）</th>
          <th className="px-3 py-1.5 text-right font-normal">外資估算金額</th>
          <th className="px-3 py-1.5 text-right font-normal">投信（張）</th>
          <th className="px-3 py-1.5 text-right font-normal">自營商（張）</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.time} onClick={() => focus(p.time)} className="cursor-pointer border-b border-line/60 hover:bg-hover">
            <td className="num px-3 py-1 text-text-2">{p.time}</td>
            <td className={`num px-3 py-1 text-right ${toneClass(p.foreign)}`}>{formatLots(p.foreign, true)}</td>
            <td className={`num px-3 py-1 text-right ${toneClass(p.foreignValue)}`}>{formatYi(p.foreignValue, 'M')}</td>
            <td className={`num px-3 py-1 text-right ${toneClass(p.trust)}`}>{formatLots(p.trust, true)}</td>
            <td className={`num px-3 py-1 text-right ${toneClass(p.dealer)}`}>{formatLots(p.dealer, true)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
