import { Link } from '@tanstack/react-router'

import { CONTRACT_VERSION, useMeta, useSecurities } from '../lib/data'
import { formatDate, formatDateTime, formatPct, formatPrice, toneClass } from '../lib/format'
import { usePrefs } from '../lib/store'

function Dot({ tone }: { tone: 'ok' | 'warn' | 'off' }) {
  const color = tone === 'ok' ? 'bg-accent' : tone === 'warn' ? 'bg-warn' : 'bg-text-3'
  return <span className={`inline-block size-1.5 shrink-0 rounded-full ${color}`} aria-hidden="true" />
}

/** 自選股的最新收盤（參考設計底部的跑馬燈）。內容少時不捲動。 */
function Ticker() {
  const watch = usePrefs((s) => s.watchlist)
  const secs = useSecurities()
  const by = new Map((secs.data?.items ?? []).map((s) => [s.symbol, s]))
  const items = watch.map((w) => by.get(w)).filter((s) => s != null)
  if (items.length === 0) return null
  return (
    <div className="flex min-w-0 flex-1 items-center gap-4 overflow-hidden">
      {items.map((s) => (
        <Link
          key={s.symbol}
          to="/stock/$symbol"
          params={{ symbol: s.symbol }}
          className="flex shrink-0 items-center gap-1.5 text-text-3 hover:text-text-1"
        >
          <span className="text-text-2">{s.name}</span>
          <span className="num text-text-2">{formatPrice(s.close, { etf: s.kind === 'etf' })}</span>
          <span className={`num ${toneClass(s.change_pct)}`}>{formatPct(s.change_pct, 2, false)}</span>
        </Link>
      ))}
    </div>
  )
}

/** 底部狀態列（參考設計的連線狀態列）：資料截止日、來源狀態、自選股。 */
export function StatusBar() {
  const meta = useMeta()

  let left
  if (meta.isPending) {
    left = (
      <span className="flex items-center gap-1.5 text-text-3">
        <Dot tone="off" />
        讀取資料狀態…
      </span>
    )
  } else if (meta.isError) {
    left = (
      <span className="flex items-center gap-1.5 text-warn">
        <Dot tone="warn" />
        {meta.error.message}
      </span>
    )
  } else {
    const m = meta.data
    const hasData = Boolean(m.data_as_of)
    const bad = m.sources.filter((s) => s.status !== 'ok')
    left = (
      <>
        <span
          className="flex shrink-0 items-center gap-1.5"
          title={`涵蓋 ${formatDate(m.coverage_start)} 起；產生於 ${formatDateTime(m.generated_at)}${
            bad.length ? `\n未完成：${bad.map((s) => s.name).join('、')}` : ''
          }`}
        >
          <Dot tone={hasData ? (bad.length ? 'warn' : 'ok') : 'warn'} />
          <span className="text-text-2">資料截至</span>
          <span className="num text-text-1">{hasData ? formatDate(m.data_as_of, true) : '尚無資料'}</span>
        </span>
        <span className="h-3 w-px shrink-0 bg-line" />
      </>
    )
  }

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t border-line bg-panel px-4 text-2xs">
      {left}
      <Ticker />
      <span className="ml-auto hidden shrink-0 text-text-3 md:inline">非即時資料 · 僅供研究，不構成投資建議</span>
      <span className="num shrink-0 text-text-3" title="資料契約版本">
        v{CONTRACT_VERSION}
      </span>
    </footer>
  )
}
