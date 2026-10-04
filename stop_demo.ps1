$ErrorActionPreference = 'Stop'
$record = Join-Path $PSScriptRoot 'tools\demo-processes.json'
if (!(Test-Path -LiteralPath $record)) { Write-Output 'No demo processes recorded.'; exit }
$saved = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
foreach ($entry in @(@{id=$saved.tunnel;marker=(Join-Path $PSScriptRoot 'tools\cloudflared.exe')},@{id=$saved.gateway;marker=(Join-Path $PSScriptRoot 'demo_server.py')})) {
    if ($entry.id) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.id)"
        if ($proc -and $proc.CommandLine.Contains($entry.marker)) { Stop-Process -Id $entry.id }
        elseif ($proc) { throw 'Process identity changed; refusing to stop an unrelated process.' }
    }
}
Remove-Item -LiteralPath $record
Write-Output 'Public demo stopped. Local collectors and Discord alerts are still running.'
