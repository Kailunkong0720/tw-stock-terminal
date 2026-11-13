# 每季更新：補資料 → 重算分析 → 輸出網站資料 → 發布到 GitHub Pages。
#
# 用法（在 pipeline 目錄，用自己的 PowerShell 即可）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quarterly_update.ps1
#   加 -NoPush        只在本機建立 data 分支的 commit，不推送（先自己檢查再發布）
#   加 -SkipBacktest  跳過回測（最花時間的一步，約每檔 7 秒 × 新增的基準日）
#
# 每一步都可以續跑：中斷（關機、睡眠、網路斷線）後重新執行這個腳本，會從沒做完的地方繼續，
# 已經抓過的資料、已經算過的預測與回測不會重做。
# 所有分析的執行時間與資料期間會自動記錄，網站「關於 → 分析說明」會跟著更新。
#
# GDELT 新聞只保留最近三個月：兩次更新的間隔最好不要超過三個月，新聞才不會有空窗。
param([switch]$NoPush, [switch]$SkipBacktest)

$ErrorActionPreference = 'Continue'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path -Parent $PSScriptRoot)
$started = Get-Date

function Invoke-Step([string]$label, [string[]]$arguments) {
    Write-Output ''
    Write-Output "== $label（$(Get-Date -Format 'MM-dd HH:mm')）"
    & uv run python -m pipeline @arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Output "失敗：$label（結束碼 $LASTEXITCODE）。詳細紀錄在 data\logs\pipeline.log；修正後重新執行這個腳本即可從中斷處繼續。"
        exit $LASTEXITCODE
    }
}

Invoke-Step '資料庫結構' @('migrate')
Invoke-Step '行情、公司行動、公司基本資料（證交所）' @('ingest', 'daily', 'actions', 'company')
Invoke-Step '三大法人與外資持股（證交所）' @('ingest', 'flows')
Invoke-Step '海外指數（Yahoo Finance）' @('ingest', 'global')
Invoke-Step '重大訊息（公開資訊觀測站）' @('ingest', 'mops')
Invoke-Step '漲跌拆解、事件歸因、知識圖譜' @('moves')
Invoke-Step 'Kronos 最新預測' @('forecast')
if (-not $SkipBacktest) {
    Invoke-Step 'Kronos 回測（只算新增的基準日）' @('backtest')
}
Invoke-Step '輸出網站資料' @('export')
if ($NoPush) {
    Invoke-Step '建立 data 分支的本機 commit（未推送）' @('publish', '--no-push')
    Write-Output '檢查沒問題後執行：uv run python -m pipeline publish'
} else {
    Invoke-Step '推送到 GitHub 並觸發部署' @('publish')
}
Write-Output ''
Write-Output "完成，共 $([int]((Get-Date) - $started).TotalMinutes) 分鐘。網站約 2 分鐘後更新。"
