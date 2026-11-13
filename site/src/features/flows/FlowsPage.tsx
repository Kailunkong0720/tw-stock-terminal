import { Link } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { IndexChart } from '../../charts/IndexChart'
import { alpha, readTheme } from '../../charts/theme'
import { EmptyState, Panel } from '../../design/Panel'
import { Segmented } from '../../design/Segmented'
import { useCalendar, useHeatmap, useIndustryFlows, useMarketFlows, useOverview } from '../../lib/data'
import { formatYi, toneClass } from '../../lib/format'
import { useUpDown } from '../../lib/prefs'

/** 產業 × 月份的外資估算淨流入矩陣（PLAN.md 7.5 第 5 項）。 */
function IndustryMatrix() {
  const ind = useIndustryFlows()
  useUpDown()
  const t = readTheme()
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null)

  const m = useMemo(() => {
    const d = ind.data
    if (!d) return null
    // 週 → 月
    const months: string[] = []
    const colOf = d.weeks.map((w) => {
      const k = w.slice(0, 7)
      if (months[months.length - 1] !== k) months.push(k)
      return months.length - 1
    })
    const rows = d.industries.map((s) => {
      const v = new Array<number>(months.length).fill(0)
      s.foreign_value.forEach((x, i) => (v[colOf[i]!]! += x))
      return { industry: s.industry, v, total: v.reduce((a, b) => a + b, 0) }
    })
    rows.sort((a, b) => b.total - a.total)
    const all = rows.flatMap((r) => r.v.map(Math.abs)).sort((a, b) => a - b)
    const scale = all[Math.floor(all.length * 0.95)] || 1
    return { months, rows, scale }
  }, [ind.data])

  if (!m) return <EmptyState title={ind.isPending ? '讀取中…' : '尚無資料'} />
  const cell = (v: number) => {
    const a = Math.min(1, Math.abs(v) / m.scale)
    return v === 0 ? t.raised : alpha(v > 0 ? t.up : t.down, 0.12 + 0.88 * a)
  }
  const hv = hover ? m.rows[hover.r] : null
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-3 pt-2">
        <div className="grid gap-y-px" style={{ gridTemplateColumns: `6.5rem repeat(${m.months.length}, minmax(5px, 1fr)) 4.5rem` }}>
          {m.rows.map((r, ri) => (
            <div key={r.industry} className="contents">
              <div className="truncate pr-2 text-2xs leading-4 text-text-2">{r.industry}</div>
              {r.v.map((v, ci) => (
                <div
                  key={ci}
                  onMouseEnter={() => setHover({ r: ri, c: ci })}
                  onMouseLeave={() => setHover(null)}
                  className="h-4"
                  style={{ background: cell(v), outline: hover?.r === ri && hover?.c === ci ? `1px solid ${t.text1}` : undefined }}
                />
              ))}
              <div className={`num pl-2 text-right text-2xs leading-4 ${toneClass(r.total)}`}>{formatYi(r.total)}</div>
            </div>
          ))}
          <div />
          {m.months.map((mo, i) => (
            <div key={mo} className="num pt-1 text-[9px] text-text-3">
              {mo.endsWith('-01') || i === 0 ? mo.slice(0, 4) : ''}
            </div>
          ))}
          <div />
        </div>
      </div>
      <div className="flex h-7 items-center gap-3 border-t border-line px-3 text-2xs text-text-3">
        {hv && hover ? (
          <>
            <span className="text-text-1">{hv.industry}</span>
            <span className="num">{m.months[hover.c]}</span>
            <span className={`num ${toneClass(hv.v[hover.c])}`}>{formatYi(hv.v[hover.c])}</span>
          </>
        ) : (
          <span>每格是一個月的外資估算淨流入（買賣超股數 × 收盤價）；右欄為 2020 年以來合計。滑過看數字。</span>
        )}
      </div>
    </div>
  )
}

