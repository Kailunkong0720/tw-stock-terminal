import { Link } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { alpha, type ChartTheme } from '../../charts/theme'
import { EmptyState, Panel } from '../../design/Panel'
import type { GlobeArc, GlobePoint, GlobeTag, GlobeView } from '../../globe/GlobeCanvas'
import type { GlobeLink, GlobePlace, GlobeSupply } from '../../lib/contract/types'

export const SUPPLY_HOME: GlobeView = { lat: 40, lng: -178, altitude: 2.0 }
const TAIWAN_VIEW: GlobeView = { lat: 23.9, lng: 120.95, altitude: 0.3 }
const TW = { lat: 23.9, lng: 121 }
const TYPE_NAME: Record<string, string> = {
  global_company: '海外公司',
  organization: '機構',
  indicator: '市場指標',
  company: '台股公司',
}
const REGIONS = ['美國', '日本', '韓國', '荷蘭', '台灣', '其他']

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
const region = (p: GlobePlace) => REGIONS.find((r) => p.place.startsWith(r) || (r === '台灣' && p.place.startsWith('台北'))) ?? '其他'

/** 兩點之間的大圓中點與角距離（度）。 */
function midpoint(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const r = Math.PI / 180
  const [p1, l1, p2, l2] = [a.lat * r, a.lng * r, b.lat * r, b.lng * r]
  const bx = Math.cos(p2) * Math.cos(l2 - l1)
  const by = Math.cos(p2) * Math.sin(l2 - l1)
  const lat = Math.atan2(Math.sin(p1) + Math.sin(p2), Math.sqrt((Math.cos(p1) + bx) ** 2 + by ** 2))
  const lng = l1 + Math.atan2(by, Math.cos(p1) + bx)
  const d = Math.acos(Math.min(1, Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(l2 - l1)))
  return { lat: lat / r, lng: (((lng / r + 540) % 360) - 180), deg: d / r }
}

function relText(l: GlobeLink, by: Map<string, GlobePlace>) {
  const a = by.get(l.source)?.name ?? l.source
  const b = by.get(l.target)?.name ?? l.target
  if (l.origin === 'data') return `${a} 與 ${b} 連動（相關係數 ${l.rho?.toFixed(2) ?? '—'}）`
  return `${a} ${l.rel_name} ${b}${l.note ? `：${l.note}` : ''}`
}

