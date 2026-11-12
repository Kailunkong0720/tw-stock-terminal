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

（Phase 0 完成時補上）
