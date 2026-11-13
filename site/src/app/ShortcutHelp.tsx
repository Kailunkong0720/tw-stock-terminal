import { useEffect, useState } from 'react'

const SHORTCUTS: [string, string][] = [
  ['Ctrl K　或　/', '搜尋股票'],
  ['1 – 6', 'K 線時間區間：1 月、3 月、6 月、1 年、3 年、全部'],
  ['A', '切換還原價／原始價'],
  ['↑　↓', '在自選股之間切換'],
  ['?', '顯示這份快捷鍵表'],
  ['Esc', '關閉視窗'],
]

/** 按 ? 顯示快捷鍵總表。 */
export function ShortcutHelp() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, [contenteditable="true"]')) return
      if (e.key === '?') setOpen((o) => !o)
      else if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-canvas/70 pt-[14vh]" onClick={() => setOpen(false)}>
      <div
        role="dialog"
        aria-label="鍵盤快捷鍵"
        className="w-[min(420px,calc(100vw-2rem))] rounded-panel border border-line-strong bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-xs font-medium text-text-2">鍵盤快捷鍵</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-xs">
          {SHORTCUTS.map(([k, d]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="num rounded border border-line bg-raised px-1.5 py-0.5 text-2xs text-text-1">{k}</kbd>
              </dt>
              <dd className="text-text-2">{d}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
