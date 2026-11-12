import { EmptyState, Panel } from '../../design/Panel'

/** 尚未實作的區塊。說明之後會出現什麼，不放假資料。 */
export function SectionPage({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="h-full p-2">
      <Panel title={title} className="h-full min-h-96">
        <EmptyState detail={detail} />
      </Panel>
    </div>
  )
}
