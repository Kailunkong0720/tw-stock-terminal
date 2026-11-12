# 台股終端（tw-stock-terminal）

台股 2020 年至今的互動分析終端：價格趨勢、外資動向、K 線模型（[Kronos](https://github.com/shiyu-coder/Kronos)）的預測與回測，以及大波動日與新聞事件的知識圖譜。

網站：<https://kailunkong0720.github.io/tw-stock-terminal/>

> **非即時資料，僅供研究，不構成投資建議。** 本站與臺灣證券交易所無任何關係，資料可能有誤，請以官方公告為準。

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

需要 [uv](https://docs.astral.sh/uv/) 與 [GitHub CLI](https://cli.github.com/)。

```bash
cd pipeline
uv run python -m pipeline refresh   # 補上次之後的新資料
uv run python -m pipeline publish   # 推到 data 分支並觸發部署
```

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
- [臺灣證券交易所 OpenAPI](https://openapi.twse.com.tw/)：上市公司基本資料、重大訊息
- 新聞只顯示標題、來源與連結，連回原站

## 授權

程式碼以 [MIT](LICENSE) 授權。資料的權利屬於各原始來源。