export function useSupply(data: GlobeSupply | undefined, t: ChartTheme) {
  const [sel, setSel] = useState<string | null>(null)
  const [showData, setShowData] = useState(false)
  const [view, setView] = useState<GlobeView>(SUPPLY_HOME)
  const by = useMemo(() => new Map((data?.places ?? []).map((p) => [p.id, p])), [data])
  const degree = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of data?.links ?? []) {
      m.set(l.source, (m.get(l.source) ?? 0) + 1)
      m.set(l.target, (m.get(l.target) ?? 0) + 1)
    }
    return m
  }, [data])
  const selected = sel ? by.get(sel) : undefined

  const select = (id: string | null) => {
    setSel(id)
    const p = id ? by.get(id) : undefined
    if (!p) return setView(SUPPLY_HOME)
    if (p.type === 'company') return setView({ lat: p.lat + 6, lng: p.lng + 25, altitude: 1.9 })
    const m = midpoint(p, TW)
    setView({ lat: m.lat, lng: m.lng, altitude: Math.min(2.8, Math.max(1.3, 0.9 + (m.deg / 90) * 1.5)) })
  }

  const layers = useMemo(() => {
    if (!data) return { arcs: [] as GlobeArc[], points: [] as GlobePoint[], tags: [] as GlobeTag[] }
    const touches = (l: GlobeLink) => sel != null && (l.source === sel || l.target === sel)
    const links = data.links.filter((l) => l.origin === 'seed' || showData || touches(l))
    const arcs: GlobeArc[] = links.flatMap((l) => {
      const isData = l.origin === 'data'
      // 實測連動：指標 → 公司（影響方向）；人工整理的關係：依關係方向（供應方 → 客戶）
      const a = by.get(isData ? l.target : l.source)
      const b = by.get(isData ? l.source : l.target)
      if (!a || !b) return []
      const on = sel == null || touches(l)
      const base = isData ? t.s3 : l.rel === 'competes' ? t.warn : l.rel === 'partners' ? t.s2 : t.s1
      const c = sel != null && on && !isData ? t.accent : base
      const strength = isData ? Math.abs(l.rho ?? 0.3) : 1
      return [
        {
          id: `${l.source}|${l.target}|${l.rel}`,
          startLat: a.lat,
          startLng: a.lng,
          endLat: b.lat,
          endLng: b.lng,
          color: on ? [alpha(c, isData ? 0.15 : 0.25), alpha(c, isData ? 0.35 + strength : 1)] : alpha(base, 0.07),
          stroke: isData ? 0.08 + strength * 0.22 : on && sel ? 0.5 : 0.3,
          dashTime: isData || l.rel === 'competes' ? 0 : 2600,
          pattern: isData ? 'dots' : l.rel === 'competes' ? 'solid' : 'flow',
          altitude: null,
          label: esc(relText(l, by)),
        } satisfies GlobeArc,
      ]
    })
    const points: GlobePoint[] = data.places.flatMap((p) => {
      const isCo = p.type === 'company'
      if (!isCo && !degree.get(p.id)) return []
      const isSel = p.id === sel
      const linked = sel != null && links.some((l) => touches(l) && (l.source === p.id || l.target === p.id))
      const color = isSel
        ? t.accent
        : isCo
          ? alpha(t.text2, linked ? 1 : sel ? 0.35 : 0.75)
          : p.type === 'organization'
            ? t.warn
            : p.type === 'indicator'
              ? t.s3
              : t.s1
      const label = isCo
        ? `${esc(p.symbol ?? '')} ${esc(p.name)}<br><span style="color:var(--text-3)">${esc(p.place)}${p.industry ? ` · ${esc(p.industry)}` : ''}</span>`
        : `${esc(p.name)}<br><span style="color:var(--text-3)">${esc(p.place)}</span>`
      return [{ id: p.id, lat: p.lat, lng: p.lng, color, radius: isCo ? (isSel ? 0.14 : linked ? 0.1 : 0.06) : isSel ? 0.5 : 0.34, label }]
    })
    // 海外節點的文字標籤：距離相近的合併成一個
    const globals = data.places.filter((p) => p.type !== 'company' && degree.get(p.id))
    const clusters: GlobePlace[][] = []
    for (const p of globals) {
      const c = clusters.find((g) => Math.hypot(g[0]!.lat - p.lat, (g[0]!.lng - p.lng) * Math.cos((p.lat * Math.PI) / 180)) < 2.4)
      if (c) c.push(p)
      else clusters.push([p])
    }
    const tags: GlobeTag[] = clusters.map((g) => {
      const names = g.map((p) => p.name)
      const text = names.length <= 3 ? names.join('、') : `${names.slice(0, 2).join('、')} 等 ${names.length} 家`
      const hit = g.some((p) => p.id === sel)
      return {
        id: g[0]!.id,
        lat: g[0]!.lat,
        lng: g[0]!.lng,
        html: `<span${hit ? ' style="color:var(--accent)"' : ''}>${esc(text)}</span>`,
        onClick: () => {
          if (g.length === 1) select(g[0]!.id)
          else setView({ lat: g[0]!.lat, lng: g[0]!.lng, altitude: 0.55 })
        },
      }
    })
    if (selected?.type === 'company') {
      tags.push({ id: selected.id, lat: selected.lat, lng: selected.lng, html: `<span style="color:var(--accent)">${esc(selected.name)}</span>` })
    }
    return { arcs, points, tags }
    // select 只用到 setter 與 by，不必列入依賴
  }, [data, by, degree, sel, showData, t, selected])

  return { sel, select, selected, showData, setShowData, view, setView, layers, by, degree }
}

export type SupplyModel = ReturnType<typeof useSupply>

