from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import assertion_change_audit as audit
import purity_cache
import supervise
import test_parallel_runner as runner
import run_receipt


class PurityCacheTest(unittest.TestCase):
    def fixture_tree(self, root: Path) -> None:
        (root / "tests").mkdir(); (root / "src/hengbot").mkdir(parents=True)
        (root / "jsonlog").mkdir()
        (root / "tests/town_producer_purity_matrix.py").write_text(
            'from hengbot import policy\nCAPTURE="jsonlog/capture.jsonl"\n', encoding="utf-8")
        for index in range(1, 7):
            (root / f"tests/test_town_producer_purity_part{index}.py").write_text(
                "import town_producer_purity_matrix\n", encoding="utf-8")
        (root / "src/hengbot/__init__.py").write_text("", encoding="utf-8")
        (root / "src/hengbot/policy.py").write_text("VALUE=1\n", encoding="utf-8")
        (root / "jsonlog/capture.jsonl").write_text("{}\n", encoding="utf-8")

    def test_changing_any_derived_input_invalidates_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); self.fixture_tree(root)
            first, inputs = purity_cache.input_sha256(root)
            self.assertIn("src/hengbot/policy.py", inputs)
            for relative in inputs:
                path = root / relative; original = path.read_bytes()
                path.write_bytes(original + b"\n# mutation")
                self.assertNotEqual(purity_cache.input_sha256(root)[0], first, relative)
                path.write_bytes(original)

    def test_pass_cache_round_trip_and_non_pass_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "cache.json"
            row = purity_cache.record_pass(path, "abc", "head", ("one",))
            self.assertEqual(purity_cache.load_pass(path, "abc"), row)
            path.write_text('{"abc":{"result":"FAIL"}}', encoding="utf-8")
            self.assertIsNone(purity_cache.load_pass(path, "abc"))

    def test_always_ignores_cache_and_failure_never_writes(self):
        modules = [*purity_cache.PURITY_MODULES, "tests.small"]
        fake = {"name": "worker-1", "modules": modules, "returncode": 1,
                "home_history_dir": "x", "wall_seconds": 0.0,
                "payload": {"tests": []}, "failures": ["bad"], "errors": [],
                "stdout": "out", "stderr": "err"}
        with tempfile.TemporaryDirectory() as name, mock.patch.multiple(
            runner, standard_modules=mock.DEFAULT, module_seconds=mock.DEFAULT,
            run_shard=mock.DEFAULT, input_sha256=mock.DEFAULT, load_pass=mock.DEFAULT,
            record_pass=mock.DEFAULT,
        ) as mocks, mock.patch.object(runner.subprocess, "check_output", return_value="head\n"):
            mocks["standard_modules"].return_value = modules
            mocks["module_seconds"].return_value = None
            mocks["run_shard"].return_value = fake
            mocks["input_sha256"].return_value = ("abc", ("input",))
            mocks["load_pass"].return_value = {"result": "PASS", "head_sha": "old", "time": "then"}
            Path("err").write_text("failure", encoding="utf-8")
            self.addCleanup(lambda: Path("err").unlink(missing_ok=True))
            result = runner.main(["--purity", "always", "--workers", "1",
                                  "--output", str(Path(name)/"o"), "--summary-output", str(Path(name)/"s"),
                                  "--streams-dir", str(Path(name)/"streams")])
            self.assertEqual(result, 1)
            self.assertTrue(set(purity_cache.PURITY_MODULES).issubset(fake["modules"]))
            mocks["record_pass"].assert_not_called()

    def test_receipt_summary_preserves_skip_line(self):
        line = "purity: skipped (inputs sha256=abc matched cached PASS from head at then)"
        self.assertIn(line, run_receipt.summarize(line + "\nTotal: 1 tests", "")["summary_lines"])


class AssertionAuditTest(unittest.TestCase):
    def repo(self, old: str, new: str, filename="test_x.py"):
        temp = tempfile.TemporaryDirectory(); root = Path(temp.name)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        (root/"tests").mkdir(); path=root/"tests"/filename; path.write_text(old, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True); subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
        base=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(); path.write_text(new, encoding="utf-8")
        return temp, root, base

    def assertFatal(self, old, new, phrase):
        temp, root, base = self.repo(old, new)
        with temp:
            lines, fatal = audit.audit(base, root)
            self.assertTrue(fatal); self.assertIn(phrase, "\n".join(lines))

    def test_weaker_assertion(self):
        self.assertFatal("def test_x(self):\n self.assertEqual(x, 1)\n", "def test_x(self):\n self.assertTrue(x)\n", "weakened")

    def test_changed_assertion_is_listed_but_not_fatal(self):
        temp, root, base = self.repo("def test_x(self):\n self.assertEqual(x, 1)\n",
                                     "def test_x(self):\n self.assertEqual(x, 2)\n")
        with temp:
            lines, fatal = audit.audit(base, root)
            self.assertFalse(fatal); self.assertIn("before:", "\n".join(lines))

    def test_added_return(self):
        self.assertFatal("def test_x(self):\n x=1\n", "def test_x(self):\n return\n", "early return")

    def test_forbidden_expected_constant(self):
        self.assertFatal("def test_x(self):\n self.assertEqual(x, 'ok')\n", "def test_x(self):\n self.assertEqual(x, 'defect:=>')\n", "forbidden expected")

    def test_catalog_identity_constant(self):
        old="def replay():\n return key == '!'\n"; new="def replay():\n return key == 'town-progress-invariant:defect:=>x'\n"
        temp, root, base = self.repo(old, new, "absorbing_state_catalog.py")
        with temp:
            lines, fatal = audit.audit(base, root)
            self.assertTrue(fatal); self.assertIn("replay identity", "\n".join(lines))


class SupervisorHelpersTest(unittest.TestCase):
    def test_process_and_prompt_detection(self):
        rows = supervise.process_rows('[{"ProcessId":7,"CommandLine":"codex exec prompt.txt"}]')
        self.assertEqual(supervise.codex_pids(rows, "prompt.txt"), {7})

    def test_reason_filter_deduplicates(self):
        seen=set(); lines=['{"reason":"town:blocked:x"}', '{"reason":"town:blocked:x"}', '{"reason":"shop"}']
        self.assertEqual(supervise.matching_reasons(lines, seen), ["town:blocked:x"])

    def test_suite_dry_run_contains_cli_and_completion(self):
        commands=supervise.suite_commands("head", 2)
        self.assertEqual(len(commands), 3)
        self.assertIn("tests.test_cli", commands[-1])


if __name__ == "__main__": unittest.main()
