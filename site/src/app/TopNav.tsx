import { Link } from '@tanstack/react-router'

import { Segmented } from '../design/Segmented'
import { setUpDown, useUpDown } from '../lib/prefs'
import { useView } from '../lib/store'

const NAV = [
  { to: '/', label: '市場' },
  { to: '/stock/$symbol', params: { symbol: '2330' }, label: '個股' },
  { to: '/flows', label: '資金流向' },
  { to: '/forecast', label: '模型' },
  { to: '/explain', label: '漲跌解析' },
  { to: '/graph', label: '知識圖譜' },
  { to: '/about', label: '關於' },
] as const

function Mark() {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
      <path d="M6 3v14M14 5v10" stroke="var(--text-3)" strokeWidth="1.2" />
      <rect x="4" y="6" width="4" height="7" rx="0.8" fill="var(--up)" />
      <rect x="12" y="8" width="4" height="4" rx="0.8" fill="var(--down)" />
    </svg>
  )
}

export function TopNav() {
  const updown = useUpDown()
  return (
    <header className="flex h-11 shrink-0 items-center gap-6 border-b border-line bg-panel px-4">
      <Link to="/" className="flex shrink-0 items-center gap-2 text-text-1">
        <Mark />
        <span className="text-sm font-semibold tracking-wide">台股終端</span>
      </Link>

      <nav className="-mb-px flex h-full min-w-0 items-stretch gap-5 overflow-x-auto">
        {NAV.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            params={'params' in item ? item.params : undefined}
            activeOptions={{ exact: item.to === '/', includeSearch: false }}
            className="flex shrink-0 items-center border-b-2 border-transparent text-xs text-text-2 transition-colors hover:text-text-1"
            activeProps={{ className: '!border-accent !text-text-1' }}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <button
        type="button"
        onClick={() => useView.getState().setSearchOpen(true)}
        className="ml-auto flex h-7 shrink-0 items-center gap-6 rounded-control border border-line bg-raised px-2.5 text-xs text-text-3 transition-colors hover:border-line-strong hover:text-text-2"
      >
        <span>搜尋代號或名稱</span>
        <kbd className="num text-2xs">Ctrl K</kbd>
      </button>

      <div className="hidden shrink-0 items-center gap-2 lg:flex">
        <span className="text-2xs text-text-3">漲跌配色</span>
        <Segmented
          size="xs"
          label="漲跌配色"
          value={updown}
          onChange={setUpDown}
          options={[
            { value: 'red-up', label: '紅漲' },
            { value: 'green-up', label: '綠漲' },
          ]}
        />
      </div>
    </header>
  )
}
