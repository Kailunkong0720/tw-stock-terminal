import { IconChevronDown, IconChevronUp } from '@tabler/icons-react'
import { useState } from 'react'

import type { AnalysisInfo } from '../lib/contract/types'
import { useMeta } from '../lib/data'
import { formatDate, formatDateTime } from '../lib/format'

export function useAnalyses(ids: string[]): AnalysisInfo[] {
  const meta = useMeta()
  const all = meta.data?.analyses ?? []
  return ids.map((id) => all.find((a) => a.id === id)).filter((a): a is AnalysisInfo => Boolean(a))
}

function runText(a: AnalysisInfo): string {
  if (!a.run_last) return '尚無執行紀錄'
  if (a.run_first && formatDateTime(a.run_first) !== formatDateTime(a.run_last)) {
    return `${formatDateTime(a.run_first)} 至 ${formatDateTime(a.run_last)}`
  }
  return formatDateTime(a.run_last)
}

/** 一項分析的完整說明：方法、參數、使用的資料與期間、計算時間（「關於」頁與各面板展開時共用）。 */
export function AnalysisCard({ a }: { a: AnalysisInfo }) {
  return (
    <article id={`analysis-${a.id}`} className="space-y-2 rounded-control border border-line bg-raised/60 p-3 text-xs leading-relaxed">
      <h4 className="text-xs font-medium text-text-1">{a.name}</h4>
      <p className="text-text-2">{a.method}</p>
      <dl className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1.5 text-text-2">
        <dt className="text-text-3">資料期間</dt>
        <dd className="num">
          {a.data_from || a.data_to ? `${formatDate(a.data_from)} 至 ${formatDate(a.data_to)}` : '—'}
        </dd>
        <dt className="text-text-3">計算時間</dt>
        <dd className="num">{runText(a)}（台北時間）</dd>
        {a.summary && (
          <>
            <dt className="text-text-3">結果</dt>
            <dd>{a.summary}</dd>
          </>
        )}
        {a.params.length > 0 && (
          <>
            <dt className="text-text-3">參數</dt>
            <dd>
              <ul className="list-disc space-y-0.5 pl-4">
                {a.params.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </dd>
          </>
        )}
        {a.inputs.length > 0 && (
          <>
            <dt className="text-text-3">使用資料</dt>
            <dd>
              <ul className="list-disc space-y-0.5 pl-4">
                {a.inputs.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </dd>
          </>
        )}
      </dl>
    </article>
  )
}

/** 面板底部的一行出處：什麼時候算的、用哪段資料；點開看完整方法。 */
export function Provenance({ ids, className = '' }: { ids: string[]; className?: string }) {
  const items = useAnalyses(ids)
  const [open, setOpen] = useState(false)
  if (items.length === 0) return null
  const a = items[0]!
  return (
    <div className={`text-2xs text-text-3 ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-2 gap-y-0.5 text-left hover:text-text-2"
      >
        <span>
          計算於 <span className="num">{a.run_last ? formatDateTime(a.run_last) : '—'}</span>
        </span>
        {(a.data_from || a.data_to) && (
          <span>
            資料 <span className="num">{formatDate(a.data_from)}</span> 至 <span className="num">{formatDate(a.data_to)}</span>
          </span>
        )}
        <span className="ml-auto inline-flex items-center gap-0.5 text-accent">
          {open ? '收起' : '方法說明'}
          {open ? <IconChevronUp size={11} /> : <IconChevronDown size={11} />}
        </span>
      </button>
      {open && (
        <div className="mt-2 max-h-80 space-y-2 overflow-auto">
          {items.map((x) => (
            <AnalysisCard key={x.id} a={x} />
          ))}
        </div>
      )}
    </div>
  )
}
