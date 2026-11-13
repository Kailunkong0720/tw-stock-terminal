import { useNavigate } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { CompareChart, type CompareLine } from '../../charts/CompareChart'
import { EmptyState, Panel } from '../../design/Panel'
import { Provenance } from '../../design/Provenance'
import { Segmented } from '../../design/Segmented'
import type { FinancialStock } from '../../lib/contract/types'
import { useFinancials } from '../../lib/data'
import { formatDate, formatPct, formatPrice, formatYi, toneClass } from '../../lib/format'

type SortKey = 'cap' | 'change_pct' | 'ret_1m' | 'ret_ytd' | 'ret_1y' | 'yield_1y' | 'foreign_5d' | 'foreign_20d' | 'trust_20d' | 'foreign_pct'

const COLS: { key: SortKey; label: string; title?: string }[] = [
  { key: 'change_pct', label: '漲跌' },
  { key: 'ret_1m', label: '1 個月' },
  { key: 'ret_ytd', label: '今年' },
  { key: 'ret_1y', label: '1 年' },
  { key: 'yield_1y', label: '殖利率', title: '近一年除權息合計 ÷ 收盤（含股票股利價值）' },
  { key: 'foreign_5d', label: '外資 5 日' },
  { key: 'foreign_20d', label: '外資 20 日' },
  { key: 'trust_20d', label: '投信 20 日' },
  { key: 'foreign_pct', label: '外資持股' },
]

