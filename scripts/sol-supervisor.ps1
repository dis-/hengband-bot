param(
    [ValidateSet('start', 'ensure', 'run', 'status', 'stop')]
    [string]$Action = 'status',
    [string]$BotRoot = 'C:\hengband\bot-client'
)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $BotRoot 'jsonlog'
$enabledFile = Join-Path $runtime 'sol-supervision.enabled'
$pidFile = Join-Path $runtime 'sol-supervisor.pid'
$legacyOperatorPidFile = Join-Path $runtime 'sol-operator.pid'
$stateFile = Join-Path $runtime 'sol-supervisor-state.json'
$agentHeartbeatFile = Join-Path $runtime 'sol-agent-heartbeat.json'
$eventsFile = Join-Path $runtime 'sol-events.jsonl'
$operatorScript = Join-Path $BotRoot 'scripts\sol-operator-once.ps1'
$self = $MyInvocation.MyCommand.Path

function Get-FilePid([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $value = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
    if ($value -match '^\d+$') { return [int]$value }
    return $null
}

function Test-LivePid($ProcessId) {
    if (-not $ProcessId) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
    catch { return $null }
}

function Write-AtomicJson([string]$Path, $Value) {
    $temp = "$Path.$PID.tmp"
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $Path -Force
}

function Add-Event([string]$Type, [string]$Detail) {
    $event = [ordered]@{
        time = [DateTimeOffset]::Now.ToString('o')
        type = $Type
        source = 'sol-supervisor'
        detail = $Detail
    }
    Add-Content -LiteralPath $eventsFile -Value ($event | ConvertTo-Json -Compress) -Encoding utf8
}

function Get-HeartbeatAgeSeconds {
    $state = Get-JsonFile $stateFile
    if (-not $state -or -not $state.heartbeat) { return [double]::PositiveInfinity }
    try { return ([DateTimeOffset]::Now - [DateTimeOffset]::Parse($state.heartbeat)).TotalSeconds }
    catch { return [double]::PositiveInfinity }
}

function Format-AgeSeconds([double]$Age) {
    if ([double]::IsInfinity($Age) -or [double]::IsNaN($Age)) { return 'missing' }
    return "$([int]$Age)s"
}

function Stop-ProcessTree([int]$RootPid) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootPid" -ErrorAction SilentlyContinue
    foreach ($child in $children) { Stop-ProcessTree ([int]$child.ProcessId) }
    Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
}

function Start-Supervisor {
    $existingPid = Get-FilePid $pidFile
    $age = Get-HeartbeatAgeSeconds
    if ((Test-LivePid $existingPid) -and $age -le 90) {
        return [ordered]@{ state = 'healthy'; pid = $existingPid; heartbeat_age_seconds = [int]$age }
    }

    if (Test-LivePid $existingPid) {
        Add-Event 'supervisor_stale' "Supervisor PID $existingPid heartbeat age is $(Format-AgeSeconds $age); recycling it."
        Stop-ProcessTree $existingPid
        Start-Sleep -Milliseconds 500
    }

    $process = Start-Process powershell.exe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $self,
        '-Action', 'run', '-BotRoot', $BotRoot
    ) -WindowStyle Hidden -PassThru

    $deadline = [DateTimeOffset]::Now.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $age = Get-HeartbeatAgeSeconds
    } while ($age -gt 10 -and [DateTimeOffset]::Now -lt $deadline -and -not $process.HasExited)

    return [ordered]@{
        state = $(if ((Test-LivePid $process.Id) -and $age -le 10) { 'started' } else { 'failed' })
        pid = $process.Id
        heartbeat_age_seconds = $(if ([double]::IsPositiveInfinity($age)) { $null } else { [int]$age })
    }
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

if ($Action -eq 'start') {
    Set-Content -LiteralPath $enabledFile -Value ([DateTimeOffset]::Now.ToString('o')) -Encoding ascii
    Start-Supervisor | ConvertTo-Json -Compress
    exit 0
}

if ($Action -eq 'ensure') {
    if (-not (Test-Path -LiteralPath $enabledFile)) {
        '{"state":"disabled"}'
        exit 0
    }
    Start-Supervisor | ConvertTo-Json -Compress
    exit 0
}

if ($Action -eq 'status') {
    $state = Get-JsonFile $stateFile
    $supervisorPid = Get-FilePid $pidFile
    [ordered]@{
        enabled = Test-Path -LiteralPath $enabledFile
        supervisor_alive = Test-LivePid $supervisorPid
        supervisor_pid = $supervisorPid
        heartbeat_age_seconds = $(
            $age = Get-HeartbeatAgeSeconds
            if ([double]::IsPositiveInfinity($age)) { $null } else { [int]$age }
        )
        state = $state
    } | ConvertTo-Json -Depth 8
    exit 0
}

