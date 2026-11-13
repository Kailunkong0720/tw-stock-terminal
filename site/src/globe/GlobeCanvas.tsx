import Globe, { type GlobeInstance } from 'globe.gl'
import { useEffect, useRef, useState } from 'react'
import { feature } from 'topojson-client'

import { alpha, readTheme } from '../charts/theme'
import './globe.css'

export type GlobeArc = {
  id: string
  startLat: number
  startLng: number
  endLat: number
  endLng: number
  color: string | [string, string]
  stroke: number
  /** 虛線流動一輪的毫秒數；0 = 不動 */
  dashTime: number
  /** flow：長虛線（可流動）；dots：點線；solid：實線。預設 flow */
  pattern?: 'flow' | 'dots' | 'solid'
  altitude?: number | null
  label?: string
}
export type GlobePoint = { id: string; lat: number; lng: number; color: string; radius: number; altitude?: number; label?: string }
export type GlobeRing = { id: string; lat: number; lng: number; color: string; maxR: number; speed: number; period: number }
export type GlobeTag = { id: string; lat: number; lng: number; html: string; onClick?: () => void }
export type GlobeView = { lat: number; lng: number; altitude: number }

type Props = {
  arcs: GlobeArc[]
  points: GlobePoint[]
  rings: GlobeRing[]
  tags: GlobeTag[]
  /** 改變時鏡頭轉過去 */
  view: GlobeView
  onPointClick?: (id: string) => void
  onArcClick?: (id: string) => void
}

const TAIWAN_ID = '158' // ISO 3166-1 數字代碼
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** 3D 地球（globe.gl）。陸地用點陣六角格，台灣以強調色描邊。 */
export function GlobeCanvas({ arcs, points, rings, tags, view, onPointClick, onArcClick }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const globe = useRef<GlobeInstance | null>(null)
  const [failed, setFailed] = useState(false)
  const handlers = useRef({ onPointClick, onArcClick })
  handlers.current = { onPointClick, onArcClick }

  // 建立一次
  useEffect(() => {
    const el = box.current
    if (!el) return
    const t = readTheme()
    const still = reducedMotion()
    let g: GlobeInstance
    try {
      g = new Globe(el, { animateIn: false })
    } catch {
      setFailed(true) // 沒有 WebGL
      return
    }
    g.backgroundColor('rgba(0,0,0,0)')
      .showAtmosphere(true)
      .atmosphereColor(t.accent)
      .atmosphereAltitude(0.12)
      .showGraticules(true)
      .arcStartLat('startLat')
      .arcStartLng('startLng')
      .arcEndLat('endLat')
      .arcEndLng('endLng')
      .arcColor('color')
      .arcStroke('stroke')
      .arcAltitude((d) => (d as GlobeArc).altitude ?? null)
      .arcAltitudeAutoScale(0.4)
      .arcDashLength((d) => ({ flow: 0.5, dots: 0.03, solid: 1 })[(d as GlobeArc).pattern ?? 'flow'])
      .arcDashGap((d) => ({ flow: 0.22, dots: 0.025, solid: 0 })[(d as GlobeArc).pattern ?? 'flow'])
      .arcDashInitialGap(() => Math.random())
      .arcDashAnimateTime((d) => (still ? 0 : (d as GlobeArc).dashTime))
      .arcLabel((d) => (d as GlobeArc).label ?? '')
      .arcsTransitionDuration(0)
      .pointLat('lat')
      .pointLng('lng')
      .pointColor('color')
      .pointRadius('radius')
      .pointAltitude((d) => (d as GlobePoint).altitude ?? 0.004)
      .pointLabel((d) => (d as GlobePoint).label ?? '')
      .pointsMerge(false)
      .pointsTransitionDuration(0)
      .ringColor((d: object) => {
        const c = (d as GlobeRing).color
        return (x: number) => alpha(c, Math.max(0, 1 - x) * 0.9)
      })
      .ringMaxRadius('maxR')
      .ringPropagationSpeed('speed')
      .ringRepeatPeriod((d) => (still ? 1e9 : (d as GlobeRing).period))
      .htmlAltitude(0.012)
      .htmlTransitionDuration(0)
      .htmlElement((d) => {
        const tag = d as GlobeTag
        const div = document.createElement('div')
        div.className = 'globe-tag'
        div.innerHTML = tag.html
        if (tag.onClick) {
          div.style.pointerEvents = 'auto'
          div.style.cursor = 'pointer'
          div.onclick = tag.onClick
        }
        return div
      })
      .onPointClick((p) => handlers.current.onPointClick?.((p as GlobePoint).id))
      .onArcClick((a) => handlers.current.onArcClick?.((a as GlobeArc).id))

    const mat = g.globeMaterial() as unknown as { color: { set(c: string): void }; emissive?: { set(c: string): void } }
    mat.color.set(t.panel)
    mat.emissive?.set('#050706')
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
    const controls = g.controls() as unknown as { enableDamping: boolean; dampingFactor: number; minDistance: number }
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = 103

    // 陸地：點陣六角格；台灣：描邊
    let alive = true
    void import('world-atlas/countries-110m.json').then((mod) => {
      if (!alive) return
      const topo = (mod.default ?? mod) as unknown as { objects: { countries: never } }
      const fc = feature(topo as never, topo.objects.countries) as unknown as { features: { id?: string | number }[] }
      const features = fc.features
      const tw = features.filter((f) => String(f.id) === TAIWAN_ID)
      g.hexPolygonsData(features)
        .hexPolygonResolution(3)
        .hexPolygonMargin(0.42)
        .hexPolygonUseDots(true)
        .hexPolygonColor((f) => (String((f as { id?: string }).id) === TAIWAN_ID ? t.accent : alpha(t.text3, 0.9)))
        .polygonsData(tw)
        .polygonCapColor(() => alpha(t.accent, 0.18))
        .polygonSideColor(() => 'rgba(0,0,0,0)')
        .polygonStrokeColor(() => t.accent)
        .polygonAltitude(0.003)
    })

    const ro = new ResizeObserver(([e]) => {
      g.width(e!.contentRect.width).height(e!.contentRect.height)
    })
    ro.observe(el)
    globe.current = g
    if (import.meta.env.DEV) (window as unknown as { __globe?: GlobeInstance }).__globe = g // 開發時方便檢查
    return () => {
      alive = false
      ro.disconnect()
      g._destructor()
      globe.current = null
      el.innerHTML = ''
    }
  }, [])

  useEffect(() => {
    globe.current?.arcsData(arcs)
  }, [arcs])
  useEffect(() => {
    globe.current?.pointsData(points)
  }, [points])
  useEffect(() => {
    globe.current?.ringsData(rings)
  }, [rings])
  useEffect(() => {
    globe.current?.htmlElementsData(tags).htmlLat('lat').htmlLng('lng')
  }, [tags])
  useEffect(() => {
    globe.current?.pointOfView(view, reducedMotion() ? 0 : 1200)
  }, [view])

  return (
    <div ref={box} className="globe-host absolute inset-0 overflow-hidden">
      {failed && (
        <div className="flex h-full items-center justify-center p-6 text-center text-xs text-text-3">
          這個瀏覽器或裝置無法顯示 3D 地球（需要 WebGL）。右側的數據仍然可以使用。
        </div>
      )}
    </div>
  )
}
