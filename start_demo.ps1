$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$runtime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (!(Test-Path -LiteralPath $runtime)) { $runtime = (Get-Command python).Source }
$client = Join-Path $PSScriptRoot 'tools\cloudflared.exe'
if (!(Test-Path -LiteralPath $client)) { throw 'Download the official cloudflared Windows client into tools\cloudflared.exe first.' }
$record = Join-Path $PSScriptRoot 'tools\demo-processes.json'
if (Test-Path -LiteralPath $record) { throw 'A demo record already exists. Run STOP_DEMO.cmd before starting a new link.' }
& (Join-Path $PSScriptRoot 'start_live.ps1') -NoBrowser
$gateway = Start-Process -FilePath $runtime -ArgumentList @('-X','utf8',('"'+(Join-Path $PSScriptRoot 'demo_server.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput 'tools\demo-server.log' -RedirectStandardError 'tools\demo-server-error.log' -PassThru
@{gateway=$gateway.Id} | ConvertTo-Json | Set-Content -LiteralPath $record
Start-Sleep -Seconds 2
try {
    $null = Invoke-WebRequest 'http://127.0.0.1:8780/api/live' -TimeoutSec 15
    $tunnel = Start-Process -FilePath $client -ArgumentList @('tunnel','--no-autoupdate','--url','http://127.0.0.1:8780') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput 'tools\demo-tunnel.log' -RedirectStandardError 'tools\demo-tunnel-error.log' -PassThru
    @{gateway=$gateway.Id;tunnel=$tunnel.Id} | ConvertTo-Json | Set-Content -LiteralPath $record
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $log = Get-Content -LiteralPath 'tools\demo-tunnel-error.log' -Raw -ErrorAction SilentlyContinue
        if ($log -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
            $Matches[0] | Set-Content -LiteralPath 'tools\demo-url.txt'
            Write-Output ('Public demo: ' + $Matches[0])
            Write-Output 'Keep this computer awake. STOP_DEMO.cmd closes public access without stopping Discord alerts.'
            break
        }
        Start-Sleep -Seconds 1
    }
    if ($attempt -eq 30) { Write-Output 'Tunnel is still starting. Check tools\demo-tunnel-error.log for its URL or an error.' }
} catch { Write-Output 'Demo did not start. Run STOP_DEMO.cmd to clean up before retrying.'; throw }
