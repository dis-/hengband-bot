<#
    Resume ONLY the bot against an already-running Hengband, WITHOUT
    --capture-home-entry.

    The hengband-bot-play skill passes --capture-home-entry unconditionally
    (its start and resume paths both do).  On 2026-09-10 that diagnostic wrote
    ~15 MB/s (a ~4.5 MB pickled policy checkpoint plus a ~2.2 MB pickled
    snapshot per decision) and pushed jsonlog to 7.2 GB in ten minutes, past
    the hard 5 GB budget.  Until that capture is gated, resume with this.

    The game process is never touched.
#>
param(
    [string]$BotRoot = 'C:\hengband\bot-client',
    [int]$GamePid = 0
)

$ErrorActionPreference = 'Stop'
$logRoot = Join-Path $BotRoot 'jsonlog'

if (Test-Path -LiteralPath (Join-Path $logRoot 'maintenance.hold')) {
    throw 'maintenance.hold exists: an investigation owns the stopped bot. Remove it deliberately first.'
}

if ($GamePid -eq 0) {
    $games = @(Get-Process Hengband -ErrorAction SilentlyContinue)
    if ($games.Count -ne 1) { throw "expected exactly one Hengband process, found $($games.Count)" }
    $GamePid = $games[0].Id
}
$game = Get-Process -Id $GamePid

$existing = Get-Content -LiteralPath (Join-Path $logRoot 'bot.pid') -Raw -ErrorAction SilentlyContinue
if ($existing) {
    $existing = $existing.Trim()
    if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
        throw "the bot is already running with PID $existing"
    }
}

$stateFile = Join-Path $logRoot 'bot-state-fixed.jsonl'
$decisionLog = Join-Path $logRoot 'bot-decisions.jsonl'
$root = Split-Path -Parent $game.Path
$monrace = Join-Path $root 'lib\edit\MonraceDefinitions.jsonc'
$outpost = Join-Path $root 'lib\edit\towns\01_Outpost_Full.txt'
$dungeon = Join-Path $root 'lib\edit\DungeonDefinitions.jsonc'
foreach ($p in @($stateFile, $monrace, $outpost, $dungeon)) {
    if (-not (Test-Path -LiteralPath $p)) { throw "missing: $p" }
}

$python = (Get-Command python).Source
$env:PYTHONPATH = Join-Path $BotRoot 'src'
$common = @(
    '-m', 'hengbot',
    '--state-file', $stateFile,
    '--decision-log', $decisionLog,
    '--monrace-definitions', $monrace,
    '--outpost-map', $outpost,
    '--dungeon-definitions', $dungeon,
    '--control-port', '47820',
    '--send-to-window',
    '--window-pid', $GamePid
)

$bot = Start-Process -FilePath $python -ArgumentList $common `
    -WorkingDirectory $BotRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logRoot 'bot-stdout.log') `
    -RedirectStandardError (Join-Path $logRoot 'bot-stderr.log')
Set-Content -LiteralPath (Join-Path $logRoot 'bot.pid') -Value $bot.Id -NoNewline
Start-Sleep -Seconds 2
if (-not (Get-Process -Id $bot.Id -ErrorAction SilentlyContinue)) {
    throw "the bot exited immediately; inspect $(Join-Path $logRoot 'bot-stderr.log')"
}

# Continuous follow seeks to EOF, so release the game from the snapshot that is
# already waiting for player input.
& $python @common --once
if ($LASTEXITCODE -ne 0) { throw "the resume one-shot decision failed with exit code $LASTEXITCODE" }

"game PID $GamePid / bot PID $($bot.Id) (no --capture-home-entry)"
