# 台股終端（tw-stock-terminal）

台股 2020 年至今的互動分析終端：價格趨勢、外資動向、K 線模型（[Kronos](https://github.com/shiyu-coder/Kronos)）的預測與回測，以及大波動日與新聞事件的知識圖譜。

網站：<https://kailunkong0720.github.io/tw-stock-terminal/>

> **非即時資料，僅供研究，不構成投資建議。** 本站與臺灣證券交易所無任何關係，資料可能有誤，請以官方公告為準。

## 功能

| 頁面 | 內容 |
|---|---|
| 市場 | 市值前 300 大的熱力圖（可播放 2020 年至今、切換漲跌／累積報酬／外資配色）、類股表現、加權指數、追蹤池近期大波動 |
| 個股 | K 線（還原／原始、均線、公司行動與大波動標記、Kronos 預測錐、回測重播）、價量分布、外資動向、事件時間軸與單日漲跌解析 |
| 資金流向 | 全市場法人買賣超與加權指數、產業 × 月份的外資淨流入、當日外資買賣超排行 |
| 模型 | 追蹤池的 Kronos 訊號排行、模型整體回測命中率與基準比較 |
| 漲跌解析 | 個股特有波動最大的日子、市場事件；單日拆解（大盤／類股／隔夜美股／個股特有）與可能相關的事件 |
| 知識圖譜 | 公司、產業、題材、海外公司、市場指標與事件的關係圖；大波動的解釋路徑；傳導預覽 |
| 全球脈動 | 3D 地球：隔夜傳導（美股前一晚的變動以弧線連到台股當天，可逐日播放 2020 年至今）與全球供應鏈（海外公司總部與台股公司所在縣市之間的關係） |
| 關於 | 更新方式、每項分析的方法／參數／使用的資料期間／計算時間（由管線自動記錄）、資料來源的起訖日 |

快捷鍵：`Ctrl+K` 搜尋、`1`–`6` 切換區間、`A` 切換還原、`↑↓` 切換自選、`←→` 與空白鍵（全球脈動）、`?` 快捷鍵表。

## 架構

```
本機（使用者的電腦）                         GitHub
pipeline：抓資料 → 計算 → 輸出 JSON ──push──► data 分支（只放 JSON）
                                              main 分支（程式碼）
                                                │ Actions 只打包，不運算
                                                ▼
                                              GitHub Pages（純靜態網站）
```

- `pipeline/`：Python 資料管線（uv 管理）。抓證交所公開資料、計算還原價、跑 Kronos、建知識圖譜，最後輸出成靜態 JSON。
- `site/`：React 靜態網站（pnpm 管理），只讀 JSON。
- 完整規劃見 [PLAN.md](PLAN.md)。

## 更新資料

網站不是即時的：資料在本機抓取與計算，**約每季更新一次**，再推上 GitHub。需要 [uv](https://docs.astral.sh/uv/) 與 [GitHub CLI](https://cli.github.com/)。

每季更新（一個指令；可以中斷後重跑，從中斷處繼續）：

```powershell
cd pipeline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quarterly_update.ps1
```

依序：補行情、公司行動、法人、海外指數、重大訊息 → 漲跌拆解、事件歸因、知識圖譜 → 最近三個月大波動日的媒體新聞（GDELT）並重算歸因 → Kronos 最新預測 → 回測（只算新增的基準日）→ 輸出 → 推送並觸發部署。
加 `-NoPush` 只建本機 commit、`-SkipBacktest` 跳過回測。每項分析的執行時間與資料期間會自動記錄，顯示在網站「關於 → 分析說明」。

GDELT 新聞只保留最近三個月，兩次更新的間隔最好不要超過三個月。

也可以分開執行：

```bash
cd pipeline
uv run python -m pipeline refresh   # 補上次之後的新資料，並重算拆解、歸因、圖譜、最新預測、輸出
uv run python -m pipeline publish   # 推到 data 分支並觸發部署
```

個別步驟：`ingest daily|actions|company|flows|global|mops|news`、`moves`、`attribution`、`forecast`、`backtest`、`export`、`check`（資料品質檢查）、`status`。

第一次建置用 `uv run python -m pipeline build`（歷史回補需要數小時，可以中斷後重跑，會從中斷處繼續）。

## 本機開發

```bash
cd site
pnpm install
pnpm dev
```

網站在 `site/public/data/` 找資料；先在 `pipeline/` 執行一次 `export`。

修改 `pipeline/pipeline/export/contract.py`（資料契約）之後：

```bash
cd pipeline && uv run python -m pipeline schema
cd ../site && pnpm gen:types
```

## 資料來源

- [臺灣證券交易所](https://www.twse.com.tw/)：每日收盤行情、三大法人買賣超、外資持股、除權除息
- [臺灣證券交易所 OpenAPI](https://openapi.twse.com.tw/)：上市公司基本資料
- [公開資訊觀測站](https://mops.twse.com.tw/)：歷史重大訊息
- Yahoo Finance：海外指數與匯率（只用於計算，不輸出原始序列）
- [GDELT](https://www.gdeltproject.org/)：媒體新聞（只涵蓋最近三個月）；只顯示標題、來源與連結，連回原站

## 第三方元件

- [Kronos](https://github.com/shiyu-coder/Kronos)（MIT）：K 線基礎模型，程式碼在 `pipeline/vendor/kronos/`
- [TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/)（Apache-2.0）：K 線圖
- [globe.gl](https://github.com/vasturiano/globe.gl)（MIT）：3D 地球；國界資料 [world-atlas](https://github.com/topojson/world-atlas)（Natural Earth，公有領域）

## 授權

程式碼以 [MIT](LICENSE) 授權。資料的權利屬於各原始來源。