if ($Action -eq 'stop') {
    Remove-Item -LiteralPath $enabledFile -Force -ErrorAction SilentlyContinue
    $supervisorPid = Get-FilePid $pidFile
    if (Test-LivePid $supervisorPid) { Stop-ProcessTree $supervisorPid }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $legacyOperatorPidFile -Force -ErrorAction SilentlyContinue
    '{"state":"stopped","game_untouched":true,"bot_untouched":true}'
    exit 0
}

# The run action is internal. The mutex prevents two Claude/sol launchers from
# creating competing operator processes.
$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\HengbandSolSupervisor', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

try {
    Set-Content -LiteralPath $enabledFile -Value ([DateTimeOffset]::Now.ToString('o')) -Encoding ascii
    Set-Content -LiteralPath $pidFile -Value $PID -Encoding ascii
    Add-Event 'supervisor_start' "Supervisor started as PID $PID."

    $operator = $null
    $generation = 0
    $restartDelay = 5
    $nextStart = [DateTimeOffset]::MinValue
    $lastIncident = ''
    $operatorStartedAt = $null

    while (Test-Path -LiteralPath $enabledFile) {
        $now = [DateTimeOffset]::Now
        $gamePid = Get-FilePid (Join-Path $runtime 'hengband.pid')
        $botPid = Get-FilePid (Join-Path $runtime 'bot.pid')
        $gameAlive = Test-LivePid $gamePid
        $botAlive = Test-LivePid $botPid
        $anomaly = $null

        if ($gameAlive -and -not $botAlive) {
            $loopLine = Get-Content -LiteralPath (Join-Path $runtime 'bot-stderr.log') -Tail 20 -ErrorAction SilentlyContinue |
                Where-Object { $_ -match 'loop-detected|stopping bot|Traceback|ERROR' } |
                Select-Object -Last 1
            $anomaly = if ($loopLine) { "bot-stopped: $loopLine" } else { 'bot-stopped while game remains alive' }
            if ($anomaly -ne $lastIncident) {
                Add-Event 'operator_alert' $anomaly
                $lastIncident = $anomaly
            }
        } elseif ($botAlive) {
            $lastIncident = ''
        }

        if ($operator -and $operator.HasExited) {
            $operatorRuntime = if ($operatorStartedAt) { ($now - $operatorStartedAt).TotalSeconds } else { 0 }
            Add-Event 'operator_exit' "Operator generation $generation exited with code $($operator.ExitCode); restart in ${restartDelay}s."
            $operator = $null
            $nextStart = $now.AddSeconds($restartDelay)
            $restartDelay = if ($operatorRuntime -ge 300) { 5 } else { [Math]::Min($restartDelay * 2, 120) }
            $operatorStartedAt = $null
            Remove-Item -LiteralPath $legacyOperatorPidFile -Force -ErrorAction SilentlyContinue
        }

        if ($operator -and -not $operator.HasExited) {
            $agentHeartbeat = Get-JsonFile $agentHeartbeatFile
            $agentAge = [double]::PositiveInfinity
            if ($agentHeartbeat -and $agentHeartbeat.time) {
                try { $agentAge = ($now - [DateTimeOffset]::Parse($agentHeartbeat.time)).TotalSeconds } catch {}
            }
            if ($agentAge -gt 360) {
                Add-Event 'operator_stale' "Operator generation $generation heartbeat age is $(Format-AgeSeconds $agentAge); recycling it."
                Stop-ProcessTree $operator.Id
                $operator = $null
                $nextStart = $now.AddSeconds(5)
                $operatorStartedAt = $null
                Remove-Item -LiteralPath $legacyOperatorPidFile -Force -ErrorAction SilentlyContinue
            }
        }

        if (-not $operator -and $now -ge $nextStart) {
            $generation++
            Write-AtomicJson $agentHeartbeatFile ([ordered]@{
                time = $now.ToString('o'); generation = $generation; phase = 'launching'; source = 'sol-supervisor'
            })
            $operator = Start-Process powershell.exe -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $operatorScript, '-BotRoot', $BotRoot
            ) -WindowStyle Hidden -PassThru
            $operatorStartedAt = $now
            Set-Content -LiteralPath $legacyOperatorPidFile -Value $operator.Id -Encoding ascii
            Add-Event 'operator_start' "Started operator generation $generation as PID $($operator.Id)."
        }

        Write-AtomicJson $stateFile ([ordered]@{
            heartbeat = $now.ToString('o')
            supervisor_pid = $PID
            operator_pid = $(if ($operator -and -not $operator.HasExited) { $operator.Id } else { $null })
            operator_generation = $generation
            game_pid = $gamePid
            game_alive = $gameAlive
            bot_pid = $botPid
            bot_alive = $botAlive
            anomaly = $anomaly
        })
        Start-Sleep -Seconds 15
    }
} finally {
    if ($operator -and -not $operator.HasExited) { Stop-ProcessTree $operator.Id }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $legacyOperatorPidFile -Force -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
