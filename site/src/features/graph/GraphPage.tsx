import { IconPlayerPauseFilled, IconPlayerPlayFilled } from '@tabler/icons-react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'

import { EmptyState, Panel } from '../../design/Panel'
import { Provenance } from '../../design/Provenance'
import { Segmented } from '../../design/Segmented'
import { GraphCanvas } from '../../graph/GraphCanvas'
import type { GraphEgo, GraphNode } from '../../lib/contract/types'
import { useEgo, usePropagate, useSecurities } from '../../lib/data'
import { formatPct } from '../../lib/format'

const TYPE_NAME: Record<string, string> = {
  company: '台股公司',
  industry: '產業',
  concept: '題材',
  global_company: '海外公司',
  organization: '機構',
  country: '國家',
  indicator: '市場指標',
  event: '事件',
  move: '異常波動',
}
const LEGEND: { type: string; label: string; shape: string }[] = [
  { type: 'company', label: '台股公司', shape: 'rounded-full bg-text-1' },
  { type: 'industry', label: '產業', shape: 'bg-series-2' },
  { type: 'concept', label: '題材', shape: 'rotate-45 bg-series-3' },
  { type: 'global_company', label: '海外公司／機構', shape: 'rounded-full border border-series-1' },
  { type: 'indicator', label: '市場指標', shape: 'bg-warn [clip-path:polygon(50%_0,100%_100%,0_100%)]' },
  { type: 'event', label: '事件', shape: 'rounded-full bg-text-2' },
  { type: 'move', label: '異常波動', shape: 'rounded-full bg-up' },
]

function filterByYear(ego: GraphEgo, year: string) {
  if (year === 'all') return ego
  const keepDyn = new Set(
    ego.nodes
      .filter((n) => (n.type === 'move' || n.type === 'event') && String(n.attrs.date ?? '').startsWith(year))
      .map((n) => n.id),
  )
  const nodes = ego.nodes.filter((n) => (n.type !== 'move' && n.type !== 'event') || keepDyn.has(n.id))
  const ids = new Set(nodes.map((n) => n.id))
  return {
    ...ego,
    nodes,
    links: ego.links.filter((l) => ids.has(l.source) && ids.has(l.target)),
    paths: ego.paths.filter((p) => ids.has(p.move)),
  }
}

