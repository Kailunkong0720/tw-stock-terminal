import { EmptyState, Panel } from '../../design/Panel'

export function MarketPage() {
  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-[minmax(0,1fr)_240px]">
      <Panel title="市場熱力圖" className="min-h-96">
        <EmptyState detail="面積是市值、顏色是漲跌幅，依產業分組；可播放 2020 年至今的變化。" />
      </Panel>
      <Panel title="類股表現" className="min-h-60">
        <EmptyState />
      </Panel>
      <Panel title="加權指數" className="min-h-60">
        <EmptyState />
      </Panel>
      <Panel title="重要事件" className="min-h-60">
        <EmptyState />
      </Panel>
    </div>
  )
}
