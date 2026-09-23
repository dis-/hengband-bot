<#
.SYNOPSIS
    Run the supervision checker and escalate a sustained stall to the desktop.

.DESCRIPTION
    Designed to be run by a per-user scheduled task every five minutes, i.e.
    OUTSIDE any session, so that a session which has stopped waking up is still
    detected.  Raises a toast when

      * the SAME front has been stalled for at least -SustainedMinutes
        (repeated at most every -RepeatMinutes while it stays stalled), or
      * the in-session verdict file is older than -SessionVerdictMaxAgeMinutes,
        which means the session itself is gone.

    No notification tooling is installed on this host, so the toast goes
    through the WinRT ToastNotificationManager; when that fails the alert is
    written to a file instead.  Every alert is appended to alerts.log either
    way, so escalation is auditable.
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$StateDir = (Join-Path $env:LOCALAPPDATA 'hengbot-supervisor'),
    [string]$Python = '',
    [DateTimeOffset]$Now = [DateTimeOffset]::Now,
    [int]$SustainedMinutes = 15,
    [int]$RepeatMinutes = 60,
    [int]$SessionVerdictMaxAgeMinutes = 10,
    [switch]$NoToast
)

$ErrorActionPreference = 'Stop'
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

if (-not (Test-Path -LiteralPath $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
}
$StateDir = (Resolve-Path -LiteralPath $StateDir).ProviderPath
# Windows PowerShell's `Set-Content -Encoding utf8` prepends a UTF-8 BOM, which
# a reader on a cp932 console cannot even print.  Write UTF-8 without one.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-TextNoBom([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

function Resolve-Python {
    if ($Python) { return $Python }
    foreach ($candidate in @('python', 'python3', 'py')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    throw 'no python interpreter on PATH; pass -Python'
}

function Write-AlertLog([string]$Method, [string]$Front, [string]$Evidence) {
    $line = '{0} {1} {2}: {3}' -f $Now.ToString('o'), $Method, $Front, $Evidence
    [System.IO.File]::AppendAllText((Join-Path $StateDir 'alerts.log'),
        ($line + [Environment]::NewLine), $utf8NoBom)
}

function Send-Alert([string]$Front, [string]$Evidence) {
    $title = "Hengbot supervision: $Front stalled"
    $method = 'toast'
    if (-not $NoToast) {
        try {
            [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
            [void][Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime]
            $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
                [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $texts = $xml.GetElementsByTagName('text')
            $texts.Item(0).AppendChild($xml.CreateTextNode($title)) | Out-Null
            $texts.Item(1).AppendChild($xml.CreateTextNode($Evidence)) | Out-Null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
        } catch {
            $method = 'alert-file'
        }
    } else {
        $method = 'alert-file'
    }
    if ($method -eq 'alert-file') {
        $alerts = Join-Path $StateDir 'alerts'
        if (-not (Test-Path -LiteralPath $alerts)) { New-Item -ItemType Directory -Path $alerts -Force | Out-Null }
        $file = Join-Path $alerts ("alert-{0}-{1}.txt" -f $Now.ToString('yyyyMMdd-HHmmss'), $Front)
        Write-TextNoBom $file ((@("$title", "$Evidence") -join [Environment]::NewLine) +
            [Environment]::NewLine)
        Write-Output "ALERT-FILE $file"
    } else {
        Write-Output "TOAST $Front"
    }
    Write-AlertLog $method $Front $Evidence
}

function Get-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding utf8
        if (-not $raw) { return $null }
        # A file written by an older PowerShell carries a BOM that
        # ConvertFrom-Json rejects as an invalid primitive.
        return ($raw.TrimStart([char]0xFEFF) | ConvertFrom-Json)
    } catch { return $null }
}

# 1. Run the checker as the scheduled task, into its own verdict file.
#    Its stderr is captured: a checker that dies on its own input used to exit
#    1 - the same code as "a front is stalled" - leave last round's verdict
#    file behind, and be read as a verdict, so the crash was silent.
$checker = Join-Path $PSScriptRoot 'supervisor_check.py'
$interpreter = Resolve-Python
$checkerErrors = Join-Path $StateDir 'checker-stderr.txt'
if (Test-Path -LiteralPath $checkerErrors) { Remove-Item -LiteralPath $checkerErrors -Force }
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $interpreter $checker --root $Root --state-dir $StateDir --source task --quiet `
        --now $Now.ToString('o') 2>$checkerErrors | Out-Null
    $checkerExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
$checkerStderr = ''
if (Test-Path -LiteralPath $checkerErrors) {
    $checkerStderr = (Get-Content -LiteralPath $checkerErrors -Raw)
    if ($null -eq $checkerStderr) { $checkerStderr = '' }
    $checkerStderr = $checkerStderr.Trim()
}
$verdict = Get-JsonOrNull (Join-Path $StateDir 'verdict-task.json')

# The verdict has to be THIS round's: a crash after the file was written would
# otherwise be indistinguishable from a healthy run.
$verdictFresh = $false
if ($verdict -and $verdict.time) {
    try {
        $verdictAge = [Math]::Abs((($Now - [DateTimeOffset]::Parse($verdict.time))).TotalMinutes)
        $verdictFresh = ($verdictAge -le $SessionVerdictMaxAgeMinutes)
    } catch { $verdictFresh = $false }
}

$checkerFault = $null
if ($checkerExit -ne 0 -and $checkerExit -ne 1) {
    $checkerFault = "supervisor_check.py exited $checkerExit"
} elseif (-not $verdict) {
    $checkerFault = 'supervisor_check.py wrote no parsable verdict file'
} elseif (-not $verdictFresh) {
    $checkerFault = ("supervisor_check.py left a stale verdict (time={0})" -f $verdict.time)
} elseif ($checkerStderr) {
    $checkerFault = "supervisor_check.py wrote to stderr"
}
if ($checkerFault -and $checkerStderr) {
    # PowerShell wraps a native command's stderr in error records; their
    # decoration lines carry no information about the failure.
    $tail = ($checkerStderr -split "\r?\n" |
             Where-Object { $_.Trim() -and $_.Trim() -notmatch '^(\+|~|At line:)' } |
             Select-Object -Last 3) -join ' | '
    if ($tail) { $checkerFault = "{0}: {1}" -f $checkerFault, $tail }
}

# 2. Update the per-front stall clocks and escalate what has been sustained.
$statePath = Join-Path $StateDir 'notify-state.json'
$state = Get-JsonOrNull $statePath
$fronts = @{}
if ($state -and $state.fronts) {
    foreach ($property in $state.fronts.PSObject.Properties) {
        $fronts[$property.Name] = @{
            stalled_since = $property.Value.stalled_since
            last_toast    = $property.Value.last_toast
        }
    }
}

$script:alerts = 0
function Update-Front([string]$Name, [bool]$Ok, [string]$Evidence) {
    if ($Ok) {
        $fronts.Remove($Name) | Out-Null
        return
    }
    if (-not $fronts.ContainsKey($Name)) {
        $fronts[$Name] = @{ stalled_since = $Now.ToString('o'); last_toast = $null }
    }
    $since = [DateTimeOffset]::Parse($fronts[$Name].stalled_since)
    $sustained = ($Now - $since).TotalMinutes
    $lastToast = $fronts[$Name].last_toast
    $due = $true
    if ($lastToast) {
        $due = (($Now - [DateTimeOffset]::Parse($lastToast)).TotalMinutes -ge $RepeatMinutes)
    }
    if ($sustained -ge $SustainedMinutes -and $due) {
        Send-Alert $Name ("stalled for {0:N0} min: {1}" -f $sustained, $Evidence)
        $fronts[$Name].last_toast = $Now.ToString('o')
        $script:alerts += 1
    } else {
        $why = if ($sustained -lt $SustainedMinutes) {
            "stalled {0:N0} min (< {1})" -f $sustained, $SustainedMinutes
        } else {
            "stalled {0:N0} min, next repeat in {1:N0} min" -f $sustained,
                ($RepeatMinutes - ($Now - [DateTimeOffset]::Parse($lastToast)).TotalMinutes)
        }
        Write-Output ("HOLD {0} {1}: {2}" -f $Name, $why, $Evidence)
    }
}

# A broken checker is itself a stalled front: it is the mechanism that is
# supposed to notice a stall, so its silence must never pass for health.
Update-Front 'checker' (-not $checkerFault) ([string]$checkerFault)
if ($checkerFault) {
    Write-Output ("CHECKER-FAULT {0}" -f $checkerFault)
}
if ($verdict -and $verdictFresh) {
    foreach ($property in $verdict.fronts.PSObject.Properties) {
        Update-Front $property.Name ([bool]$property.Value.ok) ([string]$property.Value.evidence)
    }
} elseif (-not $verdict) {
    Write-Output 'NO-VERDICT the checker produced no verdict file'
}

# 3. A missing or stale in-session verdict means the session itself is gone.
$sessionVerdict = Join-Path $StateDir 'verdict-session.json'
$sessionAge = $null
if (Test-Path -LiteralPath $sessionVerdict) {
    $sessionAge = ($Now - [DateTimeOffset]((Get-Item -LiteralPath $sessionVerdict).LastWriteTime)).TotalMinutes
}
$sessionState = @{ last_toast = $null }
if ($state -and $state.session -and $state.session.last_toast) {
    $sessionState.last_toast = $state.session.last_toast
}
if ($null -eq $sessionAge -or $sessionAge -ge $SessionVerdictMaxAgeMinutes) {
    $due = $true
    if ($sessionState.last_toast) {
        $due = (($Now - [DateTimeOffset]::Parse($sessionState.last_toast)).TotalMinutes -ge $RepeatMinutes)
    }
    $evidence = if ($null -eq $sessionAge) { 'no in-session verdict file has ever been written' }
                else { "in-session verdict is {0:N0} min old" -f $sessionAge }
    if ($due) {
        Send-Alert 'session' $evidence
        $sessionState.last_toast = $Now.ToString('o')
        $alerts += 1
    } else {
        Write-Output "HOLD session $evidence"
    }
} else {
    $sessionState.last_toast = $null
}

$save = [ordered]@{ updated = $Now.ToString('o'); fronts = $fronts; session = $sessionState }
$temporary = "$statePath.$PID.tmp"
Write-TextNoBom $temporary (($save | ConvertTo-Json -Depth 6) + [Environment]::NewLine)
Move-Item -LiteralPath $temporary -Destination $statePath -Force

Write-Output ("NOTIFY-DONE alerts={0} stalled={1}" -f $alerts, (($verdict.stalled) -join ','))
exit 0
