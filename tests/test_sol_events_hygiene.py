import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from hengbot.home_disposal import HomeDisposalCandidate, HomeDisposalState
from hengbot.sol_events import (
    InvalidEventError,
    append_event,
    format_problems,
    invalid_lines,
)


ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "jsonlog" / "sol-events.jsonl"
APPEND_SCRIPT = ROOT / "scripts" / "append_sol_event.py"
POWERSHELL_APPENDER = ROOT / "scripts" / "SolEventLog.ps1"


class SolEventLogFileTest(unittest.TestCase):
    """The tracked event log holds one JSON object per line, nothing else."""

    def test_every_line_of_the_event_log_is_a_json_object(self):
        # Read-only: the file is tracked, so every checkout (and worktree) has it.
        self.assertTrue(EVENT_LOG.exists(), EVENT_LOG)
        problems = invalid_lines(EVENT_LOG.read_bytes())
        self.assertEqual(problems, [], "\n" + format_problems(problems))

    def test_checker_rejects_the_shapes_that_broke_the_log(self):
        cases = {
            "concatenated": b'{"a":1}{"b":2}\n',
            "invalid escape": b'{"tail":"3q\\x1b"}\n',
            "mojibake swallowed quote": '{"ja":"吸収した！E,"en":"x"}\n'.encode("utf-8"),
            "missing trailing newline": b'{"a":1}\n{"b":2}',
            "blank line": b'{"a":1}\n\n{"b":2}\n',
            "not an object": b'[1,2]\n',
            "not utf-8": '{"a":"吸"}\n'.encode("cp932"),
            "byte order mark": b'\xef\xbb\xbf{"a":1}\n',
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.assertNotEqual(invalid_lines(data), [])
        self.assertEqual(invalid_lines(b'{"a":1}\n{"b":"\xe5\x90\xb8"}\n'), [])
        self.assertEqual(invalid_lines(b""), [])


class AppendEventTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="sol-events-test-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.log = self.directory / "sol-events.jsonl"

    def test_appends_one_utf8_line_per_event(self):
        append_event(self.log, {"type": "fix", "detail": "吸収"})
        append_event(self.log, '{"type": "status"}')
        data = self.log.read_bytes()
        self.assertEqual(data, '{"type":"fix","detail":"吸収"}\n{"type":"status"}\n'.encode("utf-8"))
        self.assertEqual(invalid_lines(data), [])

    def test_missing_final_newline_is_repaired_instead_of_concatenating(self):
        self.log.write_bytes(b'{"type":"old"}')
        append_event(self.log, {"type": "new"})
        self.assertEqual(self.log.read_bytes(), b'{"type":"old"}\n{"type":"new"}\n')

    def test_invalid_events_are_refused_without_writing(self):
        self.log.write_bytes(b'{"type":"old"}\n')
        for event in ('{"a":1}{"b":2}', '{"tail":"3q\\x1b"}', "[1]", 7, {"x": float("nan")}):
            with self.subTest(event=event), self.assertRaises(InvalidEventError):
                append_event(self.log, event)
        self.assertEqual(self.log.read_bytes(), b'{"type":"old"}\n')

    def test_cli_appends_and_refuses(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        event = self.directory / "event.json"
        event.write_text('{"type":"fix","detail":"吸収"}', encoding="utf-8")
        accepted = subprocess.run(
            [sys.executable, str(APPEND_SCRIPT), "--log", str(self.log), "--file", str(event)],
            capture_output=True, env=env, timeout=60,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = subprocess.run(
            [sys.executable, str(APPEND_SCRIPT), "--log", str(self.log), "--json", '{"a":1}{"b":2}'],
            capture_output=True, env=env, timeout=60,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(self.log.read_bytes(), '{"type":"fix","detail":"吸収"}\n'.encode("utf-8"))
        checked = subprocess.run(
            [sys.executable, str(APPEND_SCRIPT), "--log", str(self.log), "--check"],
            capture_output=True, env=env, timeout=60,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell")
    def test_powershell_appender_writes_valid_utf8_lines(self):
        self.log.write_bytes(b'{"type":"old"}')
        script = self.directory / "append.ps1"
        script.write_text(
            "param([string]$Appender, [string]$Log)\n"
            ". $Appender\n"
            "$record = [ordered]@{ time = '2026-09-23T00:00:00+09:00'; type = 'status';"
            " detail = [string][char]0x5438 }\n"
            "Add-SolEventLine -Path $Log -Record ($record | ConvertTo-Json -Compress)\n"
            "try { Add-SolEventLine -Path $Log -Record '{\"a\":1}{\"b\":2}'; exit 3 }\n"
            "catch { exit 0 }\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-Appender", str(POWERSHELL_APPENDER), "-Log", str(self.log),
            ],
            capture_output=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.log.read_bytes()
        self.assertEqual(invalid_lines(data), [], data)
        lines = data.decode("utf-8").splitlines()
        self.assertEqual(json.loads(lines[0]), {"type": "old"})
        self.assertEqual(json.loads(lines[1])["detail"], "吸")
        self.assertEqual(len(lines), 2)


# Runs a writer script's own Add-Event function (taken from its AST, together
# with the script's dot-sourced helpers) against a scratch event log.
WRITER_PROBE = r"""
param([string]$Script, [string]$Log)
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$null)
$scriptsDir = Split-Path -Parent $Script
foreach ($command in $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot
    }, $false)) {
    . (Invoke-Expression ($command.CommandElements[0].Extent.Text.Replace('$PSScriptRoot', "'$scriptsDir'")))
}
$function = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Add-Event'
    }, $true)
Invoke-Expression $function.Extent.Text
$eventsFile = $Log
Add-Event 'status' ('probe ' + [string][char]0x5438)
"""


class EventWritersUseTheAppenderTest(unittest.TestCase):
    """In-repo writers keep the log valid even after a newline-less append."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="sol-event-writers-"))
        self.addCleanup(shutil.rmtree, self.directory, True)

    def test_home_disposal_question_event_keeps_the_log_valid(self):
        root = self.directory
        log = root / "jsonlog" / "sol-events.jsonl"
        log.parent.mkdir(parents=True)
        log.write_bytes(b'{"type":"handwritten"}')
        state = HomeDisposalState.in_repo(root)
        potion = HomeDisposalCandidate(("a Potion", 75, 3), "a Potion", 75, 3, 1, False, False)
        state.emit_queue([potion], 321)
        data = log.read_bytes()
        self.assertEqual(invalid_lines(data), [], data)
        lines = data.decode("utf-8").splitlines()
        self.assertEqual(json.loads(lines[0]), {"type": "handwritten"})
        self.assertEqual(json.loads(lines[1])["event"], "question")

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell")
    def test_powershell_writer_scripts_keep_the_log_valid(self):
        probe = self.directory / "writer-probe.ps1"
        probe.write_text(WRITER_PROBE, encoding="utf-8")
        for name in ("sol-supervisor.ps1", "codex-dump-publisher.ps1"):
            with self.subTest(name):
                log = self.directory / f"{name}.jsonl"
                log.write_bytes(b'{"type":"handwritten"}')
                result = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", str(probe), "-Script", str(ROOT / "scripts" / name), "-Log", str(log),
                    ],
                    capture_output=True, timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                data = log.read_bytes()
                self.assertEqual(invalid_lines(data), [], data)
                lines = data.decode("utf-8").splitlines()
                self.assertEqual(len(lines), 2)
                self.assertEqual(json.loads(lines[1])["detail"], "probe 吸")


if __name__ == "__main__":
    unittest.main()
