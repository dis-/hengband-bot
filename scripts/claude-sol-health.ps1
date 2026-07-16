$ErrorActionPreference = 'Continue'
$supervisor = 'C:\hengband\bot-client\scripts\sol-supervisor.ps1'

$result = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $supervisor -Action ensure 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Output "SOL SUPERVISION ALERT: health check failed: $result"
    exit 0
}

$health = $result | Select-Object -Last 1
if ($health -notmatch '"state":"(healthy|started|disabled)"') {
    Write-Output "SOL SUPERVISION ALERT: unexpected health result: $health"
} elseif ($health -notmatch '"state":"disabled"') {
    $statePath = 'C:\hengband\bot-client\jsonlog\sol-supervisor-state.json'
    $state = $null
    try { $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch {}
    if ($state -and $state.anomaly) {
        Write-Output "SOL SUPERVISION INCIDENT: $($state.anomaly). Read $statePath and jsonlog/sol-events.jsonl, then take over diagnosis. Do not blindly resume the bot."
    } elseif ($health -match '"state":"started"') {
        Write-Output "SOL SUPERVISION RECOVERY: Claude restarted the stale or missing supervisor. Check $statePath for takeover status."
    }
}
