$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = $null
foreach ($taskCandidate in @('python', 'py')) {
    $taskCommand = Get-Command $taskCandidate -ErrorAction SilentlyContinue
    if ($taskCommand -and $taskCommand.Source -notmatch 'WindowsApps') { $taskPython = $taskCommand.Source; break }
}
if (-not $taskPython) {
    $taskBundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $taskBundledPython) { $taskPython = $taskBundledPython }
}
if (-not $taskPython) { throw 'Python 3.9 or newer is required. Install Python from python.org, then try again.' }
foreach ($taskPort in @(8765, 8766)) {
    $taskRunning = $false
    try {
        $taskHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$taskPort/health" -TimeoutSec 2
        $taskRunning = $taskHealth.app -eq 'ai-village-heat-live-v1'
        if (-not $taskRunning) { throw "Port $taskPort is used by a different application." }
    } catch { if ($_.Exception.Message -match 'different application') { throw } }
    if (-not $taskRunning) {
        $taskArgs = @('-X', 'utf8', '-u', ('"' + (Join-Path $taskRoot 'live_server.py') + '"'))
        if ($taskPort -eq 8766) { $taskArgs += '--open-chat' }
        Start-Process -FilePath $taskPython -ArgumentList $taskArgs -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot "server-$taskPort.out.log") -RedirectStandardError (Join-Path $taskRoot "server-$taskPort.err.log") | Out-Null
    }
}
if (-not ($args -contains '-NoBrowser')) { Start-Process 'http://127.0.0.1:8765' }
Write-Output 'Main village: http://127.0.0.1:8765'
Write-Output 'Open Chat:    http://127.0.0.1:8766'
