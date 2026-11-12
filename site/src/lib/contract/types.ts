/* 由 pipeline 的 JSON Schema 自動產生，請勿手改。重新產生：pnpm gen:types */

/**
 * tw-stock-terminal 靜態資料契約（由 pipeline 自動產生，請勿手改）
 */
export interface Contract {
  Meta?: Meta;
  Calendar?: Calendar;
  Securities?: Securities;
  Bars?: Bars;
  Flows?: Flows;
  MarketFlows?: MarketFlows;
  IndustryFlows?: IndustryFlows;
  Overview?: Overview;
}
/**
 * data/meta.json：網站啟動時第一個讀的檔案。
 */
export interface Meta {
  contract_version: number;
  /**
   * 輸出時間（含時區）
   */
  generated_at: string;
  /**
   * 資料截止日：最後一個有收盤資料的交易日
   */
  data_as_of: string | null;
  /**
   * 資料起始日
   */
  coverage_start: string;
  sources: SourceHealth[];
  /**
   * 追蹤池代號
   */
  tracked: string[];
  /**
   * 建置時做的取捨，顯示在「關於」頁
   */
  build_notes: string[];
}
/**
 * 一個資料來源的狀態。
 */
export interface SourceHealth {
  /**
   * 來源代號，例如 twse_daily
   */
  id: string;
  /**
   * 顯示名稱
   */
  name: string;
  status: "ok" | "partial" | "pending" | "error";
  /**
   * 該來源最新一筆資料的日期
   */
  last_date: string | null;
  note: string | null;
}
/**
 * data/calendar.json：資料期間的所有交易日（遞增）。
 *
 * 其他檔案的日序列不重複寫日期，而是用 `start`（這份日曆的索引）對齊：
 * 陣列第 i 個值對應 `dates[start + i]`。
 */
export interface Calendar {
  dates: string[];
}
/**
 * data/securities.json：所有上市股票與 ETF（搜尋用，啟動時載入）。
 */
export interface Securities {
  items: SecurityInfo[];
}
export interface SecurityInfo {
  symbol: string;
  name: string;
  kind: "stock" | "etf";
  /**
   * 產業名稱；ETF 為 ETF
   */
  industry: string | null;
  /**
   * 是否在追蹤池（有模型預測與事件分析）
   */
  tracked: boolean;
  /**
   * 資料期間內第一個交易日
   */
  first: string;
  /**
   * 資料期間內最後一個交易日
   */
  last: string;
  /**
   * 資料截止日仍有交易（未下市）
   */
  active: boolean;
  /**
   * 最後一個有成交日的收盤價（原始價）
   */
  close: number | null;
  /**
   * 資料截止日的漲跌幅（%）；當日無成交或無法判斷時為 null
   */
  change_pct: number | null;
}
/**
 * data/bars/{symbol}.json：原始（未還原）日線。
 *
 * 陣列與 calendar.dates[start:] 對齊；沒有成交的日子價格為 null、量為 0。
 * 還原價由前端用 actions 計算：某日的累積因子 = 所有 ex_date 在該日之後的 factor 乘積。
 */
export interface Bars {
  symbol: string;
  /**
   * 第一個值在 calendar.dates 中的索引
   */
  start: number;
  open: (number | null)[];
  high: (number | null)[];
  low: (number | null)[];
  close: (number | null)[];
  /**
   * 成交量（張，1 張 = 1,000 股）
   */
  volume: number[];
  /**
   * 成交金額（千元）
   */
  value: number[];
  actions: ActionInfo[];
}
export interface ActionInfo {
  ex_date: string;
  /**
   * dividend_cash / dividend_stock / dividend_both / capital_reduction / par_change / etf_split / etf_reverse_split
   */
  type: string;
  prev_close: number;
  ref_price: number;
  /**
   * 參考價 ÷ 前收。ex_date 之前每一天的價格乘以這個值即為還原價
   */
  factor: number;
  /**
   * 是否改變股數（成交量也要還原）
   */
  affects_shares: boolean;
  detail: string | null;
}
/**
 * data/flows/{symbol}.json：法人買賣超與外資持股。日序列與 calendar 對齊。
 */
export interface Flows {
  symbol: string;
  start: number;
  /**
   * 外資（不含外資自營商）買賣超，張
   */
  foreign_net: number[];
  /**
   * 投信買賣超，張
   */
  trust_net: number[];
  /**
   * 自營商買賣超，張
   */
  dealer_net: number[];
  /**
   * 外資買賣超估算金額（百萬元）= 股數 × 當日收盤價
   */
  foreign_value: number[];
  /**
   * 外資持股比率的日期（每週最後一個交易日與資料截止日）
   */
  holding_dates: string[];
  /**
   * 外資持股比率（%）
   */
  foreign_pct: number[];
}
/**
 * data/flows/market.json：全市場各類法人每日買賣差額（億元，證交所實際金額）。
 */
export interface MarketFlows {
  start: number;
  foreign: (number | null)[];
  trust: (number | null)[];
  /**
   * 自營商（自行買賣 + 避險）
   */
  dealer: (number | null)[];
  total: (number | null)[];
}
/**
 * data/flows/industry.json：各產業每週的外資估算淨流入。
 */
export interface IndustryFlows {
  /**
   * 每週最後一個交易日
   */
  weeks: string[];
  industries: IndustryFlowSeries[];
}
export interface IndustryFlowSeries {
  industry: string;
  /**
   * 每週外資估算淨流入（億元）
   */
  foreign_value: number[];
}
/**
 * data/market/overview.json：大盤、類股表現、漲跌家數。
 */
export interface Overview {
  taiex: IndexSeries;
  sectors: SectorPerf[];
  breadth: Breadth;
}
export interface IndexSeries {
  id: string;
  name: string;
  start: number;
  close: (number | null)[];
}
export interface SectorPerf {
  industry: string;
  index_id: string;
  close: number;
  /**
   * 資料截止日的漲跌幅（%）
   */
  change_pct: number | null;
  /**
   * 近 21 個交易日報酬（%）
   */
  ret_1m: number | null;
  /**
   * 今年以來報酬（%）
   */
  ret_ytd: number | null;
  /**
   * 近 252 個交易日報酬（%）
   */
  ret_1y: number | null;
}
export interface Breadth {
  start: number;
  up: number[];
  down: number[];
  flat: number[];
}
