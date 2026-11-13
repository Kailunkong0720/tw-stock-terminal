import { Link } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { EmptyState, Panel } from '../../design/Panel'
import { Provenance } from '../../design/Provenance'
import { Segmented } from '../../design/Segmented'
import type { RankingItem, TrackRecord } from '../../lib/contract/types'
import { useRanking } from '../../lib/data'
import { formatDate, formatPct, formatProb } from '../../lib/format'
import { labelTone, TrackLine } from './ModelPanel'

type H = 5 | 10 | 20
type SortKey = 'up_prob' | 'exp_ret' | 'hit'

function PoolCard({ t, ic }: { t: TrackRecord; ic: { mean: number | null; n_dates: number; positive_share: number | null } | undefined }) {
  const diff = t.hit_rate != null && t.baseline_rate != null ? t.hit_rate - t.baseline_rate : null
  return (
    <div className="space-y-2 rounded-control bg-raised p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-text-2">{t.horizon} 個交易日</span>
        <span className={`text-2xs ${t.has_edge ? 'text-accent' : 'text-warn'}`}>
          {t.n === 0 ? '尚無樣本' : t.has_edge ? '優於基準' : '無明顯優勢'}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <div className="text-2xs text-text-3">模型命中率</div>
          <div className="num text-base text-text-1">{formatProb(t.hit_rate, 1)}</div>
        </div>
        <div>
          <div className="text-2xs text-text-3">較佳基準</div>
          <div className="num text-base text-text-2">{formatProb(t.baseline_rate, 1)}</div>
        </div>
        <div>
          <div className="text-2xs text-text-3">差距</div>
          <div className={`num text-base ${diff == null ? 'text-text-3' : diff > 0 ? 'text-text-1' : 'text-warn'}`}>
            {diff == null ? '—' : `${diff > 0 ? '+' : diff < 0 ? '−' : ''}${Math.abs(diff * 100).toFixed(1)}`}
          </div>
        </div>
      </div>
      <div className="space-y-0.5 text-2xs text-text-3">
        <div>
          一律看多數方向 <span className="num text-text-2">{formatPct(t.always_rate, 1)}</span> · 延續 20 日趨勢{' '}
          <span className="num text-text-2">{formatPct(t.momentum_rate, 1)}</span> · 樣本 <span className="num">{t.n.toLocaleString()}</span>
        </div>
        {ic && ic.mean != null && (
          <div>
            Rank IC 平均 <span className="num text-text-2">{ic.mean.toFixed(3)}</span>（{ic.n_dates} 個基準日，
            <span className="num">{formatPct(ic.positive_share, 0)}</span> 為正）
          </div>
        )}
      </div>
    </div>
  )
}

