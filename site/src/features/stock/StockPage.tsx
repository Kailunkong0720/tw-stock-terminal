import { useParams } from '@tanstack/react-router'

import { EmptyState, Panel } from '../../design/Panel'

/** 個股終端（PLAN.md 7.2）。版面骨架對應參考設計：資訊條 → 大圖表 + 中欄 + 右欄 → 下方時間軸。 */
export function StockPage() {
  const { symbol } = useParams({ from: '/stock/$symbol' })
  return (
    <div className="grid min-h-full gap-2 p-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_260px_300px] xl:grid-rows-[auto_minmax(0,1fr)_220px]">
      <Panel className="xl:col-span-3" bodyClassName="flex h-14 items-center gap-6 px-4">
        <span className="num text-base font-medium text-text-1">{symbol}</span>
        <span className="text-xs text-text-3">尚無日線資料</span>
      </Panel>

      <Panel title="K 線" className="min-h-80">
        <EmptyState detail="日線資料回補完成後，這裡顯示 2020 年至今的 K 線、成交量與均線，並疊加事件標記與模型預測錐。" />
      </Panel>

      <div className="grid min-h-0 gap-2 xl:grid-rows-2">
        <Panel title="價量分布">
          <EmptyState detail="可視區間內各價位的累積成交量。" />
        </Panel>
        <Panel title="大波動日">
          <EmptyState detail="扣除大盤與類股影響後，個股特有波動最大的日子。" />
        </Panel>
      </div>

      <Panel title="模型觀點">
        <EmptyState detail="Kronos 對未來 5、10、20 個交易日的看法，以及它過去在這檔股票上的命中率。" />
      </Panel>

      <Panel title="事件時間軸" className="xl:col-span-3">
        <EmptyState detail="大波動日與可能相關的公司公告、新聞，以及當天的外資動向。" />
      </Panel>
    </div>
  )
}
