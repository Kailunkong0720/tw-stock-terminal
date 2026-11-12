import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { Group, Panel as RPanel, Separator } from 'react-resizable-panels'

import { KLineChart, type SubPane } from '../../charts/KLineChart'
import { VolumeProfile } from '../../charts/VolumeProfile'
import { EmptyState, Panel } from '../../design/Panel'
import { Segmented } from '../../design/Segmented'
import { useBacktest, useBars, useCalendar, useFlows, useForecast, useSecurities } from '../../lib/data'
import { toCandles, toFlowPoints } from '../../lib/series'
import { RANGES, type RangeKey, usePrefs } from '../../lib/store'
import { useMedia } from '../../lib/useMedia'
import { coneFromBacktest, coneFromForecast } from '../forecast/cones'
import { ModelPanel } from '../forecast/ModelPanel'
import { ReplayBar } from '../forecast/ReplayBar'
import { ActionsTable, BigMoves, FlowSummary, FlowTable } from './panels'
import { InfoBar } from './InfoBar'

const REPLAY_STEPS = 20

function Handle({ dir }: { dir: 'h' | 'v' }) {
  return (
    <Separator
      className={`group relative flex shrink-0 items-center justify-center ${dir === 'h' ? 'w-2' : 'h-2'}`}
    >
      <span
        className={`rounded-full bg-transparent transition-colors group-hover:bg-line-strong group-data-[separator=active]:bg-accent ${
          dir === 'h' ? 'h-8 w-0.5' : 'h-0.5 w-8'
        }`}
      />
    </Separator>
  )
}

