# 在 Claude 應用程式之外啟動長時間的管線步驟。
# 用 WMI 建立的處理程序不屬於任何工作階段：工作階段結束、對話重啟都不會把它一起終止。
# 用法（在 pipeline 目錄）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_bg.ps1 "ingest flows" "ingest mops" backtest
# 每個步驟的輸出寫到 data\logs\bg-<名稱>.out；進度看 data\logs\pipeline.log 或 `uv run python -m pipeline status`。
# 同一步驟已在執行時，管線的步驟鎖會讓新的那份立即結束，不會重複跑。
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Steps)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "找不到 $py；先執行 uv sync" }
$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
foreach ($step in $Steps) {
    $name = ($step -replace '^ingest\s+', '') -replace '\s+', '-'
    $log = Join-Path $root "data\logs\bg-$name.out"
    $cmd = "cmd.exe /c `"set PYTHONUTF8=1&& `"$py`" -m pipeline $step > `"$log`" 2>&1`""
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $cmd; CurrentDirectory = $root; ProcessStartupInformation = $si
    }
    if ($r.ReturnValue -ne 0) { throw "啟動 $step 失敗（WMI 回傳 $($r.ReturnValue)）" }
    Write-Output "$step → PID $($r.ProcessId)，輸出 $log"
}
