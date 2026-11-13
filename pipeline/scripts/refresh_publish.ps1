# 重新拆解與歸因、建圖、輸出、發布到 data 分支並觸發部署。
# 用法（在 pipeline 目錄）：powershell -ExecutionPolicy Bypass -File scripts\refresh_publish.ps1
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$env:PYTHONIOENCODING = 'utf-8'
Set-Location (Split-Path -Parent $PSScriptRoot)
foreach ($step in @('moves', 'export', 'publish')) {
    Write-Output "== $step $(Get-Date -Format 'HH:mm:ss')"
    cmd /c "uv run python -m pipeline $step 2>&1" | Select-String -Pattern '因子拆解|歸因：|知識圖譜：|輸出 \d+ 個檔案|已推送|已觸發|Error|Traceback|失敗' | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { Write-Output "FAILED: $step (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
}
Write-Output "== done $(Get-Date -Format 'HH:mm:ss')"