/** 個股終端（PLAN.md 7.2）：資訊條 → K 線 + 中欄 + 右欄 → 下方明細。 */
export function StockPage() {
  const { symbol } = useParams({ from: '/stock/$symbol' })
  const navigate = useNavigate()
  const cal = useCalendar()
  const secs = useSecurities()
  const bars = useBars(symbol)
  const flows = useFlows(symbol)
  const adjusted = usePrefs((s) => s.adjusted)
  const setAdjusted = usePrefs((s) => s.setAdjusted)
  const range = usePrefs((s) => s.range)
  const setRange = usePrefs((s) => s.setRange)
  const subPane = usePrefs((s) => s.subPane)
  const setSubPane = usePrefs((s) => s.setSubPane)
  const pushRecent = usePrefs((s) => s.pushRecent)
  const watchlist = usePrefs((s) => s.watchlist)
  const [bottomTab, setBottomTab] = useState<'actions' | 'flows'>('actions')
  const wide = useMedia('(min-width: 1280px)')

  const sec = secs.data?.items.find((s) => s.symbol === symbol)
  const etf = sec?.kind === 'etf'
  const dates = cal.data?.dates
  const raw = useMemo(() => (bars.data && dates ? toCandles(bars.data, dates, false) : []), [bars.data, dates])
  const adj = useMemo(() => (bars.data && dates ? toCandles(bars.data, dates, true) : []), [bars.data, dates])
  const allCandles = adjusted ? adj : raw
  const points = useMemo(() => (flows.data && dates ? toFlowPoints(flows.data, dates) : []), [flows.data, dates])

  // ── Kronos：最新預測與回測重播 ──────────────────────────────────────
  const tracked = Boolean(sec?.tracked)
  const fc = useForecast(symbol, tracked)
  const bt = useBacktest(symbol, tracked)
  const showCone = usePrefs((s) => s.showCone)
  const setShowCone = usePrefs((s) => s.setShowCone)
  const [replay, setReplay] = useState(false)
  const [rIdx, setRIdx] = useState(0)
  const [reveal, setReveal] = useState(REPLAY_STEPS)
  const [playing, setPlaying] = useState(false)
  const btPoints = bt.data?.points ?? []

  useEffect(() => {
    setReplay(false)
    setPlaying(false)
  }, [symbol])
  useEffect(() => {
    setRIdx(Math.max(0, btPoints.length - 1))
    setReveal(REPLAY_STEPS)
  }, [btPoints.length])

  // 播放：實際走勢逐日疊上去，走完 20 天後換下一個基準日
  useEffect(() => {
    if (!replay || !playing) return
    const id = window.setTimeout(
      () => {
        if (reveal < REPLAY_STEPS) setReveal(reveal + 1)
        else if (rIdx < btPoints.length - 1) {
          setRIdx(rIdx + 1)
          setReveal(0)
        } else setPlaying(false)
      },
      reveal < REPLAY_STEPS ? 70 : 900,
    )
    return () => window.clearTimeout(id)
  }, [replay, playing, reveal, rIdx, btPoints.length])

  const point = replay ? btPoints[rIdx] : undefined
  const baseIdx = point && dates ? dates.indexOf(point.base_date) : -1
  const candles = useMemo(() => {
    if (!point || !dates || baseIdx < 0) return allCandles
    const cutoff = dates[Math.min(dates.length - 1, baseIdx + reveal)]!
    return allCandles.filter((c) => c.time <= cutoff)
  }, [allCandles, point, dates, baseIdx, reveal])
  const cone = useMemo(() => {
    if (point && dates) return coneFromBacktest(point, dates, adjusted)
    return showCone && fc.data ? coneFromForecast(fc.data) : null
  }, [point, dates, adjusted, showCone, fc.data])
  const replayWindow = useMemo(() => {
    if (!point || !dates || baseIdx < 0) return null
    return { from: dates[Math.max(0, baseIdx - 80)]!, to: dates[Math.min(dates.length - 1, baseIdx + REPLAY_STEPS + 2)]! }
  }, [point, dates, baseIdx])

  useEffect(() => {
    if (sec) pushRecent(sec.symbol)
  }, [sec, pushRecent])

  // 鍵盤：1–6 切換時間區間、A 切換還原、↑↓ 在自選股之間切換
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, [contenteditable="true"], [cmdk-root]') || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= RANGES.length) setRange(RANGES[n - 1]!.key)
      else if (e.key === 'a' || e.key === 'A') setAdjusted(!usePrefs.getState().adjusted)
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (watchlist.length === 0) return
        const i = watchlist.indexOf(symbol)
        const next = e.key === 'ArrowDown' ? (i + 1) % watchlist.length : (i - 1 + watchlist.length) % watchlist.length
        e.preventDefault()
        navigate({ to: '/stock/$symbol', params: { symbol: watchlist[next]! } })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [watchlist, symbol, navigate, setRange, setAdjusted])

  if (bars.isError) {
    return (
      <div className="p-2">
        <Panel title={symbol}>
          <EmptyState title="找不到這檔股票的資料" detail="代號可能有誤，或它不是 2020 年以來的上市股票或 ETF。按 Ctrl+K 搜尋。" />
        </Panel>
      </div>
    )
  }

  const chartActions = (
    <>
      <Segmented
        size="xs"
        label="副圖"
        value={subPane}
        onChange={(v) => setSubPane(v as SubPane)}
        options={[
          { value: 'volume', label: '成交量' },
          { value: 'foreign', label: '外資' },
          { value: 'foreignCum', label: '外資累計' },
        ]}
      />
      <span className="mx-1 h-4 w-px bg-line" />
      <Segmented
        size="xs"
        label="還原"
        value={adjusted ? 'adj' : 'raw'}
        onChange={(v) => setAdjusted(v === 'adj')}
        options={[
          { value: 'adj', label: '還原' },
          { value: 'raw', label: '原始' },
        ]}
      />
      <span className="mx-1 h-4 w-px bg-line" />
      <Segmented
        size="xs"
        label="時間區間"
        value={range}
        onChange={(v) => setRange(v as RangeKey)}
        options={RANGES.map((r) => ({ value: r.key, label: r.label }))}
      />
    </>
  )

  const loading = <EmptyState title="讀取中…" />
  const chart = (
    <Panel
      title={replay ? '回測重播' : 'K 線'}
      actions={chartActions}
      className="h-full"
      bodyClassName="flex flex-col"
    >
      {candles.length ? (
        <>
          <div className="min-h-0 flex-1">
            <KLineChart
              candles={candles}
              actions={bars.data?.actions ?? []}
              flows={points}
              subPane={subPane}
              range={range}
              adjusted={adjusted}
              etf={etf}
              cone={cone}
              window={replayWindow}
            />
          </div>
          {replay && btPoints.length > 0 && (
            <ReplayBar
              points={btPoints}
              idx={rIdx}
              onIdx={(i) => {
                setPlaying(false)
                setRIdx(i)
                setReveal(REPLAY_STEPS)
              }}
              playing={playing}
              onPlay={() => {
                if (playing) return setPlaying(false)
                if (rIdx >= btPoints.length - 1 && reveal >= REPLAY_STEPS) setRIdx(0)
                setReveal(0)
                setPlaying(true)
              }}
              onClose={() => {
                setPlaying(false)
                setReplay(false)
              }}
              horizon="20"
            />
          )}
        </>
      ) : (
        loading
      )}
    </Panel>
  )
  const profile = (
    <Panel title="價量分布" className="h-full">
      {candles.length ? <VolumeProfile candles={candles} etf={etf} adjusted={adjusted} /> : loading}
    </Panel>
  )
  const moves = (
    <Panel title="大波動日" className="h-full">
      {adj.length ? <BigMoves candles={adj} etf={etf} adjusted /> : loading}
    </Panel>
  )
  const flowPanel = (
    <Panel title="外資動向" className="h-full">
      <FlowSummary flows={flows.data} points={points} />
    </Panel>
  )
  const model = (
    <Panel title="模型觀點" className="h-full">
      <ModelPanel
        tracked={tracked}
        forecast={fc.data}
        loading={tracked && fc.isPending}
        showCone={showCone}
        onToggleCone={() => {
          setReplay(false)
          setShowCone(!showCone)
        }}
        replay={replay}
        onToggleReplay={() => {
          setPlaying(false)
          setReplay(!replay)
        }}
        hasBacktest={btPoints.length > 0}
      />
    </Panel>
  )
  const bottom = (
    <Panel
      title={
        <Segmented
          size="xs"
          label="明細"
          value={bottomTab}
          onChange={(v) => setBottomTab(v as 'actions' | 'flows')}
          options={[
            { value: 'actions', label: '除權息與分割' },
            { value: 'flows', label: '法人每日買賣超' },
          ]}
        />
      }
      className="h-full"
      bodyClassName="overflow-auto"
    >
      {bottomTab === 'actions' ? <ActionsTable actions={bars.data?.actions ?? []} /> : <FlowTable points={points} />}
    </Panel>
  )

  const info = (
    <Panel bodyClassName="h-14">
      <InfoBar sec={sec} raw={raw} adj={adj} />
    </Panel>
  )

  if (!wide) {
    return (
      <div className="flex flex-col gap-2 p-2">
        {info}
        <div className="h-[460px]">{chart}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="h-80">{profile}</div>
          <div className="h-80">{moves}</div>
        </div>
        {flowPanel}
        {model}
        <div className="h-80">{bottom}</div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      {info}
      <Group orientation="horizontal" className="min-h-0 flex-1">
        <RPanel defaultSize="64%" minSize="40%">
          <Group orientation="vertical">
            <RPanel defaultSize="70%" minSize="35%">
              {chart}
            </RPanel>
            <Handle dir="v" />
            <RPanel defaultSize="30%" minSize="15%">
              {bottom}
            </RPanel>
          </Group>
        </RPanel>
        <Handle dir="h" />
        <RPanel defaultSize="17%" minSize="12%">
          <Group orientation="vertical">
            <RPanel defaultSize="58%" minSize="25%">
              {profile}
            </RPanel>
            <Handle dir="v" />
            <RPanel defaultSize="42%" minSize="20%">
              {moves}
            </RPanel>
          </Group>
        </RPanel>
        <Handle dir="h" />
        <RPanel defaultSize="19%" minSize="14%">
          <div className="flex h-full flex-col gap-2">
            <div className="shrink-0">{flowPanel}</div>
            <div className="min-h-0 flex-1">{model}</div>
          </div>
        </RPanel>
      </Group>
    </div>
  )
}
