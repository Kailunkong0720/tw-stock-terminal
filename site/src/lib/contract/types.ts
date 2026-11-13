/* 由 pipeline 的 JSON Schema 自動產生，請勿手改。重新產生：pnpm gen:types */

/**
 * tw-stock-terminal 靜態資料契約（由 pipeline 自動產生，請勿手改）
 */
export interface Contract {
  GlobeOvernight?: GlobeOvernight;
  GlobeSupply?: GlobeSupply;
  GraphCore?: GraphCore;
  GraphEgo?: GraphEgo;
  GraphPropagate?: GraphPropagate;
  Moves?: Moves;
  Events?: Events;
  Timeline?: Timeline;
  Forecast?: Forecast;
  Backtest?: Backtest;
  Ranking?: Ranking;
  Meta?: Meta;
  Calendar?: Calendar;
  Securities?: Securities;
  Bars?: Bars;
  Flows?: Flows;
  MarketFlows?: MarketFlows;
  IndustryFlows?: IndustryFlows;
  Overview?: Overview;
  Heatmap?: Heatmap;
  HeatmapHistory?: HeatmapHistory;
}
/**
 * data/globe/overnight.json：美股前一晚的變動與台股當天的表現（隔夜傳導）。
 */
export interface GlobeOvernight {
  start: number;
  series: OvernightSeries[];
  /**
   * 加權指數當日報酬
   */
  taiex: (number | null)[];
  /**
   * 台積電當日報酬（含除權息還原）
   */
  tsmc: (number | null)[];
  /**
   * 落點座標 [lat, lng]：taiex、tsmc
   */
  landing: {
    [k: string]: number[];
  };
}
export interface OvernightSeries {
  /**
   * 例如 GLOBAL:SOX
   */
  id: string;
  name: string;
  /**
   * pct：報酬率（0.01 = 1%）；bp：殖利率變動（基點）
   */
  unit: "pct" | "bp";
  lat: number;
  lng: number;
  place: string;
  /**
   * 弧線落點：加權指數（台北）或台積電（新竹）
   */
  target: "taiex" | "tsmc";
  /**
   * 與日曆對齊（從 start 起）：台股該交易日開盤前、上一個台股交易日之後的海外交易日累積變動；期間沒有海外交易日為 null
   */
  values: (number | null)[];
}
/**
 * data/globe/supply.json：全球實體與台股公司的位置，以及兩者之間的關係。
 */
export interface GlobeSupply {
  places: GlobePlace[];
  links: GlobeLink[];
}
export interface GlobePlace {
  /**
   * 圖譜節點 id，例如 entity:nvidia、company:2330
   */
  id: string;
  name: string;
  /**
   * global_company / organization / indicator / company
   */
  type: string;
  lat: number;
  lng: number;
  /**
   * 地點說明，例如「美國加州聖塔克拉拉」或「新竹科學園區」
   */
  place: string;
  symbol: string | null;
  industry: string | null;
  tracked: boolean;
}
export interface GlobeLink {
  source: string;
  target: string;
  rel: string;
  rel_name: string;
  /**
   * seed：公開資訊人工整理；data：實測股價連動
   */
  origin: "seed" | "data";
  /**
   * 實測相關係數（origin 為 data 時）
   */
  rho: number | null;
  note: string | null;
}
/**
 * data/graph/core.json：種子圖與由資料算出的靜態關係。
 */
export interface GraphCore {
  nodes: GraphNode[];
  links: GraphLink[];
}
export interface GraphNode {
  id: string;
  /**
   * company / industry / concept / global_company / organization / country / indicator / event / move
   */
  type: string;
  name: string;
  attrs: {
    [k: string]: string | number | boolean | null;
  };
}
export interface GraphLink {
  source: string;
  target: string;
  rel: string;
  rel_name: string;
  confidence: number;
  /**
   * seed：人工整理；data：由資料算出；official／market／media：事件；llm：模型從新聞抽取（虛線）
   */
  origin: "seed" | "data" | "official" | "market" | "media" | "llm";
  date: string | null;
  note: string | null;
}
/**
 * data/graph/ego/{symbol}.json：以一檔股票為中心的子圖（含事件與異常波動，可依日期過濾）。
 */
export interface GraphEgo {
  center: string;
  nodes: GraphNode[];
  links: GraphLink[];
  paths: GraphPath[];
}
export interface GraphPath {
  /**
   * 異常波動節點 id
   */
  move: string;
  /**
   * 解釋路徑上的節點（依序），相鄰節點之間有連線
   */
  nodes: string[];
}
/**
 * data/graph/propagate/{node}.json：一個全球實體或指標變動時，可能受影響的台股。
 */
