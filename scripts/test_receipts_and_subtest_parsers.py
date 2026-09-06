"""Self-tests for subTest attribution and execution receipts."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import hunk_guard
import mutation_battery
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
    def test_mutation_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual([match.group(1) for match in mutation_battery.FAILURE_RE.finditer(HEADERS)],
                         IDENTITIES)

    def test_hunk_guard_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual(list(hunk_guard._failure_sections(HEADERS)), IDENTITIES)

    def test_verify_scope_parser_handles_all_subtest_suffix_forms(self) -> None:
        self.assertEqual(verify_scope.parse_test_failures(HEADERS), IDENTITIES)
        self.assertEqual(verify_scope.parse_test_errors(HEADERS), [IDENTITIES[2]])

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
    def make_repo(self, root: Path) -> None:
        (root / "tracked.txt").write_text("original\n", encoding="utf-8")
        git(root, "init", "-q")
        git(root, "config", "user.email", "selftest@example.invalid")
        git(root, "config", "user.name", "selftest")
        git(root, "add", "."); git(root, "commit", "-qm", "base")

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
                    out, err, git(root, "rev-parse", "HEAD"), verify_scope.tree_fingerprint(root))
            ok, problems, payload = verify_receipt.verify(receipt, root)
            self.assertTrue(ok, problems); self.assertEqual(payload["result"]["test_count"], 4)
            out.write_text("tampered", encoding="utf-8")
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertFalse(ok); self.assertIn("stdout stream sha256 mismatch", problems)

    def test_receipt_detects_stale_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="receipt-stale-") as name:
            root = Path(name); self.make_repo(root)
            receipts = root / "jsonlog/receipts"; receipts.mkdir(parents=True)
            out, err = receipts / "run.stdout.log", receipts / "run.stderr.log"
            out.write_text("PASS 1 row\n", encoding="utf-8"); err.write_text("", encoding="utf-8")
            with mock.patch.object(run_receipt, "ROOT", root), mock.patch.object(run_receipt, "RECEIPTS", receipts):
                stamp = run_receipt.now()
                receipt = run_receipt.write_receipt(
                    "decision_equivalence", "selftest", ["command"], stamp, stamp, 0,
                    out, err, git(root, "rev-parse", "HEAD"), verify_scope.tree_fingerprint(root))
            (root / "tracked.txt").write_text("changed\n", encoding="utf-8")
            ok, problems, _ = verify_receipt.verify(receipt, root)
            self.assertFalse(ok); self.assertIn("stale tree_fingerprint", problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
