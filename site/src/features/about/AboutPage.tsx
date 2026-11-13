import { Panel } from '../../design/Panel'
import { useMeta } from '../../lib/data'
import { formatDate, formatDateTime } from '../../lib/format'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium text-text-1">{title}</h3>
      <div className="space-y-2 text-xs leading-relaxed text-text-2">{children}</div>
    </section>
  )
}

export function AboutPage() {
  const meta = useMeta()
  const m = meta.data
  return (
    <div className="mx-auto max-w-3xl space-y-2 p-4">
      <Panel title="關於這個網站" bodyClassName="space-y-5 p-5">
        <p className="text-sm leading-relaxed text-text-2">
          台股 2020 年至 <span className="num text-text-1">{formatDate(m?.data_as_of)}</span> 的上市股票分析工具：價格趨勢、外資動向、
          K 線模型（Kronos）的預測與回測、大波動日與事件的關聯，以及公司與全球實體的知識圖譜。
        </p>
        <div className="rounded-control border border-line bg-raised p-3 text-xs leading-relaxed text-text-2">
          資料為收盤後的歷史資料，<strong className="font-medium text-text-1">不是即時行情</strong>。
          本站與臺灣證券交易所無任何關係，資料可能有誤，請以官方公告為準。模型輸出是統計結果，
          <strong className="font-medium text-text-1">不構成投資建議</strong>。
        </div>

        <Section title="還原價">
          <p>
            依證交所公布的除權息、減資、變更面額、ETF 分割與反分割的參考價還原：某日之前的價格乘上「參考價 ÷ 前收」。
            含現金增資的除權用「減除股利參考價」，因為證交所以它作為開盤基準，現增部分不會讓股價機械性下跌。
          </p>
        </Section>
        <Section title="漲跌拆解與大波動日">
          <p>
            每天的報酬用前 250 個交易日的迴歸拆成大盤、類股（相對大盤）、前一晚費城半導體指數與個股特有四部分，
            大盤與類股使用含息的報酬指數。個股特有部分異常大（z ≥ 2.5 且至少 2%），或成交量超過前 20 日均量 3 倍且漲跌 3% 以上，
            即列為大波動日。
          </p>
        </Section>
        <Section title="可能相關的事件">
          <p>
            候選事件來自公開資訊觀測站的重大訊息，以及由資料產生的市場事件（前一晚費半漲跌 3% 以上、加權指數漲跌 2.5% 以上）。
            每個候選事件的分數由實體相關性、事件類型先驗（由本站自己的資料統計）、方向一致性、時間接近度、來源可信度組成。
            這些是「可能相關」，時間相近不代表因果；找不到就顯示未找到。
          </p>
        </Section>
        <Section title="K 線模型">
          <p>
            Kronos（開源 K 線基礎模型，MIT 授權）的 mini 版本，未針對台股微調。每次產生多條可能的走勢，上漲機率是其中期末收盤高於今天的比例。
            回測時每個基準日只用當天以前的資料（包含還原因子），命中率與兩種不需要模型的基準比較；沒有明顯優勢時標籤顯示為灰色。
          </p>
        </Section>
        <Section title="知識圖譜">
          <p>
            關係有兩種來源：人工整理的公開、廣為人知的關係（實線），以及由股價資料算出的連動（點線，近 500 個交易日與指標前一晚報酬的相關係數 0.3 以上）。
            解釋路徑把大波動、可能相關的事件與它的源頭串起來。
          </p>
        </Section>

        {m && m.build_notes.length > 0 && (
          <Section title="這次建置的設定與取捨">
            <ul className="list-disc space-y-1 pl-5">
              {m.build_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </Section>
        )}

        {m && (
          <Section title="資料來源">
            <ul className="space-y-1">
              {m.sources.map((s) => (
                <li key={s.id} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-text-1">{s.name}</span>
                  <span className={s.status === 'ok' ? 'text-accent' : 'text-warn'}>
                    {s.status === 'ok' ? '完整' : s.status === 'partial' ? '部分' : s.status === 'pending' ? '尚未取得' : '錯誤'}
                  </span>
                  {s.last_date && <span className="num text-text-3">至 {s.last_date}</span>}
                  {s.note && <span className="text-text-3">{s.note}</span>}
                </li>
              ))}
            </ul>
            <p className="text-text-3">
              臺灣證券交易所（每日收盤行情、三大法人、外資持股、除權息與分割、OpenAPI）、公開資訊觀測站（重大訊息）、
              Yahoo Finance（海外指數，只用於計算）。產生於 <span className="num">{formatDateTime(m.generated_at)}</span>。
            </p>
          </Section>
        )}

        <Section title="開放原始碼">
          <p>
            程式碼以 MIT 授權公開於 GitHub。圖表使用 TradingView 的{' '}
            <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Lightweight Charts™
            </a>
            （Copyright © TradingView, Inc.），K 線模型使用{' '}
            <a href="https://github.com/shiyu-coder/Kronos" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Kronos
            </a>
            。
          </p>
        </Section>
      </Panel>
    </div>
  )
}
