import {
  IconPlayerPauseFilled,
  IconPlayerPlayFilled,
  IconPlayerTrackNextFilled,
  IconPlayerTrackPrevFilled,
} from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'

import { readTheme } from '../../charts/theme'
import { EmptyState, Panel } from '../../design/Panel'
import { Segmented } from '../../design/Segmented'
import { GlobeCanvas, type GlobeRing } from '../../globe/GlobeCanvas'
import { useBars, useCalendar, useGlobeOvernight, useGlobeSupply } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { useUpDown } from '../../lib/prefs'
import { toCandles } from '../../lib/series'
import { OVERNIGHT_HOME, OvernightSide, type OvernightModel, type PickedStock, useOvernight } from './overnight'
import { SupplySide, useSupply } from './supply'

type Mode = 'overnight' | 'supply'
const MODE_KEY = 'globe-mode'
const PICK_KEY = 'globe-stock'
const NO_RINGS: GlobeRing[] = []

function readMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'supply' ? 'supply' : 'overnight'
  } catch {
    return 'overnight'
  }
}

function Timeline({ m, dates, start }: { m: OvernightModel; dates: string[]; start: number }) {
  if (!m.range) return null
  const { lo, hi } = m.range
  const pct = (k: number) => `${((k - lo) / Math.max(1, hi - lo)) * 100}%`
  return (
    <div className="absolute inset-x-2 bottom-2 rounded-control border border-line bg-panel/90 px-3 py-2 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2.5 sm:flex-nowrap">
        <button
          type="button"
          onClick={() => m.step(-1)}
          aria-label="前一個交易日"
          className="flex size-6 items-center justify-center rounded-control bg-raised text-text-2 hover:text-text-1"
        >
          <IconPlayerTrackPrevFilled size={11} />
        </button>
        <button
          type="button"
          onClick={m.togglePlay}
          aria-label={m.playing ? '暫停' : '播放'}
          className="flex size-6 items-center justify-center rounded-control bg-accent text-canvas"
        >
          {m.playing ? <IconPlayerPauseFilled size={12} /> : <IconPlayerPlayFilled size={12} />}
        </button>
        <button
          type="button"
          onClick={() => m.step(1)}
          aria-label="後一個交易日"
          className="flex size-6 items-center justify-center rounded-control bg-raised text-text-2 hover:text-text-1"
        >
          <IconPlayerTrackNextFilled size={11} />
        </button>
        <span className="num w-[6.5rem] shrink-0 grow text-xs text-text-1 sm:grow-0">{formatDate(dates[start + m.i])}</span>
        <div className="relative order-last min-w-0 basis-full sm:order-none sm:basis-auto sm:flex-1">
          <div className="pointer-events-none absolute inset-x-0 -top-1.5 h-1.5" aria-hidden="true">
            {m.ticks.map((tk) => (
              <span
                key={tk.i}
                className={`absolute top-0 h-1.5 w-px ${tk.v > 0 ? 'bg-up' : 'bg-down'}`}
                style={{ left: pct(tk.i) }}
              />
            ))}
          </div>
          <input
            type="range"
            min={lo}
            max={hi}
            value={m.i}
            onChange={(e) => {
              m.setPos(Number(e.target.value))
            }}
            aria-label="日期"
            className="w-full accent-[var(--accent)]"
          />
        </div>
        <Segmented
          size="xs"
          label="播放速度"
          value={m.fast ? 'fast' : 'slow'}
          onChange={(v) => m.setFast(v === 'fast')}
          options={[
            { value: 'slow', label: '1×' },
            { value: 'fast', label: '4×' },
          ]}
        />
      </div>
      <p className="mt-1 hidden text-2xs text-text-3 sm:block">
        刻度：費半前一晚漲跌超過 3% 的日子。弧線粗細與流速依變動大小（以各序列自身的標準差衡量）。←　→ 逐日，空白鍵播放。
      </p>
    </div>
  )
}

