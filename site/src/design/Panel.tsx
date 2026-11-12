import type { ReactNode } from 'react'

type PanelProps = {
  title?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
  bodyClassName?: string
}

/** 終端的基本容器：比底色亮一階，1px 細線分層，無陰影。 */
export function Panel({ title, actions, children, className = '', bodyClassName = '' }: PanelProps) {
  return (
    <section className={`flex min-h-0 min-w-0 flex-col rounded-panel border border-line bg-panel ${className}`}>
      {(title || actions) && (
        <header className="flex h-9 shrink-0 items-center justify-between gap-3 border-b border-line px-3">
          <h2 className="truncate text-xs font-medium text-text-2">{title}</h2>
          {actions && <div className="flex items-center gap-1">{actions}</div>}
        </header>
      )}
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  )
}

/** 資料尚未就緒時的空狀態。只用文字，不放插圖。 */
export function EmptyState({ title = '尚無資料', detail }: { title?: string; detail?: ReactNode }) {
  return (
    <div className="flex h-full min-h-24 flex-col items-start justify-center gap-1 px-4 py-6">
      <p className="text-xs text-text-2">{title}</p>
      {detail && <p className="max-w-md text-2xs text-text-3">{detail}</p>}
    </div>
  )
}
