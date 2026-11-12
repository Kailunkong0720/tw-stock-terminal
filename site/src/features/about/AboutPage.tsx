import { useMeta } from '../../lib/data'
import { formatDate } from '../../lib/format'
import { Panel } from '../../design/Panel'

export function AboutPage() {
  const meta = useMeta()
  return (
    <div className="mx-auto max-w-3xl p-4">
      <Panel title="關於這個網站" bodyClassName="space-y-4 p-5 text-sm leading-relaxed text-text-2">
        <p>
          這是一個台股歷史資料的分析工具，涵蓋 2020 年至
          <span className="num text-text-1"> {formatDate(meta.data?.data_as_of) } </span>
          的上市股票：價格趨勢、外資動向、K 線模型（Kronos）的預測與回測，以及大波動日與新聞事件的關聯。
        </p>
        <p>
          資料為收盤後的歷史資料，<strong className="font-medium text-text-1">不是即時行情</strong>
          。主要來源為臺灣證券交易所公開資料。本站與證交所無任何關係，資料可能有誤，請以官方公告為準。
        </p>
        <p>
          模型輸出是統計結果，<strong className="font-medium text-text-1">不構成投資建議</strong>
          。每個模型觀點旁都會列出它過去在同一檔股票上的命中率與比較基準，請一併參考。
        </p>
        {meta.data && meta.data.build_notes.length > 0 && (
          <div>
            <h3 className="mb-1 text-xs font-medium text-text-1">建置說明</h3>
            <ul className="list-disc space-y-1 pl-5 text-xs">
              {meta.data.build_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
    </div>
  )
}
