# CLAUDE.md

台股終端（tw-stock-terminal）。完整計劃與階段勾選狀態在 [PLAN.md](PLAN.md)；先讀 PLAN.md 第 0 節的工作守則。

## 接續協議（每個工作階段開始時必讀）

這個專案可能由多個工作階段接力完成（使用量重置後由排程任務 `tw-stock-terminal-resume` 自動接續）。為了不讓兩個工作階段同時改檔案：

1. **心跳檔** `.work/heartbeat`：內容是 ISO 時間。正在工作的工作階段每完成一個步驟（以及至少每 30 分鐘）就覆寫一次：
   ```powershell
   Set-Content -Encoding utf8 'D:\000dashboard-金融\.work\heartbeat' (Get-Date -Format o)
   ```
   開始工作前檢查：心跳檔的修改時間在 **90 分鐘內** → 另一個工作階段正在進行，立即結束，不改任何檔案。
2. **等待使用者** `.work/WAITING_FOR_USER.md`：需要使用者決定或動手時，把問題寫進這個檔案（第一行是一句話摘要）並結束。檔案存在時，自動接續的工作階段不做任何事。使用者回覆後由互動的工作階段刪除它。
3. **進度紀錄** `.work/PROGRESS.md`：每完成一個步驟追加一行（時間、做了什麼、下一步）。接續時先讀最後 20 行。
4. **長時間背景工作**（歷史回補、回測）：由管線自己的鎖檔防止重複執行（`pipeline/data/run/*.lock`，內含 PID）。接續時先用 `python -m pipeline status` 看有沒有工作在跑；在跑就不要重啟同一步驟，可以先做不衝突的工作（例如前端）。
5. 每完成一個勾選項目：更新 PLAN.md 的核取方塊、commit、更新心跳與進度紀錄。

### 已取得的使用者授權（2026-11-12）

- 用 winget 安裝 Node.js、uv（已完成）
- 在 GitHub 帳號 Kailunkong0720 建立**公開** repo `tw-stock-terminal`（MIT 授權）、push 到 `main` 與 `data` 分支、開啟 GitHub Pages、觸發部署工作流程
- 自動接續：每 2 小時的排程任務

### 仍需先問使用者的事

花錢的事（包括使用 Anthropic API）、新增 GitHub Secrets、刪除遠端資料、PLAN.md 標明「先問使用者」的關卡（Phase 2 設計確認、Phase 5 LLM 費用、Phase 6 的 3D 地球）。遇到時寫 `.work/WAITING_FOR_USER.md` 後停止。

## 環境

- Windows 11、PowerShell 5.1；無 NVIDIA GPU（Kronos 用 CPU）
- 新開的 shell 可能沒有最新 PATH，先執行：
  ```powershell
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  ```
- 工具版本（2026-11-12）：uv 0.13.7、Node.js 26.13.1、pnpm 12.18.0、gh 2.103.3（已登入 Kailunkong0720）
- git 身分只設在本 repo：GitHub noreply 信箱（不要改成使用者的私人信箱）
- commit 訊息結尾加上：`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## 常用指令

管線（在 `pipeline/` 下）：

```powershell
uv run python -m pipeline status      # 執行中的步驟、資料庫各表列數、輸出狀態
uv run python -m pipeline build       # 完整建置（可續跑）
uv run python -m pipeline refresh     # 只補新資料
uv run python -m pipeline export      # 輸出 JSON 到 site/public/data/
uv run python -m pipeline publish     # 推 data 分支 + 觸發部署（--no-push 只建本機 commit）
uv run python -m pipeline schema      # 改了 export/contract.py 之後重新產生 schema
uv run pytest                         # 測試（-m network 執行需要連網的測試）
uv run ruff check . ; uv run ruff format .
```

網站（在 `site/` 下）：

```powershell
pnpm dev          # 開發伺服器（或用 Browser pane 的 launch 設定「site」，port 5173）
pnpm gen:types    # schema.json → src/lib/contract/types.ts
pnpm build        # 型別檢查 + 打包
```

每季更新（使用者決定約每季一次，不需要每天；補資料 → 重算 → 回測新增基準日 → 輸出 → 發布，可續跑）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quarterly_update.ps1   # 在 pipeline/ 下；-NoPush、-SkipBacktest
```