/** 全球脈動：隔夜傳導（美股前一晚 → 台股當天）與全球供應鏈（PLAN.md Phase 6）。 */
export function GlobePage() {
  const [mode, setModeState] = useState<Mode>(readMode)
  const setMode = (v: Mode) => {
    setModeState(v)
    try {
      localStorage.setItem(MODE_KEY, v)
    } catch {
      // 無痕模式等情況存不了，不影響使用
    }
  }
  const ud = useUpDown()
  const theme = useMemo(() => readTheme(), [ud])
  const on = useGlobeOvernight()
  const sp = useGlobeSupply()
  const cal = useCalendar()
  // 隔夜傳導要看的股票（預設台積電）：弧線落在它的所在地
  const [pick, setPickState] = useState<string>(() => {
    try {
      return localStorage.getItem(PICK_KEY) || '2330'
    } catch {
      return '2330'
    }
  })
  const setPick = (s: string) => {
    setPickState(s)
    try {
      localStorage.setItem(PICK_KEY, s)
    } catch {
      // 無痕模式等情況存不了，不影響使用
    }
  }
  const bars = useBars(pick)
  const options = useMemo(
    () =>
      (sp.data?.places ?? [])
        .filter((p) => p.type === 'company' && p.tracked && p.symbol)
        .map((p) => ({ symbol: p.symbol!, name: p.name }))
        .sort((a, b) => a.symbol.localeCompare(b.symbol)),
    [sp.data],
  )
  const stock = useMemo<PickedStock | null>(() => {
    const place = sp.data?.places.find((p) => p.id === `company:${pick}`)
    const dates = cal.data?.dates
    if (!place || !bars.data || !dates || !on.data) return null
    // 還原後的日報酬，對齊日曆（前一個交易日沒有成交就留空）
    const close = new Map(toCandles(bars.data, dates, true).map((c) => [c.time, c.close]))
    const ret = on.data.taiex.map((_, k) => {
      const a = close.get(dates[on.data!.start + k - 1] ?? '')
      const b = close.get(dates[on.data!.start + k] ?? '')
      return a && b ? b / a - 1 : null
    })
    return { symbol: pick, name: place.name, lat: place.lat, lng: place.lng, place: place.place, ret }
  }, [sp.data, pick, bars.data, cal.data, on.data])
  const night = useOvernight(on.data, cal.data?.dates, theme, stock)
  const supply = useSupply(sp.data, theme)

  // 鍵盤：← → 逐日、空白鍵播放（只在隔夜傳導模式）
  useEffect(() => {
    if (mode !== 'overnight') return
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key === 'ArrowLeft') night.step(-1)
      else if (e.key === 'ArrowRight') night.step(1)
      else if (e.key === ' ') {
        e.preventDefault()
        night.togglePlay()
      } else return
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mode, night])

  const loading = mode === 'overnight' ? on.isPending || cal.isPending : sp.isPending
  const failed = mode === 'overnight' ? on.isError : sp.isError
  const layers = mode === 'overnight' ? night.layers : { ...supply.layers, rings: NO_RINGS }
  const view = mode === 'overnight' ? OVERNIGHT_HOME : supply.view

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel
        title="全球脈動"
        actions={
          <Segmented
            size="xs"
            label="模式"
            value={mode}
            onChange={(v) => setMode(v as Mode)}
            options={[
              { value: 'overnight', label: '隔夜傳導' },
              { value: 'supply', label: '全球供應鏈' },
            ]}
          />
        }
        className="min-h-[460px] sm:min-h-[560px]"
        bodyClassName="relative overflow-hidden"
      >
        {failed ? (
          <EmptyState title="資料讀取失敗" detail="請重新整理頁面；若持續發生，可能是這份資料尚未發布。" />
        ) : loading ? (
          <EmptyState title="讀取中…" />
        ) : (
          <>
            <GlobeCanvas
              arcs={layers.arcs}
              points={layers.points}
              rings={layers.rings}
              tags={layers.tags}
              view={view}
              onPointClick={(id) => {
                if (mode === 'supply') supply.select(id)
              }}
            />
            {mode === 'overnight' && on.data && cal.data && <Timeline m={night} dates={cal.data.dates} start={on.data.start} />}
            {mode === 'supply' && (
              <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-control bg-panel/80 px-2 py-1 text-2xs text-text-3">
                <span className="flex items-center gap-1">
                  <span className="inline-block size-2 rounded-full bg-series-1" />
                  海外公司
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block size-2 rounded-full bg-warn" />
                  機構
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block size-2 rounded-full bg-series-3" />
                  市場指標
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block size-1.5 rounded-full bg-text-2" />
                  台股公司
                </span>
              </div>
            )}
          </>
        )}
      </Panel>

      <div className="flex min-h-0 flex-col gap-2">
        {mode === 'overnight' ? (
          on.data && cal.data ? (
            <OvernightSide data={on.data} m={night} dates={cal.data.dates} stock={stock} options={options} onPick={setPick} />
          ) : (
            <Panel title="隔夜傳導" bodyClassName="p-3">
              <EmptyState title={on.isError ? '資料讀取失敗' : '讀取中…'} />
            </Panel>
          )
        ) : sp.data ? (
          <SupplySide data={sp.data} m={supply} />
        ) : (
          <Panel title="全球供應鏈" bodyClassName="p-3">
            <EmptyState title={sp.isError ? '資料讀取失敗' : '讀取中…'} />
          </Panel>
        )}
      </div>
    </div>
  )
}