export interface GraphPropagate {
  node: GraphNode;
  items: PropagateItem[];
}
export interface PropagateItem {
  symbol: string;
  name: string;
  /**
   * 傳導路徑的文字說明
   */
  via: string;
  /**
   * 與該指標的實測相關係數（近 500 個交易日）
   */
  rho: number | null;
}
/**
 * data/moves/{symbol}.json：異常波動日與可能相關的事件。
 */
export interface Moves {
  symbol: string;
  /**
   * 只有追蹤池有事件歸因
   */
  tracked: boolean;
  thresholds: {
    [k: string]: number;
  };
  moves: MoveOut[];
}
export interface MoveOut {
  date: string;
  /**
   * 還原後報酬
   */
  ret: number;
  /**
   * 與前一個有成交日之間隔了幾個交易日
   */
  gap: number;
  /**
   * 大盤貢獻
   */
  mkt: number | null;
  /**
   * 類股（相對大盤）貢獻
   */
  sector: number | null;
  /**
   * 前一晚費半貢獻
   */
  overnight: number | null;
  /**
   * 個股特有
   */
  idio: number | null;
  z: number | null;
  /**
   * 成交量 ÷ 前 20 日均量
   */
  vol_ratio: number | null;
  /**
   * 當日外資買賣超（張）
   */
  foreign_lots: number | null;
  /**
   * 當日外資買賣超估算金額（百萬元）
   */
  foreign_value: number | null;
  /**
   * 當日外資買賣超金額的絕對值在該股歷史中的百分位（0–1）
   */
  foreign_rank: number | null;
  candidates: Candidate[];
}
/**
 * 某個異常波動日的候選事件（可能相關，不是原因）。
 */
export interface Candidate {
  id: number;
  /**
   * 公告／發生時間（台北時間）
   */
  at: string;
  /**
   * 影響的交易日（盤後公告算下一個交易日）
   */
  trade_date: string;
  level: "official" | "media" | "market";
  type: string;
  type_name: string;
  /**
   * +1 利多、−1 利空、0 無法判斷
   */
  direction: number;
  title: string;
  source: string;
  url: string | null;
  score: number;
  /**
   * relevance、prior、direction、proximity、credibility
   */
  components: {
    [k: string]: number;
  };
}
/**
 * data/events/{symbol}.json：個股的重大訊息（不含例行公告）。
 */
export interface Events {
  symbol: string;
  events: EventOut[];
}
export interface EventOut {
  id: number;
  /**
   * 公告／發生時間（台北時間）
   */
  at: string;
  /**
   * 影響的交易日（盤後公告算下一個交易日）
   */
  trade_date: string;
  level: "official" | "media" | "market";
  type: string;
  type_name: string;
  /**
   * +1 利多、−1 利空、0 無法判斷
   */
  direction: number;
  title: string;
  source: string;
  url: string | null;
}
/**
 * data/events/timeline.json：市場事件與追蹤池最大的異常波動。
 */
export interface Timeline {
  market: EventOut[];
  moves: TimelineMove[];
}
export interface TimelineMove {
  symbol: string;
  name: string;
  date: string;
  ret: number;
  idio: number | null;
  top: Candidate | null;
}
/**
 * data/forecast/{symbol}.json：最新預測。價格為基準日的還原價（＝基準日的原始收盤尺度）。
 */
export interface Forecast {
  symbol: string;
  model: string;
  base_date: string;
  base_close: number;
  /**
   * 預測的各交易日（假日以平日估計）
   */
  future_dates: string[];
  steps: ForecastStepOut[];
  /**
   * 各條取樣路徑的收盤價
   */
  paths: number[][];
  signals: SignalOut[];
  track: TrackRecord[];
}
export interface ForecastStepOut {
  /**
   * 基準日之後第幾個交易日（1 起算）
   */
  step: number;
  p05: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  /**
   * 收盤高於基準日收盤的路徑比例
   */
  up_prob: number;
}
export interface SignalOut {
  /**
   * 交易日數：5、10、20
   */
  horizon: number;
  up_prob: number;
  /**
   * 期末報酬中位數
   */
  exp_ret: number;
  /**
   * 期末報酬第 10 百分位（下檔風險）
   */
  p10_ret: number;
  /**
   * 途中最大回檔中位數（負值）
   */
  mdd_p50: number;
  /**
   * 偏多／略偏多／中性／略偏空／偏空
   */
  label: string;
}
/**
 * 模型在回測中的方向命中率，與兩種單純基準比較。
 */
export interface TrackRecord {
  horizon: number;
  /**
   * 回測樣本數（不含平盤）
   */
  n: number;
  /**
   * 方向命中率
   */
  hit_rate: number | null;
  /**
   * 較好的單純基準：一律看多數方向、或延續近 20 日趨勢
   */
  baseline_rate: number | null;
  /**
   * 一律看多數方向的命中率
   */
  always_rate: number | null;
  /**
   * 延續近 20 日趨勢的命中率
   */
  momentum_rate: number | null;
  z: number | null;
  /**
   * 命中率明顯優於基準（單尾 p < 0.1，樣本至少 20）
   */
  has_edge: boolean;
}
/**
 * data/forecast/backtest/{symbol}.json：回測重播用。
 */
