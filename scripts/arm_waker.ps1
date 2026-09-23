<#
.SYNOPSIS
    Arm the one in-session waker and leave a marker on disk.

.DESCRIPTION
    Writes jsonlog/waker.json and then sleeps, so that "a waker is armed" is a
    fact both the turn-end guard and the scheduled checker can read, instead of
    something the session claims about itself.  Run it in the background: its
    exit is the wake-up.

    This is the only file this supervision round writes under jsonlog/.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int]$Seconds,
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Note = ''
)

$ErrorActionPreference = 'Stop'

$runtime = Join-Path $Root 'jsonlog'
if (-not (Test-Path -LiteralPath $runtime)) {
    New-Item -ItemType Directory -Path $runtime | Out-Null
}
$armedAt = [DateTimeOffset]::Now
$marker = [ordered]@{
    armed_at = $armedAt.ToString('o')
    due_at   = $armedAt.AddSeconds($Seconds).ToString('o')
    pid      = $PID
    seconds  = $Seconds
    note     = $Note
}
$path = Join-Path $runtime 'waker.json'
$temporary = "$path.$PID.tmp"
($marker | ConvertTo-Json -Compress) | Set-Content -LiteralPath $temporary -Encoding utf8
Move-Item -LiteralPath $temporary -Destination $path -Force
Write-Output "WAKER-ARMED $($marker.due_at) pid=$PID seconds=$Seconds"

Start-Sleep -Seconds $Seconds
Write-Output "WAKER-DUE $([DateTimeOffset]::Now.ToString('o'))"
