import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { Waterfall } from '../../charts/Waterfall'
import type { Candidate, MoveOut } from '../../lib/contract/types'
import { formatDateTime, formatPct, formatYi, toneClass } from '../../lib/format'

const COMPONENT_NAMES: Record<string, string> = {
  relevance: '實體相關性',
  prior: '事件類型先驗',
  direction: '方向一致性',
  proximity: '時間接近度',
  credibility: '來源可信度',
}
const WEIGHTS: Record<string, number> = { relevance: 0.35, prior: 0.25, direction: 0.15, proximity: 0.15, credibility: 0.1 }
const LEVEL: Record<string, string> = { official: '官方公告', media: '媒體', market: '市場資料' }

function ScoreBar({ c }: { c: Candidate }) {
  // 分數由五個分項加權組成；每段寬度 = 權重 × 分項分數
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-raised" aria-hidden="true">
      {Object.entries(WEIGHTS).map(([k, w], i) => (
        <div
          key={k}
          className="h-full"
          style={{ width: `${w * (c.components[k] ?? 0) * 100}%`, background: `var(--series-${(i % 3) + 1})`, opacity: 0.85 }}
        />
      ))}
    </div>
  )
}

function CandidateRow({ c, rank }: { c: Candidate; rank: number }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="space-y-1.5 border-b border-line/70 py-2 last:border-b-0">
      <div className="flex items-start gap-2">
        <span className="num mt-0.5 w-4 shrink-0 text-2xs text-text-3">{rank}</span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-2 text-2xs text-text-3">
            <span className="rounded-sm bg-raised px-1 text-text-2">{LEVEL[c.level] ?? c.level}</span>
            <span>{c.type_name}</span>
            <span className="num">{formatDateTime(c.at)}</span>
            {c.direction !== 0 && <span className={c.direction > 0 ? 'text-up' : 'text-down'}>{c.direction > 0 ? '偏利多' : '偏利空'}</span>}
          </div>
          <p className="text-xs leading-snug text-text-1">
            {c.url ? (
              <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
                {c.title}
              </a>
            ) : (
              c.title
            )}
          </p>
          <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left" aria-expanded={open}>
            <ScoreBar c={c} />
            <span className="num shrink-0 text-2xs text-text-2">{c.score.toFixed(2)}</span>
          </button>
          {open && (
            <dl className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-0.5 pt-1 text-2xs">
              {Object.entries(WEIGHTS).map(([k, w]) => (
                <div key={k} className="contents">
                  <dt className="text-text-3">{COMPONENT_NAMES[k]}</dt>
                  <dd className="num text-text-2">{(c.components[k] ?? 0).toFixed(2)}</dd>
                  <dd className="num text-right text-text-3">× {w}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </li>
  )
}

/** 單日漲跌解析：拆解瀑布圖 + 外資動向 + 可能相關的事件。 */
export function MoveDetail({ m, tracked, compact = false, symbol }: { m: MoveOut; tracked: boolean; compact?: boolean; symbol: string }) {
  const parts = [
    { key: 'mkt', label: '大盤', value: m.mkt },
    { key: 'sector', label: '類股', value: m.sector },
    { key: 'overnight', label: '隔夜美股', value: m.overnight },
    { key: 'idio', label: '個股特有', value: m.idio },
  ]
  const common = (m.mkt ?? 0) + (m.sector ?? 0) + (m.overnight ?? 0)
  const idioDominant = Math.abs(m.idio ?? 0) > Math.abs(common)
  return (
    <div className={`grid gap-4 ${compact ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]' : 'lg:grid-cols-2'}`}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="num text-sm text-text-1">{m.date}</span>
          <span className={`num text-base font-medium ${toneClass(m.ret)}`}>{formatPct(m.ret)}</span>
          {m.z != null && (
            <span className="text-2xs text-text-3">
              個股特有 z <span className="num text-text-2">{m.z.toFixed(1)}</span>
            </span>
          )}
          {m.vol_ratio != null && (
            <span className="text-2xs text-text-3">
              量 <span className="num text-text-2">{m.vol_ratio.toFixed(1)}</span> 倍
            </span>
          )}
          {m.gap > 1 && <span className="text-2xs text-warn">與前次成交間隔 {m.gap - 1} 個交易日</span>}
        </div>
        <Waterfall parts={parts} total={m.ret} highlight={idioDominant ? 'idio' : undefined} />
        <p className="text-2xs leading-relaxed text-text-3">
          {idioDominant
            ? '這一天主要是個股自己的波動（扣除大盤、類股與隔夜美股之後仍有明顯變動）。'
            : '這一天的波動主要來自大盤、類股或隔夜美股，個股特有的部分較小。'}
          {m.foreign_value != null && (
            <>
              {' '}當天外資
              <span className={`num ${toneClass(m.foreign_value)}`}>
                {m.foreign_value >= 0 ? '買超' : '賣超'} {formatYi(Math.abs(m.foreign_value), 'M', false)}
              </span>
              {m.foreign_rank != null && m.foreign_rank >= 0.9 && (
                <>（金額為該股歷史上前 <span className="num">{Math.max(1, Math.round((1 - m.foreign_rank) * 100))}%</span>）</>
              )}
              。外資動向說明的是誰在買賣，不是為什麼。
            </>
          )}
        </p>
      </div>
      <div className="min-w-0">
        <h3 className="mb-1 text-xs font-medium text-text-2">可能相關的事件</h3>
        {!tracked ? (
          <p className="text-2xs text-text-3">
            這檔不在追蹤池，沒有做事件比對。
          </p>
        ) : m.candidates.length === 0 ? (
          <p className="text-xs text-text-2">未找到明確的對應消息。</p>
        ) : (
          <ol>
            {m.candidates.map((c, i) => (
              <CandidateRow key={c.id} c={c} rank={i + 1} />
            ))}
          </ol>
        )}
        <p className="mt-2 text-2xs leading-relaxed text-text-3">
          時間相近不代表因果。分數由五個分項加權組成，點分數條可展開。
          {compact && (
            <Link to="/explain/$symbol/$date" params={{ symbol, date: m.date }} className="ml-1 text-accent hover:underline">
              完整解析
            </Link>
          )}
        </p>
      </div>
    </div>
  )
}
