param(
    [ValidateSet('start', 'run', 'status', 'stop')]
    [string]$Action = 'status',
    [string]$BotRoot = 'C:\hengband\bot-client',
    [string]$Source = 'C:\hengband\lib\user\bot-test.txt',
    [string]$Worktree = 'C:\hengband\.worktrees\bot-dump-publish',
    [DateTimeOffset]$Until = ([DateTimeOffset]::Parse('2026-07-16T16:00:00+09:00'))
)

$ErrorActionPreference = 'Stop'
$runtime = Join-Path $BotRoot 'jsonlog'
$enabledFile = Join-Path $runtime 'codex-dump-publisher.enabled'
$pidFile = Join-Path $runtime 'codex-dump-publisher.pid'
$stateFile = Join-Path $runtime 'codex-dump-publisher-state.json'
$eventsFile = Join-Path $runtime 'sol-events.jsonl'
$destination = Join-Path $Worktree 'live\bot-test.txt'
$self = $MyInvocation.MyCommand.Path

function Get-FilePid([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $value = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
    if ($value -match '^\d+$') { return [int]$value }
    return $null
}

function Test-LivePid($ProcessId) {
    return $ProcessId -and $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Write-State([string]$Status, [string]$Detail, [string]$Commit = '') {
    $value = [ordered]@{
        time = [DateTimeOffset]::Now.ToString('o')
        pid = $PID
        status = $Status
        detail = $Detail
        commit = $Commit
        until = $Until.ToString('o')
    }
    $temp = "$stateFile.$PID.tmp"
    $value | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $stateFile -Force
}

function Add-Event([string]$Type, [string]$Detail) {
    $event = [ordered]@{
        time = [DateTimeOffset]::Now.ToString('o')
        type = $Type
        source = 'codex-dump-publisher'
        detail = $Detail
    }
    Add-Content -LiteralPath $eventsFile -Value ($event | ConvertTo-Json -Compress) -Encoding utf8
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

if ($Action -eq 'start') {
    $existingPid = Get-FilePid $pidFile
    if (Test-LivePid $existingPid) {
        [ordered]@{ state = 'healthy'; pid = $existingPid; until = $Until.ToString('o') } |
            ConvertTo-Json -Compress
        exit 0
    }
    Set-Content -LiteralPath $enabledFile -Value $Until.ToString('o') -Encoding ascii
    $process = Start-Process powershell.exe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $self,
        '-Action', 'run', '-BotRoot', $BotRoot, '-Source', $Source,
        '-Worktree', $Worktree, '-Until', $Until.ToString('o')
    ) -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 1
    [ordered]@{
        state = $(if (Test-LivePid $process.Id) { 'started' } else { 'failed' })
        pid = $process.Id
        until = $Until.ToString('o')
    } | ConvertTo-Json -Compress
    exit 0
}

if ($Action -eq 'status') {
    $publisherPid = Get-FilePid $pidFile
    [ordered]@{
        enabled = Test-Path -LiteralPath $enabledFile
        alive = Test-LivePid $publisherPid
        pid = $publisherPid
        state = $(
            if (Test-Path -LiteralPath $stateFile) {
                Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
            } else { $null }
        )
    } | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq 'stop') {
    Remove-Item -LiteralPath $enabledFile -Force -ErrorAction SilentlyContinue
    $publisherPid = Get-FilePid $pidFile
    if (Test-LivePid $publisherPid) {
        Stop-Process -Id $publisherPid -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    '{"state":"stopped"}'
    exit 0
}

$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\HengbandCodexDumpPublisher', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

try {
    Set-Content -LiteralPath $pidFile -Value $PID -Encoding ascii
    Add-Event 'status' "Codex dump publisher started as PID $PID through $($Until.ToString('o'))."
    while ((Test-Path -LiteralPath $enabledFile) -and [DateTimeOffset]::Now -lt $Until) {
        try {
            if (-not (Test-Path -LiteralPath $Source)) {
                throw "Dump source is missing: $Source"
            }
            if (-not (Test-Path -LiteralPath $destination)) {
                throw "Publication destination is missing: $destination"
            }
            $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash
            $destinationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
            if ($sourceHash -eq $destinationHash) {
                Write-State 'synchronized' 'Source and publication copy are identical.'
            } else {
                Copy-Item -LiteralPath $Source -Destination $destination -Force
                & git -C $Worktree add live/bot-test.txt
                if ($LASTEXITCODE -ne 0) { throw "git add failed with exit code $LASTEXITCODE" }
                $sourceTime = (Get-Item -LiteralPath $Source).LastWriteTime.ToString('yyyy-MM-dd HH:mm')
                & git -C $Worktree commit -m "Update live dump $sourceTime JST"
                if ($LASTEXITCODE -ne 0) { throw "git commit failed with exit code $LASTEXITCODE" }
                $commit = (& git -C $Worktree rev-parse --short HEAD).Trim()
                & git -C $Worktree push origin codex/live-dump
                if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
                Write-State 'published' "Published changed live dump as $commit." $commit
                Add-Event 'status' "Codex published changed live dump as commit $commit."
            }
        } catch {
            Write-State 'error' $_.Exception.Message
            Add-Event 'question' "Codex dump publication failed: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 180
    }
    Write-State 'expired' "Publisher window ended at $($Until.ToString('o'))."
    Add-Event 'status' "Codex dump publisher reached its cutoff $($Until.ToString('o')) and stopped."
} finally {
    Remove-Item -LiteralPath $enabledFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
