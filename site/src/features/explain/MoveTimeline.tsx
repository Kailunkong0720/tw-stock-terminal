import { useMemo } from 'react'

import { EmptyState } from '../../design/Panel'
import type { Moves } from '../../lib/contract/types'
import { formatPct, toneClass } from '../../lib/format'
import { useView } from '../../lib/store'
import { MoveDetail } from './MoveDetail'

function MiniDecomp({ mkt, sector, overnight, idio }: { mkt: number | null; sector: number | null; overnight: number | null; idio: number | null }) {
  const parts = [mkt ?? 0, sector ?? 0, overnight ?? 0, idio ?? 0]
  const total = parts.reduce((a, b) => a + Math.abs(b), 0) || 1
  const colors = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--text-1)']
  return (
    <div className="flex h-1.5 w-20 overflow-hidden rounded-full bg-raised" title="大盤／類股／隔夜美股／個股特有 的相對大小">
      {parts.map((p, i) => (
        <div key={i} style={{ width: `${(Math.abs(p) / total) * 100}%`, background: colors[i], opacity: i === 3 ? 0.9 : 0.6 }} />
      ))}
    </div>
  )
}

/** 事件時間軸：這檔股票的異常波動日（新到舊），點擊展開解析並讓 K 線聚焦。 */
export function MoveTimeline({ data, symbol }: { data: Moves | undefined; symbol: string }) {
  const selected = useView((s) => s.selectedMove)
  const select = useView((s) => s.selectMove)
  const focus = useView((s) => s.focus)
  const hover = useView((s) => s.hoverDate)
  const rows = useMemo(() => [...(data?.moves ?? [])].reverse(), [data])

  if (!data || rows.length === 0) return <EmptyState title="沒有異常波動日" detail="扣除大盤、類股與隔夜美股後，沒有明顯的個股特有波動。" />
  return (
    <ul className="text-xs">
      {rows.map((m) => {
        const open = selected === m.date
        const top = m.candidates[0]
        return (
          <li key={m.date} className={`border-b border-line/60 ${hover === m.date ? 'bg-hover' : ''}`}>
            <button
              type="button"
              onClick={() => {
                select(open ? null : m.date)
                focus(m.date)
              }}
              aria-expanded={open}
              className="grid w-full grid-cols-[auto_auto_auto_1fr] items-center gap-3 px-3 py-1.5 text-left hover:bg-hover"
            >
              <span className="num text-text-2">{m.date}</span>
              <span className={`num w-14 text-right ${toneClass(m.ret)}`}>{formatPct(m.ret, 1)}</span>
              <MiniDecomp mkt={m.mkt} sector={m.sector} overnight={m.overnight} idio={m.idio} />
              <span className="truncate text-text-3">
                {data.tracked ? (
                  top ? (
                    <>
                      <span className="text-text-2">{top.type_name}</span>　{top.title}
                    </>
                  ) : (
                    '未找到明確的對應消息'
                  )
                ) : (
                  ''
                )}
              </span>
            </button>
            {open && (
              <div className="border-t border-line/60 bg-canvas/40 px-3 py-3">
                <MoveDetail m={m} tracked={data.tracked} compact symbol={symbol} />
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
