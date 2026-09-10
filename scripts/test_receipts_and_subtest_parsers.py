"""Self-tests for subTest attribution and execution receipts."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import hunk_guard
import failure_headers
import mutation_battery
import test_parallel_runner
import run_receipt
import verify_receipt
import verify_scope


HEADERS = """FAIL: test_plain (tests.test_demo.DemoTest.test_plain)
FAIL: test_paren (tests.test_demo.DemoTest.test_paren) (case='p')
ERROR: test_bracket (tests.test_demo.DemoTest.test_bracket) [message]
FAIL: test_both (tests.test_demo.DemoTest.test_both) [message] (case='b')
"""
IDENTITIES = [
    "tests.test_demo.DemoTest.test_plain",
    "tests.test_demo.DemoTest.test_paren",
    "tests.test_demo.DemoTest.test_bracket",
    "tests.test_demo.DemoTest.test_both",
]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


class SubTestParserTest(unittest.TestCase):
    def test_parallel_runner_aggregates_subtest_failure_header(self) -> None:
        stderr = (
            "FAIL: test_worker_case (tests.test_demo.DemoTest.test_worker_case) "
            "(sequence=294)\n"
        )
        self.assertEqual(
            test_parallel_runner.outcome_ids(stderr, "FAIL"),
            ["tests.test_demo.DemoTest.test_worker_case"],
        )

    def test_each_consumer_delegates_to_the_shared_header_parser(self) -> None:
        sentinel = failure_headers.FailureHeader("FAIL", "test_x", "pkg.T.test_x", 0, 28)
        with mock.patch.object(hunk_guard, "failure_sections", return_value={"pkg.T.test_x": "section"}) as parser:
            self.assertEqual(hunk_guard._failure_sections("ignored"), {"pkg.T.test_x": "section"})
            parser.assert_called_once_with("ignored", test_names_only=True)
        with mock.patch.object(verify_scope, "iter_failure_headers", return_value=iter([sentinel])) as parser:
            self.assertEqual(verify_scope.parse_test_failures("ignored"), ["pkg.T.test_x"])
            parser.assert_called_once_with("ignored", test_names_only=True)
        with mock.patch.object(mutation_battery, "iter_failure_headers", return_value=iter([sentinel])) as parser:
            self.assertEqual(mutation_battery.failure_blocks("x" * 28), [("pkg.T.test_x", "x" * 28)])
            parser.assert_called_once_with("x" * 28, test_names_only=False)
        with mock.patch.object(run_receipt, "iter_failure_headers", return_value=iter([sentinel])) as parser:
            self.assertEqual(run_receipt.summarize("", "")["failures"], ["pkg.T.test_x"])
            parser.assert_called_once_with("\n", test_names_only=False)

    def test_mutation_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual([identity for identity, _section in
                          mutation_battery.failure_blocks(HEADERS)],
                         IDENTITIES)

    def test_mutation_parser_does_not_swallow_malformed_header_newline(self) -> None:
        text = "FAIL: broken (unterminated\nFAIL: test_real (pkg.T.test_real)\n"
        self.assertEqual([identity for identity, _section in mutation_battery.failure_blocks(text)],
                         ["pkg.T.test_real"])

    def test_shared_parser_does_not_swallow_newline_and_pins_name_scope(self) -> None:
        text = "FAIL: custom (pkg.T.custom)\nFAIL: test_real (pkg.T.test_real)\n"
        self.assertEqual(
            [header.identity for header in failure_headers.iter_failure_headers(
                text, test_names_only=False)], ["pkg.T.custom", "pkg.T.test_real"])
        self.assertEqual(
            [header.identity for header in failure_headers.iter_failure_headers(
                text, test_names_only=True)], ["pkg.T.test_real"])

    def test_repeated_subtest_sections_are_preserved(self) -> None:
        text = ("FAIL: test_x (pkg.T.test_x) (case=1)\nfirst marker\n"
                "FAIL: test_x (pkg.T.test_x) (case=2)\nsecond marker\n")
        section = hunk_guard._failure_sections(text)["pkg.T.test_x"]
        self.assertIn("first marker", section)
        self.assertIn("second marker", section)

    def test_hunk_guard_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual(list(hunk_guard._failure_sections(HEADERS)), IDENTITIES)

    def test_verify_scope_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual(verify_scope.parse_test_failures(HEADERS), IDENTITIES)
        self.assertEqual(verify_scope.parse_test_errors(HEADERS), [IDENTITIES[2]])

    def test_receipt_summary_uses_shared_subtest_parser(self) -> None:
        summary = run_receipt.summarize("", HEADERS + "Ran 4 tests in 0.01s\nFAILED (failures=3, errors=1)\n")
        self.assertEqual(summary["test_count"], 4)
        self.assertEqual(summary["failures"], [IDENTITIES[0], IDENTITIES[1], IDENTITIES[3]])
        self.assertEqual(summary["errors"], [IDENTITIES[2]])

    def test_hunk_guard_subtest_only_protector_is_protected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hguard-subtest-") as name:
            root = Path(name)
            (root / "src/hengbot").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "scripts").mkdir()
            (root / "src/hengbot/__init__.py").write_text("", encoding="utf-8")
            (root / "tests/__init__.py").write_text("", encoding="utf-8")
            (root / "src/hengbot/demo.py").write_text("def value():\n    return 1\n", encoding="utf-8")
            (root / "tests/test_demo.py").write_text(
                "import unittest\nfrom hengbot.demo import value\n"
                "class DemoTest(unittest.TestCase):\n"
                " def test_value(self):\n"
                "  with self.subTest(case='only'):\n"
                "   self.assertEqual(value(), 1)\n", encoding="utf-8")
            git(root, "init", "-q")
            git(root, "config", "user.email", "selftest@example.invalid")
            git(root, "config", "user.name", "selftest")
            git(root, "add", "."); git(root, "commit", "-qm", "base")
            base = git(root, "rev-parse", "HEAD")
            (root / "src/hengbot/demo.py").write_text("def value():\n    return 2\n", encoding="utf-8")
            (root / "tests/test_demo.py").write_text(
                (root / "tests/test_demo.py").read_text(encoding="utf-8").replace(
                    "assertEqual(value(), 1)", "assertEqual(value(), 2)"), encoding="utf-8")
            git(root, "add", "."); git(root, "commit", "-qm", "change")
            target = git(root, "rev-parse", "HEAD")
            output = root / "result.json"
            with mock.patch.object(hunk_guard, "ROOT", root), mock.patch.object(verify_scope, "ROOT", root):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = hunk_guard.main(["--base", base, "--target", target,
                                            "--timeout", "30", "--output", str(output)])
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(payload["summary"]["protected"], 1)
            self.assertEqual(payload["hunks"][0]["protecting_test_id"],
                             "test_demo.DemoTest.test_value")


class ReceiptTest(unittest.TestCase):
    def test_tee_fileno_delegates_to_an_underlying_real_stream(self) -> None:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as display:
            tee = run_receipt.Tee(display, io.StringIO())
            self.assertEqual(tee.fileno(), display.fileno())
            self.assertEqual(run_receipt.Tee(io.StringIO(), display).fileno(), display.fileno())
        with self.assertRaises(io.UnsupportedOperation):
            run_receipt.Tee(io.StringIO(), io.StringIO()).fileno()

    def test_tee_preserves_unencodable_text_exactly_in_saved_stream(self) -> None:
        display_bytes = io.BytesIO()
        display = io.TextIOWrapper(display_bytes, encoding="ascii", errors="strict", newline="")
        saved = io.StringIO()
        tee = run_receipt.Tee(display, saved)
        value = "worker emitted \ufffd\n"
        self.assertEqual(tee.write(value), len(value))
        self.assertEqual(saved.getvalue(), value)
        display.flush()
        self.assertEqual(display_bytes.getvalue(), b"worker emitted \\ufffd\n")

    def test_tee_write_and_flush_tolerate_closed_streams(self) -> None:
        display, saved = io.StringIO(), io.StringIO()
        display.close(); saved.close()
        tee = run_receipt.Tee(display, saved)
        self.assertEqual(tee.write("late shutdown output"), len("late shutdown output"))
        tee.flush()

    def make_repo(self, root: Path) -> None:
        (root / "src").mkdir()
        (root / "src/tracked.txt").write_text("original\n", encoding="utf-8")
        (root / "jsonlog").mkdir()
        (root / "jsonlog/sol-events.jsonl").write_text('{"type":"base"}\n', encoding="utf-8")
        git(root, "init", "-q")
        git(root, "config", "user.email", "selftest@example.invalid")
        git(root, "config", "user.name", "selftest")
        git(root, "add", "."); git(root, "commit", "-qm", "base")

    def test_receipted_bare_policy_unittest_leaves_repository_history_unchanged(self) -> None:
        history = run_receipt.ROOT / "home-withdraw-history.jsonc"
        before = history.read_bytes()
        environment = __import__("os").environ.copy()
        environment.pop("HENGBOT_HOME_HISTORY_DIR", None)
        environment["PYTHONPATH"] = __import__("os").pathsep.join(
            [str(run_receipt.ROOT / "src"), str(run_receipt.ROOT / "tests"), str(run_receipt.ROOT / "scripts")]
        )
        run = subprocess.run(
            [
                sys.executable,
                str(run_receipt.ROOT / "scripts" / "run_receipt.py"),
                "--tool", "unittest", "--target", "receipt-history-isolation-probe", "--",
                sys.executable, "-m", "unittest",
                "test_home_disposal.ReceiptHistoryIsolationProbeTest.test_default_policy_history_writer",
            ],
            cwd=run_receipt.ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(history.read_bytes(), before)

    def test_empty_history_environment_still_uses_receipt_isolation(self) -> None:
        with mock.patch.dict(os.environ, {run_receipt.HOME_HISTORY_DIR_ENV: ""}):
            with run_receipt.isolated_home_history() as history_dir:
                self.assertTrue(history_dir)
                self.assertEqual(os.environ[run_receipt.HOME_HISTORY_DIR_ENV], history_dir)
            self.assertNotIn(run_receipt.HOME_HISTORY_DIR_ENV, os.environ)

    def test_receipt_round_trip_and_stream_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="receipt-test-") as name:
            root = Path(name); self.make_repo(root)
            receipts = root / "jsonlog/receipts"; receipts.mkdir(parents=True)
            out, err = receipts / "run.stdout.log", receipts / "run.stderr.log"
            out.write_text("Ran 4 tests in 0.01s\n\nOK\n", encoding="utf-8"); err.write_text("", encoding="utf-8")
            with mock.patch.object(run_receipt, "ROOT", root), mock.patch.object(run_receipt, "RECEIPTS", receipts):
                stamp = run_receipt.now()
                receipt = run_receipt.write_receipt(
                    "unittest", "selftest", [sys.executable, "-m", "unittest"], stamp, stamp, 0,
                    out, err, git(root, "rev-parse", "HEAD"), run_receipt.source_fingerprint(root))
            ok, problems, payload = verify_receipt.verify(receipt, root)
            self.assertTrue(ok, problems); self.assertEqual(payload["result"]["test_count"], 4)
            with mock.patch.object(run_receipt, "ROOT", root), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(verify_receipt.main([str(receipt)]), 0)
            rendered = output.getvalue()
            for label in ("tool: unittest", "target: selftest", "argv:", "exit_code: 0",
                          "derived_result:", "failures: [] means no FAIL header scraped"):
                self.assertIn(label, rendered)
            out.write_text("tampered", encoding="utf-8")
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertFalse(ok); self.assertIn("stdout stream sha256 mismatch", problems)

    def test_receipt_ignores_event_append_but_detects_stale_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="receipt-stale-") as name:
            root = Path(name); self.make_repo(root)
            receipts = root / "jsonlog/receipts"; receipts.mkdir(parents=True)
            out, err = receipts / "run.stdout.log", receipts / "run.stderr.log"
            out.write_text("PASS 1 row\n", encoding="utf-8"); err.write_text("", encoding="utf-8")
            with mock.patch.object(run_receipt, "ROOT", root), mock.patch.object(run_receipt, "RECEIPTS", receipts):
                stamp = run_receipt.now()
                receipt = run_receipt.write_receipt(
                    "decision_equivalence", "selftest", ["command"], stamp, stamp, 0,
                    out, err, git(root, "rev-parse", "HEAD"), run_receipt.source_fingerprint(root))
            with (root / "jsonlog/sol-events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write('{"type":"fix"}\n')
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertTrue(ok, problems)
            (root / "src/tracked.txt").write_text("changed\n", encoding="utf-8")
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertFalse(ok); self.assertIn("stale source_fingerprint", problems)

    def test_receipt_detects_forged_result_fields_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="receipt-forge-") as name:
            root = Path(name); self.make_repo(root)
            receipts = root / "jsonlog/receipts"; receipts.mkdir(parents=True)
            out, err = receipts / "run.stdout.log", receipts / "run.stderr.log"
            out.write_text("", encoding="utf-8")
            err.write_text(
                "FAIL: test_bad (tests.test_demo.DemoTest.test_bad)\n"
                "Ran 1 test in 0.01s\n\nFAILED (failures=1)\n", encoding="utf-8")
            with mock.patch.object(run_receipt, "ROOT", root), mock.patch.object(run_receipt, "RECEIPTS", receipts):
                stamp = run_receipt.now()
                receipt = run_receipt.write_receipt(
                    "unittest", "selftest", [sys.executable, "-m", "unittest"], stamp, stamp, 1,
                    out, err, git(root, "rev-parse", "HEAD"), run_receipt.source_fingerprint(root))
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["result"]["test_count"] = 99
            payload["result"]["failures"] = []
            payload["result"]["summary_lines"] = []
            payload["exit_code"] = 0
            receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertFalse(ok)
            joined = "\n".join(problems)
            for field in ("result.test_count", "result.failures", "result.summary_lines", "exit_code"):
                self.assertIn(field + " mismatch", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
