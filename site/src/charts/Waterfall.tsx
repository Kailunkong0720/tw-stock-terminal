import { formatPct } from '../lib/format'

type Part = { key: string; label: string; value: number | null }

/**
 * 單日報酬的瀑布圖：大盤 → 類股 → 隔夜美股 → 個股特有 → 合計（PLAN.md 7.5 第 5 項）。
 * 純 SVG，顏色用漲跌 token。
 */
export function Waterfall({ parts, total, highlight }: { parts: Part[]; total: number; highlight?: string }) {
  const W = 520
  const H = 200
  const padL = 8
  const padR = 8
  const top = 18
  const bottom = 34
  const cols = parts.length + 1
  const colW = (W - padL - padR) / cols
  const barW = Math.min(46, colW * 0.56)

  // 累積位置
  let acc = 0
  const steps = parts.map((p) => {
    const v = p.value ?? 0
    const s = { ...p, from: acc, to: acc + v }
    acc += v
    return s
  })
  const vals = [0, total, ...steps.flatMap((s) => [s.from, s.to])]
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const span = hi - lo || 0.01
  const y = (v: number) => top + ((hi - v) / span) * (H - top - bottom)
  const x = (i: number) => padL + colW * i + (colW - barW) / 2

  const color = (v: number) => (v > 0 ? 'var(--up)' : v < 0 ? 'var(--down)' : 'var(--flat)')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="單日報酬拆解">
      <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" strokeDasharray="3 3" />
      {steps.map((s, i) => {
        const v = s.value ?? 0
        const y1 = y(Math.max(s.from, s.to))
        const h = Math.max(1, Math.abs(y(s.from) - y(s.to)))
        const dim = highlight && highlight !== s.key
        return (
          <g key={s.key} opacity={dim ? 0.45 : 1}>
            <rect x={x(i)} y={y1} width={barW} height={h} rx={2} fill={color(v)} fillOpacity={0.85} />
            {i < steps.length - 1 && (
              <line
                x1={x(i) + barW}
                x2={x(i + 1)}
                y1={y(s.to)}
                y2={y(s.to)}
                stroke="var(--text-3)"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
            )}
            <text x={x(i) + barW / 2} y={y1 - 5} textAnchor="middle" className="num" fontSize={11} fill="var(--text-1)">
              {s.value == null ? '—' : formatPct(v, 1)}
            </text>
            <text x={x(i) + barW / 2} y={H - 12} textAnchor="middle" fontSize={11} fill="var(--text-2)">
              {s.label}
            </text>
          </g>
        )
      })}
      {/* 合計 */}
      <g>
        <line
          x1={x(steps.length - 1) + barW}
          x2={x(steps.length)}
          y1={y(acc)}
          y2={y(acc)}
          stroke="var(--text-3)"
          strokeDasharray="2 2"
        />
        <rect
          x={x(steps.length)}
          y={y(Math.max(0, total))}
          width={barW}
          height={Math.max(1, Math.abs(y(0) - y(total)))}
          rx={2}
          fill="none"
          stroke={color(total)}
          strokeWidth={1.5}
        />
        <text x={x(steps.length) + barW / 2} y={y(Math.max(0, total)) - 5} textAnchor="middle" className="num" fontSize={11} fill="var(--text-1)" fontWeight={500}>
          {formatPct(total, 1)}
        </text>
        <text x={x(steps.length) + barW / 2} y={H - 12} textAnchor="middle" fontSize={11} fill="var(--text-1)">
          當日
        </text>
      </g>
    </svg>
  )
}
