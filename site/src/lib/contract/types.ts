/* 由 pipeline 的 JSON Schema 自動產生，請勿手改。重新產生：pnpm gen:types */

/**
 * tw-stock-terminal 靜態資料契約（由 pipeline 自動產生，請勿手改）
 */
export interface Contract {
  Meta?: Meta;
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
