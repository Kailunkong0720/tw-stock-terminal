import { IconPlayerPauseFilled, IconPlayerPlayFilled, IconX } from '@tabler/icons-react'

import type { BacktestPoint } from '../../lib/contract/types'
import { formatPct } from '../../lib/format'

type Props = {
  points: BacktestPoint[]
  idx: number
  onIdx: (i: number) => void
  playing: boolean
  onPlay: () => void
  onClose: () => void
  horizon: '5' | '10' | '20'
}

/** 回測重播的控制列：拖動基準日、播放，並顯示那一次預測的結果。 */
export function ReplayBar({ points, idx, onIdx, playing, onPlay, onClose, horizon }: Props) {
  const p = points[idx]
  if (!p) return null
  const exp = p.exp[horizon]
  const act = p.actual[horizon]
  const right = exp != null && act != null && act !== 0 ? exp > 0 === act > 0 : null
  return (
    <div className="flex items-center gap-3 border-t border-line px-3 py-2 text-xs">
      <button
        type="button"
        onClick={onPlay}
        aria-label={playing ? '暫停' : '播放'}
        className="flex size-7 shrink-0 items-center justify-center rounded-control bg-accent text-canvas"
      >
        {playing ? <IconPlayerPauseFilled size={13} /> : <IconPlayerPlayFilled size={13} />}
      </button>
      <input
        type="range"
        min={0}
        max={points.length - 1}
        value={idx}
        onChange={(e) => onIdx(Number(e.target.value))}
        aria-label="回測基準日"
        className="min-w-24 flex-1 accent-[var(--accent)]"
      />
      <span className="num shrink-0 text-text-1">{p.base_date}</span>
      <span className="shrink-0 text-text-3">
        {horizon} 日 預期 <span className="num text-text-2">{formatPct(exp, 1)}</span>，實際{' '}
        <span className={`num ${act == null ? 'text-text-3' : act > 0 ? 'text-up' : act < 0 ? 'text-down' : 'text-flat'}`}>
          {formatPct(act, 1)}
        </span>
      </span>
      <span
        className={`w-14 shrink-0 text-right ${right == null ? 'text-text-3' : right ? 'text-accent' : 'text-warn'}`}
      >
        {right == null ? '—' : right ? '方向正確' : '方向錯誤'}
      </span>
      <button type="button" onClick={onClose} aria-label="結束重播" className="shrink-0 text-text-3 hover:text-text-1">
        <IconX size={14} />
      </button>
    </div>
  )
}
