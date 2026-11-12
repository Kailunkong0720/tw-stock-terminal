import { CONTRACT_VERSION, useMeta } from '../lib/data'
import { formatDate, formatDateTime } from '../lib/format'

function Dot({ tone }: { tone: 'ok' | 'warn' | 'off' }) {
  const color = tone === 'ok' ? 'bg-accent' : tone === 'warn' ? 'bg-warn' : 'bg-text-3'
  return <span className={`inline-block size-1.5 rounded-full ${color}`} aria-hidden="true" />
}

/** 底部狀態列（參考設計的連線狀態列）：顯示資料截止日與資料來源狀態。 */
export function StatusBar() {
  const meta = useMeta()

  let left
  if (meta.isPending) {
    left = (
      <span className="flex items-center gap-1.5 text-text-3">
        <Dot tone="off" />
        讀取資料狀態…
      </span>
    )
  } else if (meta.isError) {
    left = (
      <span className="flex items-center gap-1.5 text-warn">
        <Dot tone="warn" />
        {meta.error.message}
      </span>
    )
  } else {
    const m = meta.data
    const hasData = Boolean(m.data_as_of)
    left = (
      <>
        <span className="flex items-center gap-1.5">
          <Dot tone={hasData ? 'ok' : 'warn'} />
          <span className="text-text-2">資料截至</span>
          <span className="num text-text-1">{hasData ? formatDate(m.data_as_of, true) : '尚無資料'}</span>
        </span>
        <span className="hidden text-text-3 md:inline">
          涵蓋 <span className="num">{formatDate(m.coverage_start)}</span> 起
        </span>
        <span className="hidden text-text-3 lg:inline">
          產生於 <span className="num">{formatDateTime(m.generated_at)}</span>
        </span>
        <span className="hidden items-center gap-3 xl:flex">
          {m.sources.map((s) => (
            <span key={s.id} className="flex items-center gap-1 text-text-3" title={s.note ?? undefined}>
              <Dot tone={s.status === 'ok' ? 'ok' : s.status === 'pending' ? 'off' : 'warn'} />
              {s.name}
            </span>
          ))}
        </span>
      </>
    )
  }

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t border-line bg-panel px-4 text-2xs">
      {left}
      <span className="ml-auto hidden shrink-0 text-text-3 sm:inline">非即時資料 · 僅供研究，不構成投資建議</span>
      <span className="num shrink-0 text-text-3" title="資料契約版本">
        v{CONTRACT_VERSION}
      </span>
    </footer>
  )
}
