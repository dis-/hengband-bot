[CmdletBinding()]
param(
    [string]$DecisionLog = "C:\hengband\bot-client\jsonlog\bot-decisions.jsonl",
    [string]$BotPidFile = "C:\hengband\bot-client\jsonlog\bot.pid"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Format-Key([string]$Key) {
    if ($null -eq $Key) { return "" }
    return $Key.Replace("`e", "<Esc>").Replace("`r", "<Return>").Replace("`n", "<LF>")
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Hengbot - Current Policy Decision"
$form.Size = New-Object System.Drawing.Size(760, 620)
$form.MinimumSize = New-Object System.Drawing.Size(600, 420)
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 28, 34)

$view = New-Object System.Windows.Forms.RichTextBox
$view.Dock = [System.Windows.Forms.DockStyle]::Fill
$view.ReadOnly = $true
$view.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$view.BackColor = $form.BackColor
$view.ForeColor = [System.Drawing.Color]::Gainsboro
$view.Font = New-Object System.Drawing.Font("Consolas", 13)
$view.Margin = New-Object System.Windows.Forms.Padding(18)
$view.Text = "Waiting for the first policy decision..."
$form.Controls.Add($view)

$script:lastLine = $null
$script:lastBotRunning = $null
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 500
$timer.Add_Tick({
    $line = Get-Content -LiteralPath $DecisionLog -Tail 1 -ErrorAction SilentlyContinue
    $botPid = Get-Content -LiteralPath $BotPidFile -Raw -ErrorAction SilentlyContinue
    $botRunning = $false
    if ($botPid) {
        $botRunning = $null -ne (Get-Process -Id ([int]$botPid.Trim()) -ErrorAction SilentlyContinue)
    }
    if (-not $line -or ($line -eq $script:lastLine -and $botRunning -eq $script:lastBotRunning)) {
        return
    }

    $script:lastLine = $line
    $script:lastBotRunning = $botRunning
    try {
        $decision = $line | ConvertFrom-Json
        $botState = if ($botRunning) { "RUNNING" } else { "STOPPED" }
        $status = if ($decision.player.status.Count -gt 0) {
            $decision.player.status -join ", "
        } else {
            "none"
        }
        $store = if ($null -ne $decision.store_type) {
            "Store type $($decision.store_type)"
        } else {
            "outside store"
        }
        $requirements = @($decision.procurement_requirements | ForEach-Object {
            "  - $($_.item): $($_.current)/$($_.target)  (need $($_.missing))"
        })
        $requirementsText = if ($requirements.Count -gt 0) {
            $requirements -join "`r`n"
        } else {
            "  none"
        }
        $view.Text = @"
HENGBOT CURRENT POLICY

Bot       : $botState
Updated   : $($decision.time)

OBJECTIVE : $($decision.objective)
REASON    : $($decision.reason)
NEXT KEY  : $(Format-Key $decision.key)

Turn      : $($decision.turn)
Location  : dungeon $($decision.floor.dungeon_id), floor $($decision.floor.level), ($($decision.position.y),$($decision.position.x))
Player    : CLv $($decision.player.level)  HP $($decision.player.hp)/$($decision.player.max_hp)  MP $($decision.player.mp)/$($decision.player.max_mp)
Resources : gold $($decision.player.gold)  food $($decision.player.food_state)
Pack      : $($decision.inventory.used)/23 used  ($($decision.inventory.free) free)
Threats   : $($decision.visible_hostiles) visible hostiles  |  $status
Context   : $store

PROCUREMENT REQUIREMENTS
$requirementsText
"@
        $view.SelectionStart = 0
        $view.SelectionLength = 22
        $view.SelectionColor = [System.Drawing.Color]::DeepSkyBlue
        $view.SelectionLength = 0
    }
    catch {
        $view.Text = "Waiting for a complete decision record..."
    }
})

$form.Add_FormClosed({ $timer.Stop() })
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
