<#
.SYNOPSIS
    Claude Code Stop hook: refuse to end a turn with nothing watching the work.

.DESCRIPTION
    Exits 2 (which blocks the turn end and shows the stderr message to the
    model) when ALL of these hold:
      * the bot is not running (pid file AND process identity),
      * no background waker is armed (jsonlog/waker.json, due_at in the future),
      * the repository has unpushed commits on main, or maintenance.hold exists.

    Exits 0 in every other case, when stop_hook_active is set (so it can never
    loop), and when the kill switch jsonlog/turn-end-guard.disabled exists.
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$BotIdentity = 'hengbot',
    [switch]$IgnoreStdin
)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $Root 'jsonlog'

if (Test-Path -LiteralPath (Join-Path $runtime 'turn-end-guard.disabled')) {
    Write-Output 'turn-end guard disabled by kill switch'
    exit 0
}

# Never block a turn that is already ending because of this hook.
if (-not $IgnoreStdin -and [Console]::IsInputRedirected) {
    $raw = [Console]::In.ReadToEnd()
    if ($raw) {
        try {
            $payload = $raw | ConvertFrom-Json
            if ($payload -and $payload.stop_hook_active) {
                Write-Output 'stop_hook_active; not re-blocking'
                exit 0
            }
        } catch { }
    }
}

function Test-BotRunning {
    $pidFile = Join-Path $runtime 'bot.pid'
    if (-not (Test-Path -LiteralPath $pidFile)) { return $false }
    $raw = (Get-Content -LiteralPath $pidFile -Raw -ErrorAction SilentlyContinue)
    $botPid = 0
    if (-not [int]::TryParse(($raw -replace '\s', ''), [ref]$botPid)) { return $false }
    if ($botPid -le 0) { return $false }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$botPid" -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    # Identity, not just liveness: bot.pid held a dead pid for six hours on
    # 2026-09-23 and a recycled pid would otherwise read as a healthy bot.
    return ("$($process.CommandLine)").ToLowerInvariant().Contains($BotIdentity.ToLowerInvariant())
}

function Test-WakerArmed {
    $path = Join-Path $runtime 'waker.json'
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    try { $marker = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { return $false }
    if (-not $marker.due_at) { return $false }
    $due = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($marker.due_at, [ref]$due)) { return $false }
    return $due -gt [DateTimeOffset]::Now
}

function Get-UnpushedCount {
    try {
        $output = & git -C $Root rev-list --count origin/main..main 2>$null
        if ($LASTEXITCODE -ne 0) { return 0 }
        $count = 0
        if ([int]::TryParse(("$output").Trim(), [ref]$count)) { return $count }
        return 0
    } catch { return 0 }
}

$botRunning = Test-BotRunning
$wakerArmed = Test-WakerArmed
$unpushed = Get-UnpushedCount
$hold = Test-Path -LiteralPath (Join-Path $runtime 'maintenance.hold')

if (-not $botRunning -and -not $wakerArmed -and ($unpushed -gt 0 -or $hold)) {
    $reasons = @()
    if ($unpushed -gt 0) { $reasons += "$unpushed unpushed commit(s) on main" }
    if ($hold) { $reasons += 'maintenance.hold is present' }
    $message = "turn-end guard: the bot is not running, no waker is armed, and " +
               ($reasons -join ' and ') + ". Arm a waker (scripts/arm_waker.ps1 -Seconds N), " +
               "restart the bot, or push/clear the hold before ending the turn. " +
               "Kill switch: $runtime\turn-end-guard.disabled"
    [Console]::Error.WriteLine($message)
    exit 2
}

$state = @("bot=$botRunning", "waker=$wakerArmed", "unpushed=$unpushed", "hold=$hold") -join ' '
Write-Output "turn-end guard ok ($state)"
exit 0