分析說明（方法、計算時間、資料期間）寫在 `pipeline/pipeline/export/provenance.py`；新增分析時要在那裡加一項，並在分析步驟結束時呼叫 `core/provenance.py` 的 `save_run`。

只重算與發布（拆解＋歸因＋建圖 → 輸出 → 推送 data 分支並觸發部署）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\refresh_publish.ps1   # 在 pipeline/ 下
```

## 自動接續的注意事項（2026-11-13）

- 背景工作：`ingest flows`、`ingest mops`、`backtest`。用 `uv run python -m pipeline status` 看鎖檔；在跑就不要重啟；「已結束（殘留鎖檔）」代表中斷了，用 `scripts\start_bg.ps1` 重新啟動（會從中斷處續跑）
- flows 與 mops 完成後執行一次 `scripts\refresh_publish.ps1`；回測完成後再執行一次
- 新聞來源已定：**GDELT DOC 2.0、最近三個月**（2026-11-13 使用者決定），可以實作與回補：一輪抓完存起來，不重複抓（2026-11-13 上午本機被 GDELT 限流 429，要長時間退避）；**不要**開始 LLM 抽取（等使用者提供 API 金鑰並同意費用）
- 3D 地球已完成（隔夜傳導＋全球供應鏈）；分析說明已完成（每項分析的方法／計算時間／資料期間）
- 可以做的：Phase 4 驗收（追蹤池 z 最高的 10 天歸因結果表）、Phase 6 收尾（快捷鍵總表、程式碼分割、行動裝置）、上櫃資料（TPEx 端點需驗證）
- 電腦會睡眠：長時間指令已用 SetThreadExecutionState 防閒置睡眠；闔上筆電仍會中斷，重新執行同一指令即可續跑

## 慣例與已知的坑

- **Windows 系統編碼是 cp1252**：讀寫檔案一律明確指定 `encoding="utf-8"`；`alembic.ini` 只能放 ASCII；PowerShell 把中文用管線傳給 git 會變亂碼，commit 訊息先寫成 UTF-8 檔再 `git commit -F 檔案`
- uv 的 Python 3.11 版本捷徑在這台機器上建不起來；`.venv` 是用完整路徑建立的，`.python-version` 仍寫 3.11 給 CI 用
- **Claude 桌面版是封裝應用程式，寫進 `%APPDATA%`、`%LOCALAPPDATA%` 的東西會被虛擬化到 `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\`**，應用程式外（使用者自己的終端機、WMI 建立的處理程序）看不到。因此：
  - 基底 Python 已複製到 `pipeline/.python/cpython-3.11.18/`（已 gitignore），`.venv/pyvenv.cfg` 的 `home` 指向它；不要再用 uv 管理的 Python 重建 venv
  - pnpm 是在應用程式內用 npm 全域安裝的，應用程式外沒有；使用者自己的終端機要先 `npm install -g pnpm@12.18.0`（或用 `npx pnpm@12.18.0`）
  - uv、Node.js、gh、git 在應用程式外都看得到
- **長時間背景工作一律用 `scripts\start_bg.ps1` 啟動**（例：`... -File scripts\start_bg.ps1 "ingest flows" "ingest mops" backtest`）。用工作階段的背景指令啟動的處理程序，工作階段結束時會被一起終止（2026-11-13 09:35 三個回補就這樣中斷過）
- PowerShell 5.1 把沒有 BOM 的 .ps1 當 cp1252 讀：含中文字串的腳本要存成 UTF-8 **含 BOM**
- Node 26 不內建 corepack，pnpm 是用 `npm install -g pnpm` 裝的
- 資料契約的單一來源是 `pipeline/pipeline/export/contract.py`。改了之後要跑 `schema` 和 `pnpm gen:types`，CI 會檢查兩者一致
- push 到 `data` 分支不會觸發部署（該分支沒有工作流程檔），`publish` 會用 `gh workflow run deploy.yml --ref main` 觸發
- 中文字型用 Noto Sans TC（IBM Plex Sans TC 沒有 npm 套件），拉丁字與數字用 IBM Plex Sans／Mono
