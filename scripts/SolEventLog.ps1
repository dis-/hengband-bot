# Validated appender for jsonlog\sol-events.jsonl (dot-source this file).
#
# Writes exactly one JSON object per line as UTF-8 without a BOM, terminated by
# "`n", and repairs a missing final newline before appending (the cause of two
# objects landing on one line).  Mirrors src/hengbot/sol_events.py; the file is
# checked by tests/test_sol_events_hygiene.py.

function Add-SolEventLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Record
    )
    if ($Record -is [string]) { $line = $Record.Trim() }
    else { $line = $Record | ConvertTo-Json -Compress -Depth 16 }
    if ($line -match "[`r`n]") { throw "sol event must be a single line" }
    try { $parsed = $line | ConvertFrom-Json }
    catch { throw "sol event is not valid JSON: $($_.Exception.Message)" }
    if ($null -eq $parsed -or $parsed -isnot [System.Management.Automation.PSCustomObject]) {
        throw 'sol event must be a JSON object'
    }
    $body = [System.Text.UTF8Encoding]::new($false).GetBytes($line + "`n")
    try {
        $stream = [System.IO.FileStream]::new(
            $Path, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::ReadWrite)
    } catch [System.Management.Automation.MethodInvocationException] {
        # Surface the IOException itself so callers can retry on it by type.
        if ($_.Exception.InnerException) { throw $_.Exception.InnerException }
        throw
    }
    try {
        if ($stream.Length -gt 0) {
            [void]$stream.Seek(-1, [System.IO.SeekOrigin]::End)
            if ($stream.ReadByte() -ne 10) { $stream.WriteByte(10) }
        }
        [void]$stream.Seek(0, [System.IO.SeekOrigin]::End)
        $stream.Write($body, 0, $body.Length)
    } finally {
        $stream.Dispose()
    }
}
