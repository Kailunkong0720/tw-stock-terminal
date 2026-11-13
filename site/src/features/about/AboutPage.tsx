import { Panel } from '../../design/Panel'
import { AnalysisCard } from '../../design/Provenance'
import { useMeta } from '../../lib/data'
import { formatDate, formatDateTime } from '../../lib/format'

function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <section id={id} className="space-y-2">
      <h3 className="text-xs font-medium text-text-1">{title}</h3>
      <div className="space-y-2 text-xs leading-relaxed text-text-2">{children}</div>
    </section>
  )
}

const STATUS: Record<string, string> = { ok: '完整', partial: '部分', pending: '尚未取得', error: '錯誤' }

export function AboutPage() {
  const meta = useMeta()
  const m = meta.data
  const analyses = m?.analyses ?? []
  return (
    <div className="mx-auto max-w-3xl space-y-2 p-4">
      <Panel title="關於這個網站" bodyClassName="space-y-5 p-5">
        <p className="text-sm leading-relaxed text-text-2">
          台股 2020 年至 <span className="num text-text-1">{formatDate(m?.data_as_of)}</span> 的上市股票分析工具：價格趨勢、外資動向、
          K 線模型（Kronos）的預測與回測、大波動日與事件的關聯、公司與全球實體的知識圖譜，以及美股對台股的隔夜傳導。
        </p>
        <div className="rounded-control border border-line bg-raised p-3 text-xs leading-relaxed text-text-2">
          資料為收盤後的歷史資料，<strong className="font-medium text-text-1">不是即時行情</strong>。
          本站與臺灣證券交易所無任何關係，資料可能有誤，請以官方公告為準。模型輸出是統計結果，
          <strong className="font-medium text-text-1">不構成投資建議</strong>。
        </div>

        <Section title="更新方式">
          <p>
            所有資料都在本機抓取與計算後，輸出成靜態檔案發布到 GitHub Pages；網站本身不連線到任何資料來源。
            約每季更新一次：補上新的行情、法人、公告與新聞，重算模型預測與新增的回測，再重新發布。
          </p>
          {m && (
            <p className="num text-text-3">
              這次發布：{formatDateTime(m.generated_at)}（台北時間）　資料截止日：{formatDate(m.data_as_of)}　資料起始日：
              {formatDate(m.coverage_start)}
            </p>
          )}
        </Section>

        <Section title="分析說明" id="analyses">
          <p>
            每一項分析的方法、參數、使用的資料與期間、計算時間。期間與時間由管線在計算時自動記錄，不是手寫；
            網站各面板下方的「方法說明」也是同一份內容。
          </p>
          {analyses.length === 0 ? (
            <p className="text-text-3">這份資料沒有附上分析紀錄（較舊的發布）。</p>
          ) : (
            <div className="space-y-2">
              {analyses.map((a) => (
                <AnalysisCard key={a.id} a={a} />
              ))}
            </div>
          )}
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
            <div className="overflow-x-auto">
              <table className="w-full min-w-[30rem] text-left">
                <thead>
                  <tr className="text-2xs text-text-3">
                    <th className="py-1 pr-3 font-normal">來源</th>
                    <th className="py-1 pr-3 font-normal">狀態</th>
                    <th className="py-1 pr-3 font-normal">資料期間</th>
                    <th className="py-1 font-normal">備註</th>
                  </tr>
                </thead>
                <tbody>
                  {m.sources.map((s) => (
                    <tr key={s.id} className="border-t border-line/60 align-top">
                      <td className="py-1 pr-3 text-text-1">{s.name}</td>
                      <td className={`py-1 pr-3 ${s.status === 'ok' ? 'text-accent' : 'text-warn'}`}>{STATUS[s.status] ?? s.status}</td>
                      <td className="num py-1 pr-3 text-text-2">
                        {s.first_date || s.last_date ? `${formatDate(s.first_date)} 至 ${formatDate(s.last_date)}` : '—'}
                      </td>
                      <td className="py-1 text-text-3">{s.note ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
            ，3D 地球使用{' '}
            <a href="https://github.com/vasturiano/globe.gl" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              globe.gl
            </a>
            ，國界資料來自{' '}
            <a href="https://github.com/topojson/world-atlas" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              world-atlas
            </a>
            （Natural Earth）。
          </p>
        </Section>
      </Panel>
    </div>
  )
}
