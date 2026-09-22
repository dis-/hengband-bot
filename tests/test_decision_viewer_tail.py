import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "scripts" / "watch-decisions.ps1"
TAIL_HELPER = ROOT / "scripts" / "DecisionLogTail.ps1"

POWERSHELL = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]

# Runs the viewer's own poll read: its dot-sourced helpers and the first
# statement of its timer tick (the `$line = ...` read), taken from its AST.
VIEWER_POLL_PROBE = r"""
param([string]$Viewer, [string]$Log, [string]$Out)
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Viewer, [ref]$null, [ref]$null)
$scriptsDir = Split-Path -Parent $Viewer
foreach ($command in $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot
    }, $false)) {
    . (Invoke-Expression ($command.CommandElements[0].Extent.Text.Replace('$PSScriptRoot', "'$scriptsDir'")))
}
$tick = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.InvokeMemberExpressionAst] -and
        $node.Member.Value -eq 'Add_Tick'
    }, $true)
$read = $tick.Arguments[0].ScriptBlock.EndBlock.Statements[0]
$DecisionLog = $Log
$ErrorActionPreference = 'Continue'
Invoke-Expression $read.Extent.Text
[System.IO.File]::WriteAllText($Out, (@{ line = $line } | ConvertTo-Json -Compress),
    [System.Text.UTF8Encoding]::new($false))
"""

# While the helper's handle is open, a separate Python process performs the
# rename rotate_log performs.  The contrast handle is opened the way
# Get-Content opens the log (ReadWrite sharing, no Delete).
HELPER_RENAME_PROBE = r"""
param([string]$Helper, [string]$Log, [string]$Python, [string]$Out)
. $Helper
$rename = "import os, sys; os.replace(sys.argv[1], sys.argv[2])"
$result = [ordered]@{}
$stream = Open-SharedLogStream $Log
try {
    & $Python -c $rename $Log "$Log.1" 2>$null
    $result.rename_while_viewer_handle_open = $LASTEXITCODE
} finally { $stream.Dispose() }
$result.rotated_exists = Test-Path -LiteralPath "$Log.1"
Move-Item -LiteralPath "$Log.1" -Destination $Log
$legacy = [System.IO.FileStream]::new($Log, [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
try {
    & $Python -c $rename $Log "$Log.2" 2>$null
    $result.rename_while_legacy_handle_open = $LASTEXITCODE
} finally { $legacy.Dispose() }
$result.missing_file = Read-LastLogLine "$Log.missing"
[System.IO.File]::WriteAllText($Out, ($result | ConvertTo-Json -Compress),
    [System.Text.UTF8Encoding]::new($false))
"""


def _open_with_delete_access(path):
    """Hold ``path`` the way a pending rename does: DELETE access, full sharing.

    A later open that does not share Delete fails with a sharing violation,
    so a reader that would block the bot's rotation cannot read the file.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    delete, share_all, open_existing = 0x00010000, 0x7, 3
    handle = kernel32.CreateFileW(str(path), delete, share_all, None, open_existing, 0, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return lambda: kernel32.CloseHandle(handle)


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows share modes")
class DecisionViewerTailTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="viewer-tail-test-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.log = self.directory / "bot-decisions.jsonl"
        self.last = json.dumps({"turn": 3, "reason": "吸" + "x" * 150_000}, ensure_ascii=False)
        self.log.write_bytes(
            (json.dumps({"turn": 1}) + "\n" + json.dumps({"turn": 2}) + "\n" + self.last + "\n")
            .encode("utf-8")
        )

    def _run(self, probe_source, *arguments):
        probe = self.directory / "probe.ps1"
        probe.write_text(probe_source, encoding="utf-8")
        out = self.directory / "result.json"
        completed = subprocess.run(
            [*POWERSHELL, str(probe), *arguments, "-Out", str(out)],
            capture_output=True, timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_viewer_poll_reads_the_last_line_while_the_log_is_being_renamed(self):
        release = _open_with_delete_access(self.log)
        try:
            result = self._run(VIEWER_POLL_PROBE, "-Viewer", str(VIEWER), "-Log", str(self.log))
        finally:
            release()
        self.assertEqual(result["line"], self.last)

    def test_viewer_handle_does_not_block_rotation_rename(self):
        result = self._run(
            HELPER_RENAME_PROBE, "-Helper", str(TAIL_HELPER), "-Log", str(self.log),
            "-Python", sys.executable,
        )
        self.assertEqual(result["rename_while_viewer_handle_open"], 0)
        self.assertTrue(result["rotated_exists"])
        self.assertNotEqual(result["rename_while_legacy_handle_open"], 0)
        self.assertIsNone(result["missing_file"])


if __name__ == "__main__":
    unittest.main()
