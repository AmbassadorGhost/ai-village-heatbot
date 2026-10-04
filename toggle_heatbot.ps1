[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Toggle','On','Off','Status')][string]$Action = 'Toggle',
    [switch]$NoUi,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$toggleRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$toggleTools = Join-Path $toggleRoot 'tools'
$toggleLog = Join-Path $toggleTools 'toggle.log'

function Get-ManagedHeatbotProcesses {
    $liveMarker = Join-Path $toggleRoot 'live_server.py'
    $demoMarker = Join-Path $toggleRoot 'demo_server.py'
    $tunnelMarker = Join-Path $toggleTools 'cloudflared.exe'
    @(Get-CimInstance Win32_Process | Where-Object {
        $line = $_.CommandLine
        if (-not $line) { return $false }
        $python = $_.Name -match '^python(?:w)?\.exe$'
        $live = $python -and $line.IndexOf(('"' + $liveMarker + '"'), [StringComparison]::OrdinalIgnoreCase) -ge 0
        $demo = $python -and $line.IndexOf(('"' + $demoMarker + '"'), [StringComparison]::OrdinalIgnoreCase) -ge 0
        $tunnel = $_.Name -eq 'cloudflared.exe' -and
            $line.IndexOf($tunnelMarker, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $line.Contains('--url http://127.0.0.1:8780')
        $live -or $demo -or $tunnel
    })
}

function Show-HeatbotMessage([string]$message, [bool]$failed = $false) {
    if ($NoUi) { return }
    Add-Type -AssemblyName System.Windows.Forms
    $image = if ($failed) { [Windows.Forms.MessageBoxIcon]::Error } else { [Windows.Forms.MessageBoxIcon]::Information }
    [Windows.Forms.MessageBox]::Show($message, 'AI Village Heatbot', [Windows.Forms.MessageBoxButtons]::OK, $image) | Out-Null
}

$toggleMutex = New-Object System.Threading.Mutex($false, 'Local\AI_Village_Heatbot_Toggle')
$toggleAcquired = $false
try {
    try { $toggleAcquired = $toggleMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $toggleAcquired = $true }
    if (-not $toggleAcquired) {
        Show-HeatbotMessage 'Heatbot is already starting or stopping. Give it a moment, then try again.'
        return
    }
    $managed = @(Get-ManagedHeatbotProcesses)
    $wanted = if ($Action -eq 'Toggle') { if ($managed.Count) { 'Off' } else { 'On' } } else { $Action }
    if ($wanted -eq 'Status') {
        [PSCustomObject]@{ state = $(if ($managed.Count) { 'ON' } else { 'OFF' }); managed_process_count = $managed.Count } | ConvertTo-Json
        return
    }
    if (-not $PSCmdlet.ShouldProcess('Main village, Open Chat, demo gateway and Cloudflare tunnel', ('Turn Heatbot ' + $wanted.ToUpperInvariant()))) {
        return
    }
    if ($wanted -eq 'Off') {
        # These PIDs come from exact script/client paths in this checkout.
        # Recheck identity before stopping, in case a PID was recycled.
        foreach ($item in $managed) {
            $current = @(Get-ManagedHeatbotProcesses | Where-Object { $_.ProcessId -eq $item.ProcessId })
            if ($current.Count) { Stop-Process -Id $item.ProcessId -ErrorAction Stop }
        }
        $remaining = @(Get-ManagedHeatbotProcesses)
        if ($remaining.Count) { throw 'Some Heatbot processes did not stop. Try again or check tools\toggle.log.' }
        $demoRecord = Join-Path $toggleTools 'demo-processes.json'
        if (Test-Path -LiteralPath $demoRecord) { Remove-Item -LiteralPath $demoRecord }
        Show-HeatbotMessage 'Heatbot is OFF. Both collectors, Discord delivery, and the public demo have stopped. Double-click the desktop button to turn them on again.'
    } else {
        if (-not (Test-Path -LiteralPath $toggleTools)) { New-Item -ItemType Directory -Path $toggleTools | Out-Null }
        # A record without managed processes is stale; remove only this named file.
        $demoRecord = Join-Path $toggleTools 'demo-processes.json'
        if (-not $managed.Count -and (Test-Path -LiteralPath $demoRecord)) { Remove-Item -LiteralPath $demoRecord }
        $publicLinkPath = Join-Path $toggleTools 'demo-url.txt'
        if (Test-Path -LiteralPath $publicLinkPath) { Remove-Item -LiteralPath $publicLinkPath }
        & (Join-Path $toggleRoot 'start_demo.ps1') | Out-File -LiteralPath $toggleLog -Encoding utf8 -Append
        foreach ($checkPort in @(8765,8766)) {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$checkPort/health" -TimeoutSec 10
            if ($health.app -ne 'ai-village-heat-live-v1') { throw "Heatbot did not start on port $checkPort." }
        }
        $tunnelRunning = @(Get-ManagedHeatbotProcesses | Where-Object { $_.Name -eq 'cloudflared.exe' })
        if (-not $tunnelRunning.Count) { throw 'The local viewers started, but the public tunnel did not. Double-click again to stop them and retry.' }
        $publicLink = if (Test-Path -LiteralPath $publicLinkPath) { (Get-Content -LiteralPath $publicLinkPath -Raw).Trim() } else { 'Still starting; see tools\demo-tunnel-error.log.' }
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765/' }
        Show-HeatbotMessage ("Heatbot is ON. Both villages and the public demo are running.`n`nPublic link: $publicLink`n`nDouble-click the desktop button again to turn everything off. Keep this computer awake during the demo.")
    }
    [PSCustomObject]@{ action = $wanted; managed_process_count = @(Get-ManagedHeatbotProcesses).Count } | ConvertTo-Json
} catch {
    if (Test-Path -LiteralPath $toggleTools) { $_.Exception.Message | Out-File -LiteralPath $toggleLog -Append -Encoding utf8 }
    Show-HeatbotMessage ("Heatbot could not finish changing state.`n`n" + $_.Exception.Message) $true
    throw
} finally {
    if ($toggleAcquired) { $toggleMutex.ReleaseMutex() }
    $toggleMutex.Dispose()
}