/** 資金流向頁：全市場外資、產業輪動、當日外資買賣超最大的個股。 */
export function FlowsPage() {
  const mf = useMarketFlows()
  const ov = useOverview()
  const cal = useCalendar()
  const heat = useHeatmap()
  const [who, setWho] = useState<'foreign' | 'trust' | 'dealer'>('foreign')

  const series = useMemo(() => {
    const dates = cal.data?.dates
    const t = ov.data?.taiex
    const f = mf.data
    if (!dates || !t || !f) return null
    const line = t.close.flatMap((v, i) => (v == null ? [] : [{ time: dates[t.start + i]!, value: v }]))
    const arr = f[who]
    const bars = arr.flatMap((v, i) => (v == null ? [] : [{ time: dates[f.start + i]!, value: v }]))
    const ranked = [...bars].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 12)
    return { line, bars, markers: ranked.map((b) => ({ time: b.time, up: b.value > 0 })) }
  }, [cal.data, ov.data, mf.data, who])

  const top = useMemo(() => {
    const h = heat.data
    if (!h) return { buy: [], sell: [] }
    const rows = h.items.map((it, i) => ({ ...it, v: h.foreign_1d[i] })).filter((r): r is typeof r & { v: number } => r.v != null)
    rows.sort((a, b) => b.v - a.v)
    return { buy: rows.slice(0, 10), sell: rows.slice(-10).reverse() }
  }, [heat.data])

  /** 全市場法人資料的最後一天（回補還沒到最新日時，用來說明為什麼右欄是空的） */
  const flowsUntil = useMemo(() => {
    const f = mf.data
    const dates = cal.data?.dates
    if (!f || !dates) return null
    for (let i = f.foreign.length - 1; i >= 0; i--) if (f.foreign[i] != null) return dates[f.start + i] ?? null
    return null
  }, [mf.data, cal.data])

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_320px] xl:grid-rows-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel
        title="全市場法人買賣超（億元）與加權指數"
        actions={
          <Segmented
            size="xs"
            label="法人"
            value={who}
            onChange={(v) => setWho(v as typeof who)}
            options={[
              { value: 'foreign', label: '外資' },
              { value: 'trust', label: '投信' },
              { value: 'dealer', label: '自營商' },
            ]}
          />
        }
        className="min-h-80"
      >
        {series ? <IndexChart line={series.line} bars={series.bars} markers={series.markers} /> : <EmptyState title="讀取中…" />}
      </Panel>

      <Panel title={`當日外資買賣超最大（${heat.data?.as_of ?? ''}）`} className="min-h-80 xl:row-span-2" bodyClassName="overflow-auto">
        {heat.data && top.buy.length === 0 && (
          <EmptyState
            title="這一天還沒有法人資料"
            detail={flowsUntil ? `目前法人買賣超資料到 ${flowsUntil}，其餘日期回補中。` : '法人買賣超資料回補中。'}
          />
        )}
        {(top.buy.length > 0 ? [['買超', top.buy], ['賣超', top.sell]] : []).map(([label, rows]) => (
          <div key={label as string} className="pb-2">
            <h3 className="px-3 pb-1 pt-2 text-2xs text-text-3">{label as string}</h3>
            <ul className="text-xs">
              {(rows as typeof top.buy).map((r) => (
                <li key={r.symbol}>
                  <Link
                    to="/stock/$symbol"
                    params={{ symbol: r.symbol }}
                    className="grid grid-cols-[auto_1fr_auto] gap-2 px-3 py-1 hover:bg-hover"
                  >
                    <span className="num text-text-2">{r.symbol}</span>
                    <span className="truncate text-text-1">{r.name}</span>
                    <span className={`num ${toneClass(r.v)}`}>{formatYi(r.v)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="px-3 pb-3 text-2xs leading-relaxed text-text-3">
          外資採證交所定義（不含外資自營商）。金額為估算：買賣超股數 × 收盤價。這是交易所內的買賣淨額，不是跨境資金的匯入匯出。
        </p>
      </Panel>

      <Panel title="產業輪動：外資每月淨流入" className="min-h-80">
        <IndustryMatrix />
      </Panel>
    </div>
  )
}
