param(
    [string]$BotRoot = 'C:\hengband\bot-client'
)

$ErrorActionPreference = 'Continue'
$runtime = Join-Path $BotRoot 'jsonlog'
$prompt = Join-Path $BotRoot 'SOL-OPERATOR-BRIEF.md'
$stdout = Join-Path $runtime 'sol-operator.log'
$stderr = Join-Path $runtime 'sol-operator.err.log'

# LANDMINE: multi-line text passed as a codex.cmd ARGUMENT gets mangled by the
# .cmd shim (newlines split the argv) - codex then sees an empty/fragmented
# prompt and replies "Ready, send the operation" before exiting (generations
# 2-14). Compose the full prompt into a FILE and pass a single-line pointer,
# the same shape as every dispatch that has worked.
$instruction = @'
You are the bot operator for ONE supervised iteration. Do not ask for
instructions and do not wait for input - act now, autonomously:
(1) Assess the session: game/bot PIDs under jsonlog (hengband.pid, bot.pid),
    log freshness (bot-state-fixed.jsonl / bot-decisions.jsonl mtimes),
    bot-stderr.log tail.
(2) If the bot is STOPPED while the game runs, resume ONLY the bot via the
    hengband-bot-play skill (never restart or kill the game). Code fixes for
    past incidents are already committed on main - the restart loads them;
    do not re-diagnose old, already-fixed loop messages.
(3) Monitor roughly 20 minutes per the brief's watch items (loops, danger,
    stderr watchdog dumps, economy progress).
(4) Append start/status events with concrete numbers to
    jsonlog\sol-events.jsonl, then exit; the supervisor relaunches you.
The operator contract follows.

'@
$composed = Join-Path $runtime 'operator-prompt.txt'
Set-Content -LiteralPath $composed -Encoding utf8 -Value ($instruction + (Get-Content -Raw $prompt))
& 'C:\Users\user\node-portable\node-v24.17.0-win-x64\codex.cmd' exec `
    --ignore-user-config -m gpt-5.6-sol -s danger-full-access `
    -C $BotRoot --skip-git-repo-check `
    "Read C:\hengband\bot-client\jsonlog\operator-prompt.txt and follow it exactly, acting autonomously now." `
    1>> $stdout 2>> $stderr
exit $LASTEXITCODE