function PathText({ ego, nodes }: { ego: GraphEgo; nodes: string[] }) {
  const by = new Map(ego.nodes.map((n) => [n.id, n]))
  const rel = (a: string, b: string) =>
    ego.links.find((l) => (l.source === a && l.target === b) || (l.source === b && l.target === a))?.rel_name ?? '→'
  return (
    <ol className="space-y-1">
      {nodes.map((id, i) => {
        const n = by.get(id)
        return (
          <li key={id} className="text-xs">
            {i > 0 && <div className="pl-3 text-2xs text-text-3">↓ {rel(nodes[i - 1]!, id)}</div>}
            <div className="flex items-baseline gap-2">
              <span className="w-14 shrink-0 text-2xs text-text-3">{TYPE_NAME[n?.type ?? ''] ?? ''}</span>
              <span className="text-text-1">{n?.type === 'event' ? String(n.attrs.title ?? n.name) : n?.name}</span>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function Propagation({ node }: { node: GraphNode }) {
  const p = usePropagate(['indicator', 'global_company', 'concept', 'organization'].includes(node.type) ? node.id : null)
  if (!p.data) return null
  return (
    <div className="space-y-1.5">
      <h4 className="text-2xs text-text-3">傳導預覽：{node.name}變動時，可能受影響的台股（{p.data.items.length}）</h4>
      <ul className="max-h-72 overflow-auto text-xs">
        {p.data.items.map((it) => (
          <li key={it.symbol} className="grid grid-cols-[auto_1fr_auto] gap-2 border-b border-line/60 py-1">
            <Link to="/graph/$symbol" params={{ symbol: it.symbol }} className="num text-text-1 hover:text-accent">
              {it.symbol}
            </Link>
            <span className="truncate text-text-2" title={it.via}>
              {it.name}
              <span className="ml-1.5 text-2xs text-text-3">{it.via}</span>
            </span>
            <span className="num text-2xs text-text-3">{it.rho == null ? '' : `ρ ${it.rho.toFixed(2)}`}</span>
          </li>
        ))}
      </ul>
      <p className="text-2xs text-text-3">ρ 是近 500 個交易日的實測相關係數；沒有 ρ 的是依關係推得，強弱未經資料驗證。</p>
    </div>
  )
}

/** /graph/:symbol：知識圖譜（PLAN.md 6.3、7.5）。 */
export function GraphPage() {
  const params = useParams({ strict: false }) as { symbol?: string }
  const symbol = params.symbol ?? '2330'
  const navigate = useNavigate()
  const ego = useEgo(symbol)
  const secs = useSecurities()
  const [year, setYear] = useState('all')
  const [playing, setPlaying] = useState(false)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [pathMove, setPathMove] = useState<string | null>(null)

  useEffect(() => {
    setSelected(null)
    setPathMove(null)
  }, [symbol])

  const years = useMemo(() => {
    const ys = new Set((ego.data?.nodes ?? []).filter((n) => n.type === 'move').map((n) => String(n.attrs.date).slice(0, 4)))
    return [...ys].sort()
  }, [ego.data])
  const view = useMemo(() => (ego.data ? filterByYear(ego.data, year) : null), [ego.data, year])
  const path = pathMove ? (view?.paths.find((p) => p.move === pathMove)?.nodes ?? null) : null

  // 播放：依年份推進，圖上的事件與波動隨之出現與淡去
  useEffect(() => {
    if (!playing || years.length === 0) return
    const id = window.setTimeout(() => {
      const i = years.indexOf(year)
      if (i < years.length - 1) setYear(years[i + 1]!)
      else setPlaying(false)
    }, 1800)
    return () => window.clearTimeout(id)
  }, [playing, year, years])

  const trackedList = (secs.data?.items ?? []).filter((s) => s.tracked)
  const centerName = trackedList.find((s) => s.symbol === symbol)?.name ?? symbol
  const movesWithPath = (view?.paths ?? [])
    .map((p) => ({ p, n: view!.nodes.find((n) => n.id === p.move)! }))
    .filter((x) => x.n)
    .sort((a, b) => String(b.n.attrs.date).localeCompare(String(a.n.attrs.date)))

  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_360px]">
      <Panel
        title={
          <span className="flex items-center gap-2">
            知識圖譜
            <select
              value={symbol}
              onChange={(e) => navigate({ to: '/graph/$symbol', params: { symbol: e.target.value } })}
              className="num rounded-control border border-line bg-raised px-1.5 py-0.5 text-xs text-text-1"
              aria-label="中心股票"
            >
              {trackedList.map((s) => (
                <option key={s.symbol} value={s.symbol}>
                  {s.symbol} {s.name}
                </option>
              ))}
            </select>
          </span>
        }
        actions={
          <>
            <button
              type="button"
              onClick={() => {
                if (!playing && years.length) setYear(years[0]!)
                setPlaying(!playing)
              }}
              aria-label={playing ? '暫停' : '依年份播放'}
              className="flex size-6 shrink-0 items-center justify-center rounded-control bg-raised text-text-2 hover:text-text-1"
            >
              {playing ? <IconPlayerPauseFilled size={12} /> : <IconPlayerPlayFilled size={12} />}
            </button>
            <Segmented
              size="xs"
              label="年份"
              value={year}
              onChange={(v) => {
                setPlaying(false)
                setYear(v)
              }}
              options={[{ value: 'all', label: '全部' }, ...years.map((y) => ({ value: y, label: y }))]}
            />
          </>
        }
        className="min-h-[560px]"
        bodyClassName="relative"
      >
        {ego.isPending ? (
          <EmptyState title="讀取中…" />
        ) : !view ? (
          <EmptyState title="這檔沒有知識圖譜" detail="圖譜只涵蓋追蹤池。" />
        ) : (
          <>
            <GraphCanvas
              nodes={view.nodes}
              links={view.links}
              center={view.center}
              path={path}
              selected={selected?.id ?? null}
              onSelect={(n) => {
                setSelected(n)
                if (n.type === 'move') setPathMove(n.id)
                else if (n.type === 'company' && n.id !== view.center) navigate({ to: '/graph/$symbol', params: { symbol: String(n.attrs.symbol) } })
              }}
            />
            <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-control bg-panel/80 px-2 py-1 text-2xs text-text-3">
              {LEGEND.map((l) => (
                <span key={l.type} className="flex items-center gap-1">
                  <span className={`inline-block size-2 ${l.shape}`} />
                  {l.label}
                </span>
              ))}
              <span>實線：人工整理　點線：資料算出</span>
            </div>
          </>
        )}
      </Panel>

      <div className="flex min-h-0 flex-col gap-2">
        <Panel title={pathMove ? '解釋路徑' : selected ? TYPE_NAME[selected.type] ?? '節點' : `${centerName} 的異常波動`} className="min-h-0 flex-1" bodyClassName="overflow-auto p-3">
          {pathMove && path && view ? (
            <div className="space-y-3">
              <PathText ego={view} nodes={path} />
              <div className="flex gap-3 text-2xs">
                <Link
                  to="/explain/$symbol/$date"
                  params={{ symbol, date: pathMove.split(':')[2]! }}
                  className="text-accent hover:underline"
                >
                  完整漲跌解析
                </Link>
                <button type="button" onClick={() => setPathMove(null)} className="text-text-3 hover:text-text-1">
                  返回清單
                </button>
              </div>
              <p className="text-2xs leading-relaxed text-text-3">路徑表示「可能相關」，時間相近不代表因果。</p>
            </div>
          ) : selected && selected.type !== 'move' ? (
            <div className="space-y-3 text-xs">
              <div>
                <div className="text-sm text-text-1">{selected.type === 'event' ? String(selected.attrs.title) : selected.name}</div>
                {selected.attrs.aliases ? <div className="text-2xs text-text-3">{String(selected.attrs.aliases)}</div> : null}
                {selected.type === 'event' && (
                  <div className="mt-1 text-2xs text-text-3">
                    {String(selected.attrs.date)} · {String(selected.attrs.type_name)}
                    {selected.attrs.url ? (
                      <a href={String(selected.attrs.url)} target="_blank" rel="noreferrer" className="ml-2 text-accent hover:underline">
                        來源
                      </a>
                    ) : null}
                  </div>
                )}
                {selected.type === 'company' && (
                  <Link to="/stock/$symbol" params={{ symbol: String(selected.attrs.symbol) }} className="mt-1 inline-block text-2xs text-accent hover:underline">
                    開啟個股終端
                  </Link>
                )}
              </div>
              <Propagation node={selected} />
              <button type="button" onClick={() => setSelected(null)} className="text-2xs text-text-3 hover:text-text-1">
                返回清單
              </button>
            </div>
          ) : movesWithPath.length === 0 ? (
            <EmptyState title="這段期間沒有找到可能相關事件的異常波動" />
          ) : (
            <ul className="text-xs">
              {movesWithPath.map(({ p, n }) => (
                <li key={p.move}>
                  <button
                    type="button"
                    onClick={() => setPathMove(p.move)}
                    className="grid w-full grid-cols-[auto_auto_1fr] items-center gap-2 border-b border-line/60 py-1.5 text-left hover:bg-hover"
                  >
                    <span className="num text-text-2">{String(n.attrs.date)}</span>
                    <span className={`num w-12 text-right ${Number(n.attrs.ret) >= 0 ? 'text-up' : 'text-down'}`}>
                      {formatPct(Number(n.attrs.ret), 1)}
                    </span>
                    <span className="truncate text-text-3">
                      {view?.nodes.find((x) => x.id === p.nodes[p.nodes.length - 2])?.name ?? ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="怎麼讀" bodyClassName="space-y-1 p-3 text-2xs leading-relaxed text-text-3">
          <p>點選右側清單或圖上的異常波動，解釋路徑上的連線會出現流動的粒子，其餘節點淡出。</p>
          <p>點選指標、海外公司或題材，可看「傳導預覽」：它變動時可能受影響的台股。點選其他台股公司會切換中心。</p>
          <p>關係來源：人工整理（實線）、由股價資料算出的連動（點線）。新聞抽取的關係尚未加入。</p>
          <Provenance ids={['graph', 'attribution']} className="border-t border-line pt-2" />
        </Panel>
      </div>
    </div>
  )
}
