import { useNavigate } from '@tanstack/react-router'
import { Command } from 'cmdk'
import { useEffect, useMemo, useState } from 'react'

import type { SecurityInfo } from '../lib/contract/types'
import { useSecurities } from '../lib/data'
import { formatPct, formatPrice, toneClass } from '../lib/format'
import { usePrefs, useView } from '../lib/store'

function rank(s: SecurityInfo, q: string): number {
  if (!q) return 0
  // 同樣符合時，追蹤池（市值前 150 大與主要 ETF）排前面
  const big = s.tracked ? 15 : 0
  if (s.symbol === q) return 100
  if (s.symbol.startsWith(q)) return 80 - s.symbol.length + big
  if (s.name === q) return 70 + big
  if (s.name.startsWith(q)) return 50 + big
  if (s.name.includes(q)) return 30 + big
  if (s.industry?.includes(q)) return 10 + big
  return -1
}

function Row({ s, onPick }: { s: SecurityInfo; onPick: (sym: string) => void }) {
  return (
    <Command.Item
      value={s.symbol}
      onSelect={() => onPick(s.symbol)}
      className="grid cursor-pointer grid-cols-[4.5rem_1fr_auto_4.5rem] items-center gap-3 rounded-control px-2.5 py-1.5 text-xs data-[selected=true]:bg-hover"
    >
      <span className="num text-text-1">{s.symbol}</span>
      <span className="truncate text-text-1">
        {s.name}
        <span className="ml-2 text-2xs text-text-3">{s.industry}</span>
        {!s.active && <span className="ml-2 text-2xs text-warn">已停止交易</span>}
      </span>
      <span className="num text-right text-text-2">{formatPrice(s.close, { etf: s.kind === 'etf' })}</span>
      <span className={`num text-right ${toneClass(s.change_pct)}`}>{formatPct(s.change_pct, 2, false)}</span>
    </Command.Item>
  )
}

/** Ctrl+K 股票搜尋（代號、名稱、產業）。 */
export function SearchDialog() {
  const open = useView((s) => s.searchOpen)
  const setOpen = useView((s) => s.setSearchOpen)
  const secs = useSecurities()
  const navigate = useNavigate()
  const watchlist = usePrefs((s) => s.watchlist)
  const recent = usePrefs((s) => s.recent)
  const [q, setQ] = useState('')

  useEffect(() => {
    if (!open) setQ('')
  }, [open])

  const items = secs.data?.items ?? []
  const bySym = useMemo(() => new Map(items.map((s) => [s.symbol, s])), [items])
  const results = useMemo(() => {
    const t = q.trim().toUpperCase()
    if (!t) return []
    return items
      .map((s) => [rank(s, t), s] as const)
      .filter(([r]) => r >= 0)
      .sort((a, b) => b[0] - a[0] || Number(b[1].active) - Number(a[1].active))
      .slice(0, 40)
      .map(([, s]) => s)
  }, [items, q])

  const pick = (sym: string) => {
    setOpen(false)
    navigate({ to: '/stock/$symbol', params: { symbol: sym } })
  }
  const group = (title: string, syms: string[]) => {
    const list = syms.map((s) => bySym.get(s)).filter((s): s is SecurityInfo => Boolean(s))
    if (list.length === 0) return null
    return (
      <Command.Group heading={title} className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:text-text-3">
        {list.map((s) => (
          <Row key={s.symbol} s={s} onPick={pick} />
        ))}
      </Command.Group>
    )
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      shouldFilter={false}
      label="搜尋股票"
      overlayClassName="fixed inset-0 z-40 bg-canvas/70"
      contentClassName="fixed left-1/2 top-[12vh] z-50 w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-panel border border-line-strong bg-panel"
    >
      <div className="flex items-center gap-2 border-b border-line px-3">
        <span className="text-text-3">⌕</span>
        <Command.Input
          value={q}
          onValueChange={setQ}
          placeholder="代號、名稱或產業，例如 2330、台積、半導體"
          className="h-11 flex-1 bg-transparent text-sm text-text-1 outline-none placeholder:text-text-3"
        />
        <kbd className="num rounded border border-line px-1.5 text-2xs text-text-3">Esc</kbd>
      </div>
      <Command.List className="max-h-[56vh] overflow-auto p-1.5">
        {secs.isPending && <Command.Loading>讀取清單…</Command.Loading>}
        {q.trim() ? (
          <>
            <Command.Empty className="px-3 py-6 text-xs text-text-3">找不到符合的股票或 ETF</Command.Empty>
            {results.map((s) => (
              <Row key={s.symbol} s={s} onPick={pick} />
            ))}
          </>
        ) : (
          <>
            {group('自選', watchlist)}
            {group('最近看過', recent.filter((r) => !watchlist.includes(r)))}
          </>
        )}
      </Command.List>
      <div className="flex gap-4 border-t border-line px-3 py-1.5 text-2xs text-text-3">
        <span>↑↓ 選擇</span>
        <span>Enter 開啟</span>
        <span className="ml-auto">共 {items.length.toLocaleString()} 檔上市股票與 ETF</span>
      </div>
    </Command.Dialog>
  )
}

/** 全域快捷鍵：Ctrl/⌘+K 或 / 開啟搜尋。 */
export function useGlobalShortcuts() {
  const setOpen = useView((s) => s.setSearchOpen)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, [contenteditable="true"]')
      if ((e.key === 'k' || e.key === 'K') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        setOpen(!useView.getState().searchOpen)
      } else if (e.key === '/' && !typing) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])
}