export function SupplySide({ data, m }: { data: GlobeSupply; m: SupplyModel }) {
  const companies = useMemo(
    () => data.places.filter((p) => p.type === 'company' && p.tracked).sort((a, b) => (a.symbol ?? '').localeCompare(b.symbol ?? '')),
    [data],
  )
  const globals = data.places.filter((p) => p.type !== 'company' && m.degree.get(p.id))
  const s = m.selected
  const own = s
    ? data.links
        .filter((l) => l.source === s.id || l.target === s.id)
        .sort((a, b) => (a.origin === b.origin ? Math.abs(b.rho ?? 0) - Math.abs(a.rho ?? 0) : a.origin === 'seed' ? -1 : 1))
    : []

  return (
    <>
      <Panel title="全球供應鏈" bodyClassName="space-y-3 p-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={s?.type === 'company' ? s.id : ''}
            onChange={(e) => m.select(e.target.value || null)}
            className="num min-w-0 flex-1 rounded-control border border-line bg-raised px-1.5 py-1 text-xs text-text-1"
            aria-label="選擇台股公司"
          >
            <option value="">選擇台股公司…</option>
            {companies.map((p) => (
              <option key={p.id} value={p.id}>
                {p.symbol} {p.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => m.setView(TAIWAN_VIEW)} className="rounded-control bg-raised px-2 py-1 text-text-2 hover:text-text-1">
            放大台灣
          </button>
          <button type="button" onClick={() => m.select(null)} className="rounded-control bg-raised px-2 py-1 text-text-2 hover:text-text-1">
            全球
          </button>
        </div>
        <label className="flex items-center gap-2 text-text-2">
          <input type="checkbox" checked={m.showData} onChange={(e) => m.setShowData(e.target.checked)} className="accent-[var(--accent)]" />
          顯示所有實測連動（股價與美股指標的相關係數 ≥ 0.3）
        </label>
      </Panel>

      <Panel
        title={s ? `${TYPE_NAME[s.type] ?? ''}：${s.name}` : '海外節點'}
        className="min-h-0 flex-1"
        bodyClassName="overflow-auto p-3 text-xs"
      >
        {s ? (
          <div className="space-y-3">
            <div className="text-2xs text-text-3">
              {s.symbol ? `${s.symbol} · ` : ''}
              {s.place}
              {s.industry ? ` · ${s.industry}` : ''}
            </div>
            {own.length === 0 ? (
              <EmptyState title="沒有整理到與海外節點的關係" detail="目前只收錄公開資訊中長期、廣泛報導的關係，以及實測的股價連動。" />
            ) : (
              <ul className="space-y-1.5">
                {own.map((l) => {
                  const other = m.by.get(l.source === s.id ? l.target : l.source)
                  return (
                    <li key={`${l.source}|${l.target}|${l.rel}`} className="border-b border-line/60 pb-1.5">
                      <button type="button" onClick={() => other && m.select(other.id)} className="text-left hover:text-text-1">
                        <span className={l.origin === 'data' ? 'text-text-2' : 'text-text-1'}>{relText(l, m.by)}</span>
                      </button>
                      <div className="text-2xs text-text-3">{l.origin === 'data' ? '由股價資料算出（近 500 個交易日）' : '公開資訊整理'}</div>
                    </li>
                  )
                })}
              </ul>
            )}
            {s.type === 'company' && s.symbol && (
              <div className="flex gap-3 text-2xs">
                <Link to="/stock/$symbol" params={{ symbol: s.symbol }} className="text-accent hover:underline">
                  開啟個股終端
                </Link>
                <Link to="/graph/$symbol" params={{ symbol: s.symbol }} className="text-accent hover:underline">
                  知識圖譜
                </Link>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {REGIONS.map((r) => {
              const items = globals.filter((p) => region(p) === r)
              if (items.length === 0) return null
              return (
                <div key={r}>
                  <h3 className="pb-1 text-2xs text-text-3">{r}</h3>
                  <ul>
                    {items.map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          onClick={() => m.select(p.id)}
                          className="grid w-full grid-cols-[1fr_auto] gap-2 py-1 text-left hover:bg-hover"
                        >
                          <span className="text-text-1">
                            {p.name}
                            <span className="ml-1.5 text-2xs text-text-3">{TYPE_NAME[p.type]}</span>
                          </span>
                          <span className="num text-text-3">{m.degree.get(p.id)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        )}
      </Panel>
      <Panel title="怎麼讀" bodyClassName="space-y-1 p-3 text-2xs leading-relaxed text-text-3">
        <p>流動的線：供應或合作關係，光點從供應方流向客戶。實線：競爭。點線：股價實測連動（從指標指向台股）。</p>
        <p>台股公司依登記地址放在所在縣市，新竹科學園區單獨一區；同一地點的公司以螺旋排開。</p>
        <p>關係只收錄公開資訊中長期、廣泛報導者，不代表完整的客戶或供應商名單。</p>
      </Panel>
    </>
  )
}
