import { Link, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { KLineChart } from '../../charts/KLineChart'
import { EmptyState, Panel } from '../../design/Panel'
import { Provenance } from '../../design/Provenance'
import { Segmented } from '../../design/Segmented'
import { useBars, useCalendar, useEvents, useMoves, useSecurities, useTimeline } from '../../lib/data'
import { formatDateTime, formatPct, toneClass } from '../../lib/format'
import { toCandles } from '../../lib/series'
import { MoveDetail } from './MoveDetail'

/** /explain：全市場的大波動與市場事件。 */
export function ExplainIndexPage() {
  const tl = useTimeline()
  const [year, setYear] = useState<string>('all')
  const years = useMemo(() => {
    const ys = new Set((tl.data?.moves ?? []).map((m) => m.date.slice(0, 4)))
    return ['all', ...[...ys].sort().reverse()]
  }, [tl.data])
  if (tl.isPending) return <div className="p-2"><Panel title="漲跌解析"><EmptyState title="讀取中…" /></Panel></div>
  if (!tl.data) return <div className="p-2"><Panel title="漲跌解析"><EmptyState title="尚無事件資料" /></Panel></div>
  const moves = tl.data.moves.filter((m) => year === 'all' || m.date.startsWith(year)).slice().reverse()
  const market = tl.data.market.filter((e) => year === 'all' || e.trade_date.startsWith(year)).slice().reverse()
  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Panel
        title={`追蹤池最大的個股特有波動（${moves.length}）`}
        className="min-h-96"
        bodyClassName="overflow-auto"
        actions={
          <Segmented size="xs" label="年份" value={year} onChange={setYear} options={years.map((y) => ({ value: y, label: y === 'all' ? '全部' : y }))} />
        }
      >
        <ul className="text-xs">
          {moves.map((m) => (
            <li key={`${m.symbol}-${m.date}`} className="border-b border-line/60">
              <Link
                to="/explain/$symbol/$date"
                params={{ symbol: m.symbol, date: m.date }}
                className="grid grid-cols-[auto_auto_minmax(0,6rem)_auto_1fr] items-center gap-3 px-3 py-1.5 hover:bg-hover"
              >
                <span className="num text-text-2">{m.date}</span>
                <span className="num text-text-1">{m.symbol}</span>
                <span className="truncate text-text-1">{m.name}</span>
                <span className={`num w-14 text-right ${toneClass(m.ret)}`}>{formatPct(m.ret, 1)}</span>
                <span className="truncate text-text-3">
                  {m.top ? (
                    <>
                      <span className="text-text-2">{m.top.type_name}</span>　{m.top.title}
                    </>
                  ) : (
                    '未找到明確的對應消息'
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title={`市場事件（${market.length}）`} className="min-h-96" bodyClassName="overflow-auto">
        <ul className="text-xs">
          {market.map((e) => (
            <li key={e.id} className="grid grid-cols-[auto_1fr] gap-3 border-b border-line/60 px-3 py-1.5">
              <span className="num text-text-2">{e.trade_date}</span>
              <span className={e.direction > 0 ? 'text-up' : e.direction < 0 ? 'text-down' : 'text-text-2'}>{e.title}</span>
            </li>
          ))}
        </ul>
        <p className="px-3 py-2 text-2xs text-text-3">市場事件由資料產生：前一晚費城半導體指數漲跌 3% 以上、加權指數當日漲跌 2.5% 以上。</p>
        <Provenance ids={['factor', 'attribution']} className="px-3 pb-3" />
      </Panel>
    </div>
  )
}

/** /explain/:symbol/:date：單日漲跌的完整解析。 */
export function ExplainDetailPage() {
  const { symbol, date } = useParams({ from: '/explain/$symbol/$date' })
  const secs = useSecurities()
  const moves = useMoves(symbol)
  const sec = secs.data?.items.find((s) => s.symbol === symbol)
  const events = useEvents(symbol, Boolean(sec?.tracked))
  const bars = useBars(symbol)
  const cal = useCalendar()
  const m = moves.data?.moves.find((x) => x.date === date)
  const candles = useMemo(() => (bars.data && cal.data ? toCandles(bars.data, cal.data.dates, true) : []), [bars.data, cal.data])
  const win = useMemo(() => {
    const dates = cal.data?.dates
    if (!dates) return null
    const i = dates.indexOf(date)
    if (i < 0) return null
    return { from: dates[Math.max(0, i - 60)]!, to: dates[Math.min(dates.length - 1, i + 20)]! }
  }, [cal.data, date])
  const nearby = useMemo(() => {
    const dates = cal.data?.dates ?? []
    const i = dates.indexOf(date)
    const lo = dates[Math.max(0, i - 5)] ?? date
    const hi = dates[Math.min(dates.length - 1, i + 5)] ?? date
    return (events.data?.events ?? []).filter((e) => e.trade_date >= lo && e.trade_date <= hi)
  }, [events.data, cal.data, date])

  const title = (
    <span>
      <Link to="/stock/$symbol" params={{ symbol }} className="num text-text-1 hover:text-accent">
        {symbol}
      </Link>{' '}
      {sec?.name} · 漲跌解析
    </span>
  )
  if (moves.isPending || bars.isPending) return <div className="p-2"><Panel title={title}><EmptyState title="讀取中…" /></Panel></div>
  if (!m) {
    return (
      <div className="p-2">
        <Panel title={title}>
          <EmptyState title={`${date} 不是這檔股票的異常波動日`} detail="只有扣除大盤、類股與隔夜美股後仍有明顯變動的日子才有解析。" />
        </Panel>
      </div>
    )
  }
  return (
    <div className="grid min-h-full gap-2 p-2 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <Panel title={title} bodyClassName="p-4">
        <MoveDetail m={m} tracked={Boolean(moves.data?.tracked)} symbol={symbol} />
        <Provenance ids={['factor', 'attribution']} className="mt-4 border-t border-line pt-2" />
      </Panel>
      <div className="flex min-h-0 flex-col gap-2">
        <Panel title="前後走勢（還原）" className="h-80">
          {candles.length > 0 && (
            <KLineChart
              candles={candles}
              actions={bars.data?.actions ?? []}
              flows={null}
              subPane="volume"
              range="3M"
              adjusted
              etf={sec?.kind === 'etf'}
              window={win}
              moves={moves.data?.moves.map((x) => ({ date: x.date, ret: x.ret })) ?? []}
            />
          )}
        </Panel>
        <Panel title="前後 5 個交易日的公告" className="min-h-40" bodyClassName="overflow-auto">
          {nearby.length === 0 ? (
            <EmptyState title={sec?.tracked ? '這段期間沒有重大訊息' : '這檔不在追蹤池，沒有收集公告'} />
          ) : (
            <ul className="text-xs">
              {nearby.map((e) => (
                <li key={e.id} className={`grid grid-cols-[auto_auto_1fr] gap-3 border-b border-line/60 px-3 py-1.5 ${e.trade_date === date ? 'bg-hover' : ''}`}>
                  <span className="num text-text-2">{formatDateTime(e.at)}</span>
                  <span className="text-text-3">{e.type_name}</span>
                  <span className="text-text-1">{e.title}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  )
}
