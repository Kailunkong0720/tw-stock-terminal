import { IconStar, IconStarFilled } from '@tabler/icons-react'

import type { SecurityInfo } from '../../lib/contract/types'
import { formatDate, formatLots, formatPct, formatPrice, formatSigned, kToYi, toneClass } from '../../lib/format'
import type { Candle } from '../../lib/series'
import { usePrefs } from '../../lib/store'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="shrink-0">
      <div className="text-2xs text-text-3">{label}</div>
      <div className="num text-xs text-text-1">{children}</div>
    </div>
  )
}

/** 標的資訊條（參考設計最上方那一列）。 */
export function InfoBar({ sec, raw, adj }: { sec: SecurityInfo | undefined; raw: Candle[]; adj: Candle[] }) {
  const watch = usePrefs((s) => s.watchlist)
  const toggle = usePrefs((s) => s.toggleWatch)
  const last = raw[raw.length - 1]
  const prev = raw[raw.length - 2]
  const etf = sec?.kind === 'etf'
  // 漲跌以還原價計算，除權息日才不會顯示成大跌
  const a1 = adj[adj.length - 1]
  const a0 = adj[adj.length - 2]
  const chg = a1 && a0 ? a1.close / a0.close - 1 : null
  const chgPts = a1 && a0 ? a1.close - a0.close : null
  const first = adj[0]
  const totalRet = first && a1 ? a1.close / first.close - 1 : null
  let hi = -Infinity
  let lo = Infinity
  let hiT = ''
  let loT = ''
  for (const c of adj) {
    if (c.high > hi) [hi, hiT] = [c.high, c.time]
    if (c.low < lo) [lo, loT] = [c.low, c.time]
  }
  const watched = sec ? watch.includes(sec.symbol) : false

  return (
    <div className="flex h-full items-center gap-6 overflow-x-auto px-4">
      <div className="flex shrink-0 items-center gap-3">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="num text-base font-medium text-text-1">{sec?.symbol ?? '—'}</span>
            <span className="text-sm text-text-1">{sec?.name}</span>
          </div>
          <div className="text-2xs text-text-3">
            {sec?.industry ?? '—'}
            {sec && !sec.active && <span className="ml-2 text-warn">已停止交易（最後交易日 {sec.last}）</span>}
          </div>
        </div>
        {sec && (
          <button
            type="button"
            onClick={() => toggle(sec.symbol)}
            aria-pressed={watched}
            aria-label={watched ? '從自選移除' : '加入自選'}
            title={watched ? '從自選移除' : '加入自選'}
            className={`rounded-control p-1 transition-colors hover:bg-hover ${watched ? 'text-accent' : 'text-text-3'}`}
          >
            {watched ? <IconStarFilled size={14} /> : <IconStar size={14} stroke={1.5} />}
          </button>
        )}
      </div>

      <div className="shrink-0">
        <div className={`num text-lg font-medium leading-tight ${toneClass(chg)}`}>
          {formatPrice(last?.close, { etf })}
        </div>
        <div className={`num text-2xs ${toneClass(chg)}`}>
          {formatSigned(chgPts)} {formatPct(chg)}
        </div>
      </div>

      <div className="h-8 w-px shrink-0 bg-line" />

      <Field label="開">{formatPrice(last?.open, { etf })}</Field>
      <Field label="高">{formatPrice(last?.high, { etf })}</Field>
      <Field label="低">{formatPrice(last?.low, { etf })}</Field>
      <Field label="昨收">{formatPrice(prev?.close, { etf })}</Field>
      <Field label="成交量（張）">{formatLots(last?.volume)}</Field>
      <Field label="成交值">{last ? `${kToYi(last.value).toFixed(2)} 億` : '—'}</Field>

      <div className="h-8 w-px shrink-0 bg-line" />

      <Field label={`${first ? first.time.slice(0, 4) : ''} 年以來（還原）`}>
        <span className={toneClass(totalRet)}>{formatPct(totalRet, 1)}</span>
      </Field>
      <Field label="期間最高（還原）">
        {Number.isFinite(hi) ? formatPrice(hi, { adjusted: true }) : '—'}
        <span className="ml-1 text-2xs text-text-3">{hiT.slice(0, 7)}</span>
      </Field>
      <Field label="期間最低（還原）">
        {Number.isFinite(lo) ? formatPrice(lo, { adjusted: true }) : '—'}
        <span className="ml-1 text-2xs text-text-3">{loT.slice(0, 7)}</span>
      </Field>
      <Field label="資料日期">{formatDate(last?.time)}</Field>
    </div>
  )
}
