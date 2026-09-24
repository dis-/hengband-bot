"""The Stop hook that refuses to end a turn on a report that is not Japanese.

User decision 2026-09-24: 「報告は日本語で。」  Every transcript here is a small
synthetic JSONL file in a temporary directory; no real transcript is read.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_language_guard.py"

JAPANESE_REPORT = (
    "セッション判定の修正を入れました（`f1b1d16`）。原因は MSIX の書き込みリダイレクトで、"
    "`scripts/supervisor_notify.ps1` が "
    r"C:\Users\user\AppData\Local\hengbot-supervisor\verdict-session.json"
    " を見つけられず、毎時「一度も書かれていない」と通知していました。\n\n"
    "- 検証: `python -m unittest tests.test_supervisor_check` → Ran 44 tests OK\n"
    "- revert-proof: 親 f7e80d2 に戻すと V1 が落ちることを確認\n"
    "- 詳細は https://example.invalid/review/123 と src/hengbot/policy.py の "
    "`_close_store_visit()` を参照。\n"
    "```\nTraceback (most recent call last):\n  File \"x.py\", line 1\n```\n"
)
ENGLISH_REPORT = (
    "Fixed the session verdict lookup. The scheduled task never saw the file because "
    "the packaged app redirects its writes, so it raised the same alert every hour. "
    "I added tests for the fresh, stale, missing and fault cases, and all of them pass."
)


def assistant(*blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"role": "assistant", "content": list(blocks)}}


def text(value):
    return {"type": "text", "text": value}


def user_prompt(value):
    return {"type": "user", "message": {"role": "user", "content": value}}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_x", "content": "ok"}]}}


class ReportLanguageGuardTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="report-language-guard-"))
        self.root = self.directory / "root"
        (self.root / "jsonlog").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def transcript(self, *entries) -> Path:
        path = self.directory / "transcript.jsonl"
        path.write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n"
                                for entry in entries), encoding="utf-8")
        return path

    def run_guard(self, payload) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root)],
            input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=60)

    def stop(self, path, active=False):
        return {"session_id": "s", "transcript_path": str(path),
                "hook_event_name": "Stop", "stop_hook_active": active}

    def test_a_japanese_report_with_paths_hashes_and_code_passes(self):
        path = self.transcript(user_prompt("報告して"), assistant(text(JAPANESE_REPORT)))
        run = self.run_guard(self.stop(path))
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))

    def test_an_english_report_is_blocked_with_a_japanese_message(self):
        path = self.transcript(user_prompt("報告して"), assistant(text(ENGLISH_REPORT)))
        run = self.run_guard(self.stop(path))
        self.assertEqual(run.returncode, 2)
        message = run.stderr.decode("utf-8")
        self.assertIn("日本語で書き直してください", message)
        self.assertIn("報告は日本語で。", message)

    def test_the_blocking_message_is_utf8_whatever_the_console_codec(self):
        """Claude Code decodes hook stderr as UTF-8; cp932 bytes arrive garbled."""
        path = self.transcript(user_prompt("報告して"), assistant(text(ENGLISH_REPORT)))
        base = {key: value for key, value in os.environ.items()
                if key not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        for label, extra in (("unset", {}),
                             ("cp932", {"PYTHONIOENCODING": "cp932"}),
                             ("utf8-mode-off", {"PYTHONUTF8": "0",
                                                "PYTHONIOENCODING": "cp932:strict"})):
            with self.subTest(environment=label):
                run = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(self.root)],
                    input=json.dumps(self.stop(path)).encode("utf-8"),
                    capture_output=True, timeout=60, env=dict(base, **extra))
                self.assertEqual(run.returncode, 2)
                message = run.stderr.decode("utf-8")  # strict: mojibake raises
                self.assertIn("日本語で書き直してください", message)
                self.assertIn("報告は日本語で。", message)

    def test_the_fail_open_note_is_utf8_whatever_the_console_codec(self):
        """The note quotes the OS error, which names a possibly Japanese path."""
        missing = self.directory / "報告の記録.jsonl"
        base = {key: value for key, value in os.environ.items()
                if key not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        for label, extra in (("unset", {}), ("cp932", {"PYTHONIOENCODING": "cp932"})):
            with self.subTest(environment=label):
                run = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(self.root)],
                    input=json.dumps(self.stop(missing)).encode("utf-8"),
                    capture_output=True, timeout=60, env=dict(base, **extra))
                self.assertEqual(run.returncode, 0)
                note = run.stderr.decode("utf-8")  # strict: cp932 bytes raise
                self.assertIn("not checking", note)
                self.assertIn("報告の記録.jsonl", note)

    def test_a_short_message_under_the_minimum_passes(self):
        path = self.transcript(user_prompt("状況は？"), assistant(text("Pushed. All green.")))
        run = self.run_guard(self.stop(path))
        self.assertEqual(run.returncode, 0)

    def test_stop_hook_active_never_blocks_again(self):
        path = self.transcript(user_prompt("報告して"), assistant(text(ENGLISH_REPORT)))
        run = self.run_guard(self.stop(path, active=True))
        self.assertEqual(run.returncode, 0)

    def test_the_kill_switch_disables_the_guard(self):
        (self.root / "jsonlog" / "turn-end-guard.disabled").write_text("", encoding="utf-8")
        path = self.transcript(user_prompt("報告して"), assistant(text(ENGLISH_REPORT)))
        run = self.run_guard(self.stop(path))
        self.assertEqual(run.returncode, 0)

    def test_an_unreadable_transcript_fails_open_with_a_note(self):
        for path in (self.directory / "missing.jsonl", self.directory):
            with self.subTest(path=str(path)):
                run = self.run_guard(self.stop(path))
                self.assertEqual(run.returncode, 0)
                self.assertIn("not checking", run.stderr.decode("utf-8", "replace"))

    def test_garbage_on_stdin_fails_open(self):
        run = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root)],
                             input=b"not json", capture_output=True, timeout=60)
        self.assertEqual(run.returncode, 0)
        self.assertIn(b"not checking", run.stderr)

    def test_only_the_final_message_after_the_last_tool_result_counts(self):
        # English narration before a tool call, Japanese report at the end.
        passing = self.transcript(
            user_prompt("報告して"), assistant(text(ENGLISH_REPORT)),
            assistant({"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": {}}),
            tool_result(), assistant(text(JAPANESE_REPORT)))
        self.assertEqual(self.run_guard(self.stop(passing)).returncode, 0)
        # Japanese earlier in the turn does not excuse an English ending.
        failing = self.transcript(
            user_prompt("報告して"), assistant(text(JAPANESE_REPORT)),
            assistant({"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": {}}),
            tool_result(), assistant(text(ENGLISH_REPORT)))
        self.assertEqual(self.run_guard(self.stop(failing)).returncode, 2)

    def test_thinking_and_tool_input_are_not_measured(self):
        path = self.transcript(
            user_prompt("報告して"),
            assistant({"type": "thinking", "thinking": ENGLISH_REPORT * 3},
                      {"type": "tool_use", "id": "t", "name": "Bash",
                       "input": {"command": ENGLISH_REPORT}}),
            assistant(text(JAPANESE_REPORT)))
        self.assertEqual(self.run_guard(self.stop(path)).returncode, 0)

    def test_a_multi_block_final_message_is_measured_as_a_whole(self):
        path = self.transcript(
            user_prompt("報告して"),
            assistant(text(ENGLISH_REPORT[:120])), assistant(text(ENGLISH_REPORT[120:])))
        self.assertEqual(self.run_guard(self.stop(path)).returncode, 2)


if __name__ == "__main__":
    unittest.main()