/** 模型頁：追蹤池的訊號排行與模型整體回測表現（PLAN.md 9 Phase 3）。 */
export function ForecastPage() {
  const r = useRanking()
  const [h, setH] = useState<H>(20)
  const [sort, setSort] = useState<SortKey>('up_prob')
  const [onlyEdge, setOnlyEdge] = useState(false)

  const rows = useMemo(() => {
    const items = r.data?.items ?? []
    const get = (it: RankingItem) => ({
      s: it.signals.find((x) => x.horizon === h),
      t: it.track.find((x) => x.horizon === h),
    })
    return items
      .map((it) => ({ it, ...get(it) }))
      .filter((x) => x.s && (!onlyEdge || x.t?.has_edge))
      .sort((a, b) => {
        if (sort === 'hit') return (b.t?.hit_rate ?? -1) - (a.t?.hit_rate ?? -1)
        return (b.s![sort] as number) - (a.s![sort] as number)
      })
  }, [r.data, h, sort, onlyEdge])

  if (r.isPending) return <div className="p-2"><Panel title="模型"><EmptyState title="讀取中…" /></Panel></div>
  if (!r.data) {
    return (
      <div className="p-2">
        <Panel title="模型">
          <EmptyState title="尚無模型結果" detail="Kronos 的預測與回測完成後會出現在這裡。" />
        </Panel>
      </div>
    )
  }
  const d = r.data
  const icBy = new Map(d.rank_ic.map((x) => [x.horizon, x]))

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel
        title={`追蹤池訊號（${rows.length} 檔）`}
        className="min-h-96"
        bodyClassName="overflow-auto"
        actions={
          <>
            <Segmented
              size="xs"
              label="期間"
              value={String(h)}
              onChange={(v) => setH(Number(v) as H)}
              options={[
                { value: '5', label: '5 日' },
                { value: '10', label: '10 日' },
                { value: '20', label: '20 日' },
              ]}
            />
            <span className="mx-1 h-4 w-px bg-line" />
            <Segmented
              size="xs"
              label="排序"
              value={sort}
              onChange={(v) => setSort(v as SortKey)}
              options={[
                { value: 'up_prob', label: '上漲機率' },
                { value: 'exp_ret', label: '預期報酬' },
                { value: 'hit', label: '回測命中' },
              ]}
            />
            <button
              type="button"
              onClick={() => setOnlyEdge(!onlyEdge)}
              aria-pressed={onlyEdge}
              className={`ml-1 h-6 shrink-0 whitespace-nowrap rounded-control px-2 text-2xs ${
                onlyEdge ? 'bg-accent text-canvas' : 'bg-raised text-text-2'
              }`}
            >
              只看有優勢
            </button>
          </>
        }
      >
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-panel text-2xs text-text-3">
            <tr className="border-b border-line">
              <th className="px-3 py-1.5 text-left font-normal">代號</th>
              <th className="px-3 py-1.5 text-left font-normal">名稱</th>
              <th className="hidden px-3 py-1.5 text-left font-normal md:table-cell">產業</th>
              <th className="px-3 py-1.5 text-left font-normal">模型觀點</th>
              <th className="px-3 py-1.5 text-right font-normal">上漲機率</th>
              <th className="px-3 py-1.5 text-right font-normal">預期報酬</th>
              <th className="hidden px-3 py-1.5 text-right font-normal sm:table-cell">下檔 10%</th>
              <th className="hidden px-3 py-1.5 text-left font-normal lg:table-cell">回測</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ it, s, t }) => (
              <tr key={it.symbol} className="border-b border-line/60 hover:bg-hover">
                <td className="num px-3 py-1">
                  <Link to="/stock/$symbol" params={{ symbol: it.symbol }} className="text-text-1 hover:text-accent">
                    {it.symbol}
                  </Link>
                </td>
                <td className="whitespace-nowrap px-3 py-1 text-text-1">{it.name}</td>
                <td className="hidden px-3 py-1 text-text-3 md:table-cell">{it.industry}</td>
                <td className={`whitespace-nowrap px-3 py-1 ${labelTone(s!.label, Boolean(t?.has_edge))}`}>{s!.label}</td>
                <td className="num px-3 py-1 text-right text-text-1">{formatProb(s!.up_prob, 0)}</td>
                <td className={`num px-3 py-1 text-right ${s!.exp_ret > 0 ? 'text-up' : s!.exp_ret < 0 ? 'text-down' : 'text-flat'}`}>
                  {formatPct(s!.exp_ret, 1)}
                </td>
                <td className="num hidden px-3 py-1 text-right text-text-2 sm:table-cell">{formatPct(s!.p10_ret, 1)}</td>
                <td className="hidden whitespace-nowrap px-3 py-1 text-2xs lg:table-cell">
                  <TrackLine t={t} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div className="flex min-h-0 flex-col gap-2">
        <Panel title="模型整體表現（回測）" bodyClassName="space-y-2 p-3">
          {d.pool.map((t) => (
            <PoolCard key={t.horizon} t={t} ic={icBy.get(t.horizon)} />
          ))}
          <p className="text-2xs leading-relaxed text-text-3">
            {d.backtest_dates.length > 0 ? (
              <>
                回測期間 <span className="num">{formatDate(d.backtest_dates[0])}</span> 至{' '}
                <span className="num">{formatDate(d.backtest_dates[d.backtest_dates.length - 1])}</span>，共{' '}
                {d.backtest_dates.length} 個基準日。
              </>
            ) : (
              '回測尚未完成。'
            )}
            每個基準日只用當天以前的資料預測。「較佳基準」是兩種不需要模型的策略中較好的那一個；
            模型命中率要明顯高於它才算有優勢。
          </p>
        </Panel>
        <Panel title="怎麼讀" className="min-h-0 flex-1" bodyClassName="space-y-2 overflow-auto p-3 text-2xs leading-relaxed text-text-3">
          <p>
            {d.model}：開源的 K 線基礎模型，未針對台股微調。回看 {d.settings.lookback} 個交易日，產生 {d.settings.n_paths}{' '}
            條可能的未來走勢；上漲機率是這些路徑中期末收盤高於今天的比例，預期報酬是中位數。
          </p>
          <ul className="list-disc space-y-0.5 pl-4">
            {d.label_rules.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
          <p>沒有回測優勢的標的，標籤一律顯示為灰色。</p>
          <p className="text-text-2">此為統計模型的輸出，不構成投資建議。</p>
          <Provenance ids={['forecast', 'backtest']} className="border-t border-line pt-2" />
        </Panel>
      </div>
    </div>
  )
}
