import { Link } from '@tanstack/react-router'

import { EmptyState } from '../../design/Panel'
import type { Forecast, SignalOut, TrackRecord } from '../../lib/contract/types'
import { formatDate, formatPct } from '../../lib/format'

/** 標籤顏色：有回測優勢時用漲跌色；沒有優勢一律灰色（PLAN.md 5.2）。 */
export function labelTone(label: string, edge: boolean): string {
  if (!edge) return 'text-text-3'
  if (label.includes('多')) return 'text-up'
  if (label.includes('空')) return 'text-down'
  return 'text-text-2'
}

function ProbBar({ p }: { p: number }) {
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-raised" aria-hidden="true">
      <div className="h-full bg-up/70" style={{ width: `${p * 100}%` }} />
      <div className="h-full flex-1 bg-down/50" />
    </div>
  )
}

export function TrackLine({ t }: { t: TrackRecord | undefined }) {
  if (!t || t.n === 0 || t.hit_rate == null) return <span className="text-text-3">尚無回測樣本</span>
  return (
    <span className="text-text-3">
      回測命中 <span className="num text-text-2">{formatPct(t.hit_rate, 0)}</span>
      <span className="mx-1">·</span>基準 <span className="num">{formatPct(t.baseline_rate, 0)}</span>
      <span className="mx-1">·</span>樣本 <span className="num">{t.n}</span>
    </span>
  )
}

function SignalRow({ s, t }: { s: SignalOut; t: TrackRecord | undefined }) {
  const edge = Boolean(t?.has_edge)
  return (
    <div className="space-y-1.5 border-b border-line/70 px-3 py-2.5 last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-text-2">{s.horizon} 個交易日</span>
        <span className={`text-sm font-medium ${labelTone(s.label, edge)}`}>{s.label}</span>
      </div>
      <ProbBar p={s.up_prob} />
      <div className="grid grid-cols-3 gap-2 text-2xs">
        <div>
          <div className="text-text-3">上漲機率</div>
          <div className="num text-text-1">{formatPct(s.up_prob, 0)}</div>
        </div>
        <div>
          <div className="text-text-3">預期報酬</div>
          <div className={`num ${s.exp_ret > 0 ? 'text-up' : s.exp_ret < 0 ? 'text-down' : 'text-flat'}`}>
            {formatPct(s.exp_ret, 1)}
          </div>
        </div>
        <div>
          <div className="text-text-3">下檔 10%</div>
          <div className="num text-text-2">{formatPct(s.p10_ret, 1)}</div>
        </div>
      </div>
      <div className="text-2xs">
        <TrackLine t={t} />
        {t && t.n > 0 && !edge && <span className="ml-1.5 text-warn">無明顯優勢</span>}
      </div>
    </div>
  )
}

type Props = {
  tracked: boolean
  forecast: Forecast | undefined
  loading: boolean
  showCone: boolean
  onToggleCone: () => void
  replay: boolean
  onToggleReplay: () => void
  hasBacktest: boolean
}

export function ModelPanel({ tracked, forecast, loading, showCone, onToggleCone, replay, onToggleReplay, hasBacktest }: Props) {
  if (!tracked) {
    return (
      <EmptyState
        title="此標的不在預測範圍"
        detail={
          <>
            模型只對追蹤池（市值前 150 大的上市股票與 4 檔主要 ETF）做預測與回測。
            <Link to="/forecast" className="ml-1 text-accent hover:underline">
              看追蹤池
            </Link>
          </>
        }
      />
    )
  }
  if (loading) return <EmptyState title="讀取中…" />
  if (!forecast) return <EmptyState title="這檔還沒有預測結果" detail="模型會在每次更新資料後重算。" />

  const byH = new Map(forecast.track.map((t) => [t.horizon, t]))
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 px-3 pb-1 pt-2 text-2xs text-text-3">
        <span>
          {forecast.model} · 基準日 <span className="num text-text-2">{formatDate(forecast.base_date)}</span>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {forecast.signals.map((s) => (
          <SignalRow key={s.horizon} s={s} t={byH.get(s.horizon)} />
        ))}
      </div>
      <div className="flex gap-1.5 border-t border-line px-3 py-2">
        <button
          type="button"
          onClick={onToggleCone}
          aria-pressed={showCone}
          className={`h-7 flex-1 rounded-control text-xs transition-colors ${
            showCone ? 'bg-accent text-canvas' : 'bg-raised text-text-2 hover:text-text-1'
          }`}
        >
          預測錐
        </button>
        <button
          type="button"
          onClick={onToggleReplay}
          disabled={!hasBacktest}
          aria-pressed={replay}
          className={`h-7 flex-1 rounded-control text-xs transition-colors disabled:opacity-40 ${
            replay ? 'bg-accent text-canvas' : 'bg-raised text-text-2 hover:text-text-1'
          }`}
        >
          回測重播
        </button>
      </div>
      <p className="border-t border-line px-3 py-1.5 text-2xs leading-snug text-text-3">
        此為統計模型的輸出，不構成投資建議。
      </p>
    </div>
  )
}
