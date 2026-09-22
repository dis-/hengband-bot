# Tail reader for the decision log (dot-sourced by watch-decisions.ps1).
#
# Get-Content -Tail opens the log without FILE_SHARE_DELETE and, on a large
# file, holds that handle long enough for the bot's rotation rename to fail
# with WinError 32.  These helpers open the file with ReadWrite|Delete sharing,
# read only a chunk near the end, and close before returning, so a rename or
# delete by the writer is never blocked and no handle survives between polls.

function Open-SharedLogStream([string]$Path) {
    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    return [System.IO.FileStream]::new(
        $Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, $share)
}

function Read-LastLogLine([string]$Path, [int]$InitialChunkBytes = 65536) {
    try { $stream = Open-SharedLogStream $Path }
    catch { return $null }
    try {
        $length = $stream.Length
        $chunk = [long]$InitialChunkBytes
        while ($length -gt 0) {
            $start = [Math]::Max([long]0, $length - $chunk)
            $count = [int]($length - $start)
            $buffer = New-Object byte[] $count
            [void]$stream.Seek($start, [System.IO.SeekOrigin]::Begin)
            $read = 0
            while ($read -lt $count) {
                $got = $stream.Read($buffer, $read, $count - $read)
                if ($got -le 0) { break }
                $read += $got
            }
            $end = $read
            while ($end -gt 0 -and ($buffer[$end - 1] -eq 10 -or $buffer[$end - 1] -eq 13)) { $end-- }
            $newline = -1
            for ($index = $end - 1; $index -ge 0; $index--) {
                if ($buffer[$index] -eq 10) { $newline = $index; break }
            }
            if ($newline -ge 0 -or $start -eq 0) {
                $begin = $newline + 1
                return [System.Text.Encoding]::UTF8.GetString($buffer, $begin, $end - $begin)
            }
            $chunk *= 2
        }
        return $null
    }
    finally {
        $stream.Dispose()
    }
}
