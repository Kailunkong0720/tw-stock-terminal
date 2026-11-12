import { Outlet } from '@tanstack/react-router'

import { CONTRACT_VERSION, useMeta } from '../lib/data'
import { StatusBar } from './StatusBar'
import { TopNav } from './TopNav'

function ContractBanner() {
  const meta = useMeta()
  if (!meta.data || meta.data.contract_version === CONTRACT_VERSION) return null
  return (
    <div className="shrink-0 border-b border-line bg-raised px-4 py-1.5 text-xs text-warn">
      資料版本（v{meta.data.contract_version}）與網站版本（v{CONTRACT_VERSION}）不一致，部分畫面可能無法顯示。請稍後重新整理。
    </div>
  )
}

export function AppShell() {
  return (
    <div className="flex h-full flex-col">
      <TopNav />
      <ContractBanner />
      <main className="min-h-0 flex-1 overflow-auto">
        <Outlet />
      </main>
      <StatusBar />
    </div>
  )
}
