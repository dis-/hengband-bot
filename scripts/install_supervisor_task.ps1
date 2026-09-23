<#
.SYNOPSIS
    Register (or remove) the per-user scheduled task that escalates stalls.

.DESCRIPTION
    Escalation has to live outside the session: an in-session chain dies with
    the session it is supposed to watch.  This registers a per-user task - no
    elevation, interactive logon so the toast reaches the desktop - that runs
    scripts/supervisor_notify.ps1 every -IntervalMinutes.

    Idempotent: re-running it replaces the registration and prints what it
    registered.  -Uninstall removes it.
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'HengbotSupervisorCheck',
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$IntervalMinutes = 5,
    [string]$Python = '',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Uninstall) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "UNREGISTERED $TaskName"
    } else {
        Write-Output "NOT-REGISTERED $TaskName (nothing to remove)"
    }
    exit 0
}

# The task must outlive the worktree it was installed from, so it always names
# the checkout given by -Root, never $PSScriptRoot.
$notify = Join-Path (Join-Path $Root 'scripts') 'supervisor_notify.ps1'
if (-not (Test-Path -LiteralPath $notify)) {
    Write-Warning "$notify does not exist yet; registering the task against the path it will occupy once the change is merged into $Root."
}

$argumentList = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', "`"$notify`"", '-Root', "`"$Root`""
)
if ($Python) { $argumentList += @('-Python', "`"$Python`"") }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ($argumentList -join ' ') -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At ([DateTime]::Now.AddMinutes(1))
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ([DateTime]::Now.AddMinutes(1)) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
# Interactive logon, current user: no elevation, and the toast reaches the desktop.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force `
    -Description 'Hengbot supervision: check the bot/measurement/review fronts and escalate a sustained stall to the desktop.' | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName
Write-Output "REGISTERED $TaskName state=$($registered.State) every ${IntervalMinutes}m"
Write-Output "  action : powershell.exe $($argumentList -join ' ')"
Write-Output "  user   : $env:USERDOMAIN\$env:USERNAME (Interactive, Limited)"
Write-Output "  root   : $Root"
exit 0
