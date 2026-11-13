import { IconPlayerPauseFilled, IconPlayerPlayFilled } from '@tabler/icons-react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'

import { IndexChart } from '../../charts/IndexChart'
import { Treemap } from '../../charts/Treemap'
import { EmptyState, Panel } from '../../design/Panel'
import { Segmented } from '../../design/Segmented'
import { useCalendar, useHeatmap, useHeatmapHistory, useOverview, useTimeline } from '../../lib/data'
import { formatPct, formatYi, toneClass } from '../../lib/format'

type Mode = 'ret' | 'cum' | 'foreign'

function p90(values: (number | null)[]): number {
  const a = values.filter((v): v is number => v != null).map(Math.abs).sort((x, y) => x - y)
  return a.length ? a[Math.floor(a.length * 0.9)]! : 1
}

/** 市場總覽（PLAN.md 7.5 第 4 項）：熱力圖可沿 2020 年至今的時間軸播放。 */
export function MarketPage() {
  const heat = useHeatmap()
  const ov = useOverview()
  const cal = useCalendar()
  const tl = useTimeline()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('ret')
  const [week, setWeek] = useState<number | null>(null) // null = 資料截止日當天
  const [playing, setPlaying] = useState(false)
  const [industry, setIndustry] = useState<string | null>(null)

  const h = heat.data
  const nWeeks = h?.weeks.length ?? 0
  // 各週歷史只有在播放、拖動時間軸或看累積報酬時才下載
  const needHistory = mode === 'cum' || week != null || playing
  const hist = useHeatmapHistory(needHistory).data

  // 累積報酬：從第一週累乘到所選的週
  const cum = useMemo(() => {
    if (!h || !hist) return []
    const out: (number | null)[][] = []
    const acc = h.items.map(() => 1)
    const seen = h.items.map(() => false)
    for (let w = 0; w < hist.weeks.length; w++) {
      out.push(
        h.items.map((_, j) => {
          const r = hist.ret[w]![j]
          if (r != null) {
            acc[j] = acc[j]! * (1 + r / 100)
            seen[j] = true
          }
          return seen[j] ? (acc[j]! - 1) * 100 : null
        }),
      )
    }
    return out
  }, [h, hist])

  const { values, scale, label, fmt } = useMemo(() => {
    if (!h) return { values: [] as (number | null)[], scale: 1, label: '', fmt: (v: number | null) => String(v) }
    const pct = (v: number | null) => formatPct(v, 1, false)
    const yi = (v: number | null) => (v == null ? '—' : formatYi(v))
    // 歷史還在下載時先顯示當天
    const wk = hist ? week : null
    const loading = needHistory && !hist ? '（讀取歷史資料中…）' : ''
    if (mode === 'foreign') {
      const v = wk == null ? h.foreign_1d : hist!.foreign[wk]!
      return {
        values: v,
        scale: Math.max(1, p90(v)),
        label: (wk == null ? '當日外資買賣超' : '當週外資買賣超') + loading,
        fmt: yi,
      }
    }
    if (mode === 'cum' && hist) {
      const w = week ?? nWeeks - 1
      return { values: cum[w] ?? [], scale: 100, label: `${h.weeks[0]} 起累積報酬`, fmt: pct }
    }
    const v = wk == null ? h.ret_1d : hist!.ret[wk]!
    return { values: v, scale: wk == null ? 5 : 8, label: (wk == null ? '當日漲跌' : '當週漲跌') + loading, fmt: pct }
  }, [h, hist, needHistory, mode, week, cum, nWeeks])

  useEffect(() => {
    if (!playing || !h || !hist) return
    const id = window.setTimeout(() => {
      const w = week ?? -1
      if (w < nWeeks - 1) setWeek(w + 1)
      else setPlaying(false)
    }, 260)
    return () => window.clearTimeout(id)
  }, [playing, week, nWeeks, h, hist])

  const [indexId, setIndexId] = useState<'taiex' | 'otc'>('taiex')
  const hasOtc = Boolean(ov.data?.otc)
  const taiex = useMemo(() => {
    const t = indexId === 'otc' && ov.data?.otc ? ov.data.otc : ov.data?.taiex
    const dates = cal.data?.dates
    if (!t || !dates) return []
    return t.close.flatMap((v, i) => (v == null ? [] : [{ time: dates[t.start + i]!, value: v }]))
  }, [ov.data, cal.data, indexId])
  const taiexMarks = useMemo(
    () =>
      indexId === 'otc'
        ? []
        : (tl.data?.market ?? [])
            .filter((e) => e.title.startsWith('加權指數'))
            .map((e) => ({ time: e.trade_date, up: e.direction > 0 })),
    [tl.data, indexId],
  )
  const recent = (tl.data?.moves ?? []).slice(-14).reverse()

  const dateLabel = h ? (week == null ? h.as_of : h.weeks[week]) : ''

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_360px] xl:grid-rows-[minmax(0,1fr)_260px]">
      <Panel
        title={
          <span className="flex items-center gap-2">
            市場熱力圖
            {industry && (
              <button type="button" onClick={() => setIndustry(null)} className="rounded-sm bg-raised px-1.5 text-2xs text-text-2 hover:text-text-1">
                {industry} ✕
              </button>
            )}
          </span>
        }
        actions={
          <Segmented
            size="xs"
            label="配色"
            value={mode}
            onChange={(v) => setMode(v as Mode)}
            options={[
              { value: 'ret', label: '漲跌' },
              { value: 'cum', label: '累積' },
              { value: 'foreign', label: '外資' },
            ]}
          />
        }
        className="min-h-[520px]"
        bodyClassName="flex flex-col"
      >
        {!h ? (
          <EmptyState title={heat.isPending ? '讀取中…' : '尚無熱力圖資料'} />
        ) : (
          <>
            <div className="relative min-h-0 flex-1">
              <Treemap
                items={h.items}
                values={values}
                scale={scale}
                format={fmt}
                onPick={(s) => navigate({ to: '/stock/$symbol', params: { symbol: s } })}
                focusIndustry={industry}
                onIndustry={setIndustry}
              />
            </div>
            <div className="flex items-center gap-3 border-t border-line px-3 py-2 text-xs">
              <button
                type="button"
                onClick={() => {
                  if (!playing && (week == null || week >= nWeeks - 1)) setWeek(0)
                  setPlaying(!playing)
                }}
                aria-label={playing ? '暫停' : '播放 2020 年至今'}
                className="flex size-7 shrink-0 items-center justify-center rounded-control bg-accent text-canvas"
              >
                {playing ? <IconPlayerPauseFilled size={13} /> : <IconPlayerPlayFilled size={13} />}
              </button>
              <input
                type="range"
                min={0}
                max={nWeeks}
                value={week == null ? nWeeks : week}
                onChange={(e) => {
                  setPlaying(false)
                  const v = Number(e.target.value)
                  setWeek(v >= nWeeks ? null : v)
                }}
                aria-label="週"
                className="min-w-24 flex-1 accent-[var(--accent)]"
              />
              <span className="num w-24 shrink-0 text-right text-text-1">{dateLabel}</span>
              <span className="hidden shrink-0 text-text-3 sm:inline">{label}</span>
            </div>
          </>
        )}
      </Panel>

      <Panel title="類股表現" className="min-h-72" bodyClassName="overflow-auto">
        {!ov.data ? (
          <EmptyState title="讀取中…" />
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-panel text-2xs text-text-3">
              <tr className="border-b border-line">
                <th className="px-3 py-1.5 text-left font-normal">類股</th>
                <th className="px-2 py-1.5 text-right font-normal">當日</th>
                <th className="px-2 py-1.5 text-right font-normal">1 月</th>
                <th className="px-2 py-1.5 text-right font-normal">今年</th>
                <th className="px-3 py-1.5 text-right font-normal">1 年</th>
              </tr>
            </thead>
            <tbody>
              {[...ov.data.sectors]
                .sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0))
                .map((s) => (
                  <tr
                    key={s.index_id}
                    onClick={() => setIndustry(industry === s.industry ? null : s.industry)}
                    className={`cursor-pointer border-b border-line/60 hover:bg-hover ${industry === s.industry ? 'bg-hover' : ''}`}
                  >
                    <td className="px-3 py-1 text-text-1">{s.industry}</td>
                    {[s.change_pct, s.ret_1m, s.ret_ytd].map((v, i) => (
                      <td key={i} className={`num px-2 py-1 text-right ${toneClass(v)}`}>
                        {formatPct(v, 1, false)}
                      </td>
                    ))}
                    <td className={`num px-3 py-1 text-right ${toneClass(s.ret_1y)}`}>{formatPct(s.ret_1y, 1, false)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title={indexId === 'otc' ? '櫃買指數' : '加權指數（▲▼ 單日漲跌 2.5% 以上）'}
        actions={
          hasOtc ? (
            <Segmented
              size="xs"
              label="指數"
              value={indexId}
              onChange={(v) => setIndexId(v as 'taiex' | 'otc')}
              options={[
                { value: 'taiex', label: '加權' },
                { value: 'otc', label: '櫃買' },
              ]}
            />
          ) : undefined
        }
        className="min-h-60"
      >
        {taiex.length > 0 ? <IndexChart line={taiex} markers={taiexMarks} /> : <EmptyState title="讀取中…" />}
      </Panel>

      <Panel title="追蹤池近期的大波動" className="min-h-60" bodyClassName="overflow-auto">
        <ul className="text-xs">
          {recent.map((m) => (
            <li key={`${m.symbol}-${m.date}`} className="border-b border-line/60">
              <Link
                to="/explain/$symbol/$date"
                params={{ symbol: m.symbol, date: m.date }}
                className="grid grid-cols-[auto_minmax(0,5rem)_auto_1fr] items-center gap-2 px-3 py-1.5 hover:bg-hover"
              >
                <span className="num text-text-3">{m.date.slice(5)}</span>
                <span className="truncate text-text-1">{m.name}</span>
                <span className={`num w-12 text-right ${toneClass(m.ret)}`}>{formatPct(m.ret, 1)}</span>
                <span className="truncate text-2xs text-text-3">{m.top?.title ?? '未找到明確的對應消息'}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
