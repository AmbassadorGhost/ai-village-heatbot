$ErrorActionPreference = 'Stop'
foreach ($taskPort in @(8765, 8766)) {
    try {
        $taskHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$taskPort/health" -TimeoutSec 2
        if ($taskHealth.app -ne 'ai-village-heat-live-v1') { continue }
        $taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($taskHealth.pid)"
        $taskExpected = Join-Path $PSScriptRoot 'live_server.py'
        if ($taskProcess -and $taskProcess.CommandLine.Contains($taskExpected)) {
            Stop-Process -Id $taskHealth.pid
            Write-Output "Stopped heatbot on port $taskPort."
        }
    } catch { Write-Output "No running heatbot found on port $taskPort." }
}