function Spark({ values }: { values: (number | null)[] }) {
  const v = values.filter((x): x is number => x != null)
  if (v.length < 2) return null
  const lo = Math.min(...v)
  const hi = Math.max(...v)
  const w = 72
  const h = 18
  const pts = values
    .map((x, i) => (x == null ? null : `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((x - lo) / (hi - lo || 1)) * h).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')
  const up = v[v.length - 1]! >= v[0]!
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className={up ? 'text-up' : 'text-down'}>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  )
}

function median(xs: (number | null)[]): number | null {
  const v = xs.filter((x): x is number => x != null).sort((a, b) => a - b)
  if (!v.length) return null
  const m = Math.floor(v.length / 2)
  return v.length % 2 ? v[m]! : (v[m - 1]! + v[m]!) / 2
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-2xs text-text-3">{label}</div>
      <div className={`num text-base ${tone ?? 'text-text-1'}`}>{value}</div>
    </div>
  )
}

/** 金融股專區：金控、銀行、保險、證券期貨的表現、殖利率與法人動向。 */
export function FinancialsPage() {
  const fin = useFinancials()
  const navigate = useNavigate()
  const [group, setGroup] = useState('all')
  const [sort, setSort] = useState<SortKey>('cap')
  const [desc, setDesc] = useState(true)
  const d = fin.data

  const rows = useMemo(() => {
    const items = (d?.items ?? []).filter((x) => group === 'all' || x.group === group)
    return [...items].sort((a, b) => {
      const va = a[sort] ?? -Infinity
      const vb = b[sort] ?? -Infinity
      return desc ? vb - va : va - vb
    })
  }, [d, group, sort, desc])

  const lines = useMemo<CompareLine[]>(() => {
    if (!d) return []
    const colors: CompareLine['color'][] = ['accent', 'text2']
    return d.index.map((s, k) => ({
      name: s.name.replace('發行量加權股價指數', '加權指數'),
      color: colors[k] ?? 's3',
      points: s.values.flatMap((v, i) => (v == null ? [] : [{ time: d.weeks[i]!, value: v }])),
    }))
  }, [d])

  if (fin.isPending) return <div className="p-2"><Panel title="金融股"><EmptyState title="讀取中…" /></Panel></div>
  if (!d) return <div className="p-2"><Panel title="金融股"><EmptyState title="尚無金融股資料" detail="下次發布資料後會出現。" /></Panel></div>

  const sel = rows
  const rhos = d.items.map((x) => x.us10y_rho).filter((x): x is number => x != null)
  const maxRho = rhos.length ? Math.max(...rhos.map(Math.abs)) : null
  const totalForeign = sel.reduce((a, x) => a + (x.foreign_20d ?? 0), 0)
  const head = (key: SortKey, label: string, title?: string) => (
    <th key={key} className="px-2 py-1.5 text-right font-normal" title={title}>
      <button
        type="button"
        onClick={() => {
          if (sort === key) setDesc(!desc)
          else {
            setSort(key)
            setDesc(true)
          }
        }}
        className={`whitespace-nowrap hover:text-text-1 ${sort === key ? 'text-text-1' : ''}`}
      >
        {label}
        {sort === key ? (desc ? ' ↓' : ' ↑') : ''}
      </button>
    </th>
  )

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel
        title={`金融股（${formatDate(d.as_of)}）`}
        actions={
          <Segmented
            size="xs"
            label="類別"
            value={group}
            onChange={setGroup}
            options={[{ value: 'all', label: '全部' }, ...d.groups.map((g) => ({ value: g, label: g }))]}
          />
        }
        className="min-h-[520px]"
        bodyClassName="flex flex-col"
      >
        <div className="grid grid-cols-2 gap-3 border-b border-line px-3 py-2.5 sm:grid-cols-4">
          <Stat label="檔數" value={String(sel.length)} />
          <Stat label="今年報酬（中位數）" value={formatPct(median(sel.map((x) => x.ret_ytd)), 1, false)} tone={toneClass(median(sel.map((x) => x.ret_ytd)))} />
          <Stat label="殖利率（中位數）" value={formatPct(median(sel.map((x) => x.yield_1y)), 2, false).replace('+', '')} />
          <Stat label="外資 20 日合計" value={formatYi(totalForeign)} tone={toneClass(totalForeign)} />
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full min-w-[920px] text-xs">
            <thead className="sticky top-0 z-10 bg-panel text-2xs text-text-3">
              <tr className="border-b border-line">
                <th className="sticky left-0 bg-panel px-3 py-1.5 text-left font-normal">股票</th>
                <th className="px-2 py-1.5 text-right font-normal">收盤</th>
                {COLS.map((c) => head(c.key, c.label, c.title))}
                <th className="px-2 py-1.5 text-right font-normal">一年走勢</th>
              </tr>
            </thead>
            <tbody>
              {sel.map((x: FinancialStock) => (
                <tr
                  key={x.symbol}
                  onClick={() => navigate({ to: '/stock/$symbol', params: { symbol: x.symbol } })}
                  className="cursor-pointer border-b border-line/60 hover:bg-hover"
                >
                  <td className="sticky left-0 bg-panel px-3 py-1.5">
                    <span className="num text-text-2">{x.symbol}</span> <span className="text-text-1">{x.name}</span>
                    <span className="ml-1.5 text-2xs text-text-3">{x.group}</span>
                    {x.market === 'TPEx' && <span className="ml-1 text-2xs text-text-3">上櫃</span>}
                  </td>
                  <td className="num px-2 text-right text-text-1">{formatPrice(x.close)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.change_pct)}`}>{formatPct(x.change_pct, 2, false)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.ret_1m)}`}>{formatPct(x.ret_1m, 1, false)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.ret_ytd)}`}>{formatPct(x.ret_ytd, 1, false)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.ret_1y)}`}>{formatPct(x.ret_1y, 1, false)}</td>
                  <td className="num px-2 text-right text-text-1">{x.yield_1y == null ? '—' : `${x.yield_1y.toFixed(2)}%`}</td>
                  <td className={`num px-2 text-right ${toneClass(x.foreign_5d)}`}>{formatYi(x.foreign_5d)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.foreign_20d)}`}>{formatYi(x.foreign_20d)}</td>
                  <td className={`num px-2 text-right ${toneClass(x.trust_20d)}`}>{formatYi(x.trust_20d)}</td>
                  <td className="num px-2 text-right text-text-2">
                    {x.foreign_pct == null ? '—' : `${x.foreign_pct.toFixed(1)}%`}
                    {x.foreign_pct_chg_4w != null && (
                      <span className={`ml-1 text-2xs ${toneClass(x.foreign_pct_chg_4w)}`}>
                        {x.foreign_pct_chg_4w > 0 ? '+' : ''}
                        {x.foreign_pct_chg_4w.toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <Spark values={x.weekly} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="flex min-h-0 flex-col gap-2">
        <Panel title="金融保險類 vs 加權指數（2020 年初 = 100）" className="h-72 xl:h-80">
          {lines.length ? <CompareChart lines={lines} /> : <EmptyState title="沒有指數資料" />}
        </Panel>
        <Panel title="怎麼讀" className="min-h-0 flex-1" bodyClassName="space-y-1.5 overflow-auto p-3 text-2xs leading-relaxed text-text-3">
          <p>報酬為還原後（含除權息）。殖利率是近一年除權息合計 ÷ 收盤，含股票股利的價值，純現金增資不算。</p>
          <p>外資、投信為估算金額（買賣超股數 × 收盤價）；外資持股旁的數字是四週來的變化（百分點）。</p>
          <p>類別依公司名稱判斷（證交所的產業別只有「金融保險」一類）。點任一列開啟個股終端。</p>
          {maxRho != null && (
            <p>
              與美國十年期公債殖利率前一晚變動的相關係數（近 500 個交易日），絕對值最大為 {maxRho.toFixed(2)}
              {maxRho < 0.15 ? '：台灣金融股的日常漲跌與美債殖利率的隔夜變動沒有明顯關係。' : '。'}
            </p>
          )}
          <Provenance ids={['financials']} className="border-t border-line pt-2" />
        </Panel>
      </div>
    </div>
  )
}