export interface Backtest {
  symbol: string;
  model: string;
  points: BacktestPoint[];
  track: TrackRecord[];
}
export interface BacktestPoint {
  base_date: string;
  /**
   * 以基準日當下已知的公司行動還原的收盤（＝當日原始收盤）
   */
  base_close: number;
  /**
   * 換算成目前還原價要乘上的因子（基準日之後的公司行動）
   */
  scale: number;
  steps: ForecastStepOut[];
  /**
   * 實際報酬，鍵為 5、10、20
   */
  actual: {
    [k: string]: number | null;
  };
  /**
   * 模型預期報酬（中位數），鍵為 5、10、20
   */
  exp: {
    [k: string]: number;
  };
}
/**
 * data/forecast/ranking.json：追蹤池的訊號排行與模型整體表現。
 */
export interface Ranking {
  model: string;
  /**
   * lookback、pred_len、n_paths、backtest_every、backtest_years
   */
  settings: {
    [k: string]: number;
  };
  label_rules: string[];
  items: RankingItem[];
  /**
   * 整個追蹤池合計的命中率
   */
  pool: TrackRecord[];
  rank_ic: RankIC[];
  backtest_dates: string[];
}
export interface RankingItem {
  symbol: string;
  name: string;
  industry: string | null;
  base_date: string;
  signals: SignalOut[];
  track: TrackRecord[];
}
export interface RankIC {
  horizon: number;
  /**
   * 各基準日橫斷面 Spearman 相關的平均
   */
  mean: number | null;
  n_dates: number;
  /**
   * Rank IC 為正的基準日比例
   */
  positive_share: number | null;
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
  /**
   * 各項分析的方法、時間與資料期間
   */
  analyses: AnalysisInfo[];
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
   * 該來源最早一筆資料的日期
   */
  first_date: string | null;
  /**
   * 該來源最新一筆資料的日期
   */
  last_date: string | null;
  note: string | null;
}
/**
 * 一項分析的說明：用什麼方法、什麼時候算的、用哪段資料（網站「分析說明」）。
 */
export interface AnalysisInfo {
  id: string;
  name: string;
  /**
   * 方法說明
   */
  method: string;
  /**
   * 參數與門檻（條列）
   */
  params: string[];
  /**
   * 使用的資料與來源（條列）
   */
  inputs: string[];
  /**
   * 使用資料的第一天
   */
  data_from: string | null;
  /**
   * 使用資料的最後一天
   */
  data_to: string | null;
  /**
   * 這份結果最早的計算時間（分多次算完時）
   */
  run_first: string | null;
  /**
   * 最近一次計算完成的時間
   */
  run_last: string | null;
  /**
   * 結果摘要，例如樣本數
   */
  summary: string | null;
  /**
   * 呈現這項分析的頁面（站內路徑）
   */
  page: string | null;
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
 * data/securities.json：所有上市股票、ETF 與上櫃股票（搜尋用，啟動時載入）。
 */
export interface Securities {
  items: SecurityInfo[];
}
export interface SecurityInfo {
  symbol: string;
  name: string;
  kind: "stock" | "etf";
  /**
   * TWSE：上市；TPEx：上櫃
   */
  market: "TWSE" | "TPEx";
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
  /**
   * 櫃買指數
   */
  otc: IndexSeries | null;
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
/**
 * data/market/heatmap.json：市值前幾大上市股票的熱力圖。
 *
 * 版面以最新市值固定，播放時只有顏色變化。各週的歷史在 heatmap-history.json（用到才載入）。
 */
export interface Heatmap {
  as_of: string;
  items: HeatItem[];
  /**
   * 資料截止日的漲跌幅（%）
   */
  ret_1d: (number | null)[];
  /**
   * 資料截止日的外資估算買賣超（億元）
   */
  foreign_1d: (number | null)[];
  /**
   * 每週最後一個交易日（時間軸的長度）
   */
  weeks: string[];
}
export interface HeatItem {
  symbol: string;
  name: string;
  industry: string;
  /**
   * 市值（億元）＝最新收盤 × 發行股數
   */
  cap: number;
}
/**
 * data/market/heatmap-history.json：熱力圖各週的歷史。第一維是週、第二維與 heatmap.json 的 items 對齊。
 */
export interface HeatmapHistory {
  weeks: string[];
  /**
   * 各週還原報酬（%）
   */
  ret: (number | null)[][];
  /**
   * 各週外資估算買賣超（億元）
   */
  foreign: (number | null)[][];
}
