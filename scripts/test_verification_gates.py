"""Synthetic-repository regression tests for both verification gates."""

from __future__ import annotations

import contextlib
import ast
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import hunk_guard
import verify_scope

PYTHON = Path(__import__("sys").executable)


def command(root: Path, *args: str) -> str:
    run = subprocess.run(args, cwd=root, text=True, encoding="utf-8", errors="replace",
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return run.stdout


class SyntheticRepo:
    def __enter__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="vgate-selftest-")
        self.root = Path(self._temporary.name)
        (self.root / "src/hengbot").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "src/hengbot/__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests/__init__.py").write_text("", encoding="utf-8")
        (self.root / "src/hengbot/demo.py").write_text("def value():\n    return 1\n", encoding="utf-8")
        (self.root / "tests/test_demo.py").write_text(
            "import unittest\nfrom hengbot.demo import value\n"
            "class T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(), 1)\n", encoding="utf-8")
        for lint in verify_scope.LINTS:
            path = self.root / lint
            path.write_text("raise SystemExit(0)\n", encoding="utf-8")
        command(self.root, "git", "init", "-q")
        command(self.root, "git", "config", "user.email", "selftest@example.invalid")
        command(self.root, "git", "config", "user.name", "verification self-test")
        command(self.root, "git", "add", ".")
        command(self.root, "git", "commit", "-qm", "base")
        self.base = command(self.root, "git", "rev-parse", "HEAD").strip()
        return self

    def change(self, source: str = "def value():\n    return 2\n", expected: int = 2) -> None:
        (self.root / "src/hengbot/demo.py").write_text(source, encoding="utf-8")
        (self.root / "tests/test_demo.py").write_text(
            "import unittest\nfrom hengbot.demo import value\n"
            f"class T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(), {expected})\n", encoding="utf-8")

    def __exit__(self, *exc):
        self._temporary.cleanup()


class VerificationGateSelfTest(unittest.TestCase):
    def test_live_artifact_survives_copy_and_atexit_cleanup(self) -> None:
        with SyntheticRepo() as repo, tempfile.TemporaryDirectory(prefix="vgate-live-") as live_name:
            live = Path(live_name)
            (live / "evidence").mkdir(); marker = live / "evidence/keep.bin"; marker.write_bytes(b"live")
            worktree = Path(tempfile.mkdtemp(prefix="vgate-copy-"))
            command(repo.root, "git", "worktree", "add", "--detach", str(worktree), "HEAD")
            verify_scope.copy_runtime_artifacts(live, worktree)
            verify_scope._ACTIVE_WORKTREES.add(worktree.resolve())
            with mock.patch.object(verify_scope, "ROOT", repo.root):
                verify_scope.cleanup_active_worktrees()
            self.assertEqual(marker.read_bytes(), b"live")
            self.assertFalse(worktree.exists())

    def test_artifact_copy_cannot_touch_source(self) -> None:
        with tempfile.TemporaryDirectory() as source_name, tempfile.TemporaryDirectory() as destination_name:
            source, destination = Path(source_name), Path(destination_name)
            (source / "evidence").mkdir(); marker = source / "evidence/x"; marker.write_text("x")
            before = marker.stat().st_mtime_ns
            verify_scope.copy_runtime_artifacts(source, destination)
            (destination / "evidence/x").write_text("changed")
            self.assertEqual((marker.read_text(), marker.stat().st_mtime_ns), ("x", before))

    def test_reparse_cleanup_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root_name, tempfile.TemporaryDirectory() as outside_name:
            root, outside = Path(root_name), Path(outside_name)
            subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "link"), str(outside)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            with self.assertRaises(RuntimeError): verify_scope.refuse_reparse_points(root)

    def test_next_run_reclaims_simulated_kill_but_not_live_owner(self) -> None:
        with SyntheticRepo() as repo:
            dead = Path(tempfile.mkdtemp(prefix="hengbot-verify-"))
            live = Path(tempfile.mkdtemp(prefix="hengbot-hunk-"))
            command(repo.root, "git", "worktree", "add", "--detach", str(dead), "HEAD")
            command(repo.root, "git", "worktree", "add", "--detach", str(live), "HEAD")
            verify_scope.worktree_owner_path(dead).write_text(
                json.dumps({"pid": 2147483647, "started": time.time()}), encoding="utf-8")
            with mock.patch.object(verify_scope, "process_is_running", side_effect=lambda pid: pid == __import__("os").getpid()):
                verify_scope.record_worktree_owner(live)
                verify_scope.cleanup_stale_temp_worktrees(repo.root)
            self.assertFalse(dead.exists())
            self.assertTrue(live.exists())
            verify_scope.cleanup_worktree(live, repo.root)

    def test_real_unittest_docstring_shape_is_captured(self) -> None:
        output = "test_x (test_demo.T.test_x)\nA docstring\n----------------------------------------------------------------------\nFAIL: test_x (test_demo.T.test_x)\n"
        self.assertEqual(verify_scope.parse_test_failures(output), ["test_demo.T.test_x"])

    def test_timeout_and_import_failures_never_protect(self) -> None:
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["x"], 1)):
            self.assertEqual(hunk_guard.run_candidate(Path.cwd(), "tests.x", 1, Path(tempfile.gettempdir()) / "x.err"), set())
        for error in ("AttributeError", "TypeError", "IndentationError", "TabError"):
            with tempfile.TemporaryDirectory() as name:
                stderr = Path(name) / "x.err"
                completed = subprocess.CompletedProcess([], 1, stdout="")
                with mock.patch("subprocess.run", return_value=completed):
                    stderr.write_text(f"{error}: broken\n")
                    self.assertEqual(hunk_guard.run_candidate(Path.cwd(), "tests.x", 1, stderr), set())

    def test_incoherent_revert_error_is_rejected_but_assertion_pin_counts(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "src/hengbot/demo.py"
            source.parent.mkdir(parents=True); source.write_text("value = 7\n")
            stderr = root / "candidate.err"
            def failing_run(*args, **kwargs):
                kwargs["stderr"].write(
                    "ERROR: test_compute (test_foo.ComputeTest.test_compute)\n"
                    "Traceback (most recent call last):\n"
                    f'  File "{source}", line 17, in compute\n'
                    "    return helper()\nNameError: name 'helper' is not defined\n\n"
                    "FAIL: test_pin (test_foo.ComputeTest.test_pin)\n"
                    "Traceback (most recent call last):\n"
                    "AssertionError: 0 != 7\n")
                return subprocess.CompletedProcess([], 1, stdout="")
            with mock.patch("subprocess.run", side_effect=failing_run):
                self.assertEqual(hunk_guard.run_candidate(
                    root, "tests.x", 1, stderr, "src/hengbot/demo.py", {"helper"}),
                    {"test_foo.ComputeTest.test_pin"})

    def test_deepest_frame_and_introduced_symbol_both_bind_discriminator(self) -> None:
        root = Path.cwd(); source = root / "src/hengbot/demo.py"
        base = ("ERROR: test_x (test_demo.T.test_x)\nTraceback (most recent call last):\n"
                f'  File "{source}", line 1, in value\n    helper()\n'
                "NameError: name 'helper' is not defined\n")
        self.assertTrue(hunk_guard._is_incoherent_revert(base, root, "src/hengbot/demo.py", {"helper"}))
        self.assertFalse(hunk_guard._is_incoherent_revert(base, root, "src/hengbot/demo.py", {"other"}))
        test_deepest = base.replace("NameError:", f'  File "{Path(__file__)}", line 1, in test_x\nNameError:')
        self.assertFalse(hunk_guard._is_incoherent_revert(test_deepest, root, "src/hengbot/demo.py", {"helper"}))

    def test_introduced_symbols_covers_definition_assignment_and_import(self) -> None:
        body = ["+def helper():\n", "+    pass\n", "+answer = 7\n", "+self.retry_after = 1\n",
                "+from pkg import backoff\n"]
        self.assertEqual(hunk_guard.introduced_symbols(body),
                         {"helper", "answer", "retry_after", "backoff"})

    def test_indented_docstring_only_hunk_is_nonbehavioral(self) -> None:
        body = ["-    \"\"\"old prose\"\"\"\n", "+    \"\"\"new prose\"\"\"\n"]
        self.assertNotEqual(hunk_guard.classify(body), "behavioral")

    def test_zero_context_docstring_prose_fallback_is_nonbehavioral(self) -> None:
        self.assertEqual(hunk_guard.classify(["-    old prose only\n", "+    new prose only\n"]),
                         "nonbehavioral-docstring-prose")

    def test_file_grouping_keeps_interdependent_hunks_together(self) -> None:
        hunks = [{"file": "src/hengbot/x.py", "line_start": 1, "line_end": 2},
                 {"file": "src/hengbot/x.py", "line_start": 5, "line_end": 6},
                 {"file": "src/hengbot/y.py", "line_start": 1, "line_end": 1}]
        self.assertEqual([len(group) for group in hunk_guard.group_hunks(hunks)], [2, 1])

    def test_out_of_scope_allowance_is_not_evaluated(self) -> None:
        with SyntheticRepo() as repo, mock.patch.object(verify_scope, "ROOT", repo.root), \
             mock.patch.object(verify_scope, "KNOWN_FAILURES", ({"module":"never", "pattern":"dead", "reason":"x", "date":"x"},)), \
             mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}), io.StringIO() as output, contextlib.redirect_stdout(output):
            rc = verify_scope.main(["--derive-only"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.getvalue())["allowlist_coverage"]["known_failures"], [])

    def test_in_scope_unmatched_allowance_fails_main(self) -> None:
        entry = {"module":"tests.test_demo", "pattern":"dead", "reason":"x", "date":"x"}
        with SyntheticRepo() as repo, mock.patch.object(verify_scope, "ROOT", repo.root), \
             mock.patch.object(verify_scope, "ALWAYS_MODULES", {"tests.test_demo"}), \
             mock.patch.object(verify_scope, "KNOWN_FAILURES", (entry,)), \
             mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}), io.StringIO() as output, contextlib.redirect_stdout(output):
            self.assertEqual(verify_scope.main(["--timeout", "10"]), 1)
            self.assertFalse(json.loads(output.getvalue())["allowlist_coverage"]["known_failures"][0]["matched"])

    def test_verify_main_reports_new_tree_fingerprint_and_allowlist_keys(self) -> None:
        with SyntheticRepo() as repo, mock.patch.object(verify_scope, "ROOT", repo.root), \
             mock.patch.object(verify_scope, "KNOWN_FAILURES", ()), mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}), \
             io.StringIO() as output, contextlib.redirect_stdout(output):
            self.assertEqual(verify_scope.main(["--derive-only"]), 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["tool"]["tree_fingerprint"], verify_scope.tree_fingerprint(repo.root))
            self.assertIn("allowlist_coverage", payload)
            self.assertIn("known_untested_paths", payload)

    def test_verify_main_counts_failed_skipped_and_lint_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / "src").mkdir(); (root / "tests").mkdir()
            script = root / "lint.py"; script.write_text("print('tests/x.py:1: bad')\nraise SystemExit(1)\n")
            allowance = {"count": 1, "reason": "baseline", "date": "x"}
            with mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {"lint.py": allowance}):
                item = verify_scope.run_item(root, "lint.py", [str(PYTHON), "lint.py"], 10, root / "logs")
            self.assertEqual((item["status"], item["failed"], item["skipped"]), ("failed_known", 1, 0))

    def test_hunk_main_drives_behavioral_and_no_behavioral_paths(self) -> None:
        with SyntheticRepo() as repo:
            repo.change()
            patches = (mock.patch.object(verify_scope, "ROOT", repo.root), mock.patch.object(hunk_guard, "ROOT", repo.root),
                       mock.patch.object(verify_scope, "ALWAYS_MODULES", set()), mock.patch.object(verify_scope, "KNOWN_FAILURES", ()),
                       mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}))
            with patches[0], patches[1], patches[2], patches[3], patches[4], io.StringIO() as output, contextlib.redirect_stdout(output):
                self.assertEqual(hunk_guard.main(["--base", repo.base, "--wide", "--timeout", "10"]), 0)
                payload = json.loads(output.getvalue())
                self.assertEqual(payload["hunks"][0]["result"], "PROTECTED")

    def test_new_file_branch_and_no_behavioral_warning_are_real(self) -> None:
        diff = "diff --git a/src/hengbot/new.py b/src/hengbot/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/src/hengbot/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
        self.assertTrue(hunk_guard.parse_hunks(diff)[0]["new_file"])
        self.assertNotEqual(hunk_guard.classify(["+# prose\n"]), "behavioral")

    def test_new_file_is_unverified_and_other_files_keep_separate_groups(self) -> None:
        hunks = [
            {"file": "src/hengbot/new.py", "line_start": 1, "line_end": 20, "new_file": True, "body": ["+x=1\n"]},
            {"file": "src/hengbot/a.py", "line_start": 1, "line_end": 2, "new_file": False, "body": ["+from .new import x\n"]},
            {"file": "src/hengbot/a.py", "line_start": 100, "line_end": 101, "new_file": False, "body": ["+y=x\n"]},
        ]
        self.assertEqual([len(group) for group in hunk_guard.group_hunks(hunks)], [1, 1, 1])
        source = Path(hunk_guard.__file__).read_text(encoding="utf-8")
        self.assertIn('"NEW-FILE-UNVERIFIED" if new_file', source)

    def test_failed_loader_is_never_a_protector_even_for_structural_changes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            stderr = Path(name) / "loader.err"
            def loader_failure(*args, **kwargs):
                kwargs["stderr"].write(
                    "ERROR: test_x (unittest.loader._FailedTest.test_x)\n"
                    "structural collection failure\n")
                return subprocess.CompletedProcess([], 1, stdout="")
            with mock.patch("subprocess.run", side_effect=loader_failure):
                self.assertEqual(hunk_guard.run_candidate(Path.cwd(), "tests.x", 1, stderr), set())

    def test_exception_text_does_not_void_a_real_failing_test(self) -> None:
        for error in ("ImportError", "ModuleNotFoundError", "NameError", "SyntaxError",
                      "AttributeError", "TypeError", "IndentationError", "TabError"):
            with tempfile.TemporaryDirectory() as name:
                stderr = Path(name) / "candidate.err"
                def failing_run(*args, **kwargs):
                    kwargs["stderr"].write(
                        "FAIL: test_pin (test_demo.T.test_pin)\n"
                        f"{error}: deliberately asserted by this test\n")
                    kwargs["stderr"].flush()
                    return subprocess.CompletedProcess([], 1, stdout="")
                with mock.patch("subprocess.run", side_effect=failing_run):
                    self.assertEqual(hunk_guard.run_candidate(Path.cwd(), "tests.x", 1, stderr),
                                     {"test_demo.T.test_pin"})

    def test_answer_key_cannot_be_reintroduced_under_historical_name(self) -> None:
        self.assertFalse(hasattr(hunk_guard, "INELIGIBLE_PROTECTORS"))

    def test_inline_blanket_exception_denylist_cannot_void_assertion_pin(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            stderr = Path(name) / "candidate.err"
            def failing_run(*args, **kwargs):
                kwargs["stderr"].write(
                    "FAIL: test_pin (test_demo.T.test_pin)\nAssertionError: NameError ImportError AttributeError\n")
                return subprocess.CompletedProcess([], 1, stdout="")
            with mock.patch("subprocess.run", side_effect=failing_run):
                self.assertEqual(hunk_guard.run_candidate(Path.cwd(), "tests.x", 1, stderr),
                                 {"test_demo.T.test_pin"})

    def test_new_file_and_no_behavioral_results_come_from_main(self) -> None:
        with SyntheticRepo() as repo, mock.patch.object(verify_scope, "ROOT", repo.root), \
             mock.patch.object(hunk_guard, "ROOT", repo.root), \
             mock.patch.object(verify_scope, "ALWAYS_MODULES", set()), \
             mock.patch.object(verify_scope, "KNOWN_FAILURES", ()), \
             mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}):
            (repo.root / "src/hengbot/new.py").write_text("x = 1\n", encoding="utf-8")
            command(repo.root, "git", "add", "-N", "src/hengbot/new.py")
            with io.StringIO() as output, contextlib.redirect_stdout(output):
                self.assertEqual(hunk_guard.main(["--base", repo.base, "--wide", "--timeout", "10"]), 1)
                payload = json.loads(output.getvalue())
            self.assertEqual(payload["hunks"][0]["result"], "NEW-FILE-UNVERIFIED")
            (repo.root / "src/hengbot/new.py").unlink()
            command(repo.root, "git", "reset", "-q", "--", "src/hengbot/new.py")
            (repo.root / "src/hengbot/demo.py").write_text("# changed prose\ndef value():\n    return 1\n", encoding="utf-8")
            with io.StringIO() as output, contextlib.redirect_stdout(output):
                self.assertEqual(hunk_guard.main(["--base", repo.base, "--wide", "--timeout", "10"]), 0)
                payload = json.loads(output.getvalue())
            self.assertEqual(payload["warnings"], ["NO-BEHAVIORAL-HUNKS"])

    def test_known_failure_matcher_is_required_by_main(self) -> None:
        entry = {"module": "tests.test_demo", "pattern": "stalled_capture", "count": 1,
                 "reason": "fixture", "date": "x"}
        with SyntheticRepo() as repo:
            repo.change(expected=99)
            test = repo.root / "tests/test_demo.py"
            test.write_text(test.read_text() + "# stalled_capture\n", encoding="utf-8")
            with mock.patch.object(verify_scope, "ROOT", repo.root), \
                 mock.patch.object(verify_scope, "ALWAYS_MODULES", {"tests.test_demo"}), \
                 mock.patch.object(verify_scope, "KNOWN_FAILURES", (entry,)), \
                 mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}), \
                 mock.patch.object(verify_scope, "known_failure_matches", return_value=[]), \
                 io.StringIO() as output, contextlib.redirect_stdout(output):
                self.assertEqual(verify_scope.main(["--timeout", "10"]), 1)
                self.assertEqual(json.loads(output.getvalue())["modules"]["tests.test_demo"]["status"], "failed")

    def test_stalled_capture_allowance_matches_real_failure_text(self) -> None:
        entry = next(item for item in verify_scope.KNOWN_FAILURES
                     if item["module"] == "tests.test_home_knowledge_scan")
        failure = ["test_home_knowledge_scan.T.test_capture"]
        self.assertEqual(verify_scope.known_failure_matches(
            entry["module"],
            "FAIL: test_stalled_capture_requests_home_knowledge_and_completes "
            "(test_home_knowledge_scan.HomeKnowledgeScanTest."
            "test_stalled_capture_requests_home_knowledge_and_completes)\n"
            "AssertionError: False is not true",
            failure), [entry])

    def test_inline_literal_answer_key_cannot_filter_new_failures(self) -> None:
        tree = ast.parse(Path(hunk_guard.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Sub):
                continue
            left_names = {item.id for item in ast.walk(node.left) if isinstance(item, ast.Name)}
            if left_names & {"failures", "new_failures"} and isinstance(
                    node.right, (ast.Set, ast.List, ast.Tuple, ast.Dict)):
                offenders.append(node.lineno)
        self.assertEqual(offenders, [])

    def test_failed_skipped_and_lint_excess_are_measured(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / "src").mkdir(); (root / "tests").mkdir()
            runner = root / "runner.py"
            runner.write_text("import sys\nsys.stderr.write('FAIL: test_x (x.T.test_x)\\n... skipped reason\\n')\nraise SystemExit(1)\n")
            item = verify_scope.run_item(root, "tests.x", [str(PYTHON), str(runner)], 10, root / "logs")
            self.assertEqual((item["failed"], item["skipped"]), (1, 1))
            lint = root / "lint.py"
            lint.write_text("print('tests/a.py:1: one')\nprint('tests/b.py:2: two')\nraise SystemExit(1)\n")
            allowance = {"count": 1, "reason": "baseline", "date": "x"}
            with mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {"lint.py": allowance}):
                item = verify_scope.run_item(root, "lint.py", [str(PYTHON), str(lint)], 10, root / "logs")
            self.assertEqual((item["status"], item["failed"]), ("failed", 2))

    def test_historical_target_scope_does_not_use_live_test_glob(self) -> None:
        with SyntheticRepo() as repo:
            old = repo.root / "tests/test_historical.py"
            old.write_text("from hengbot.demo import value\n", encoding="utf-8")
            command(repo.root, "git", "add", "."); command(repo.root, "git", "commit", "-qm", "historical test")
            target = command(repo.root, "git", "rev-parse", "HEAD").strip()
            old.unlink()
            self.assertIn("tests/test_historical.py", verify_scope.test_paths_at(repo.root, target))

    def test_atexit_registration_removes_an_active_temp_tree(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            victim = Path(name) / "hengbot-verify-exit"
            victim.mkdir()
            code = ("import pathlib,sys; sys.path.insert(0, r'%s'); import verify_scope; "
                    "verify_scope._ACTIVE_WORKTREES.add(pathlib.Path(r'%s').resolve())") % (
                        Path(__file__).parent, victim)
            subprocess.run([str(PYTHON), "-c", code], check=True)
            self.assertFalse(victim.exists())

    def test_old_unregistered_temp_tree_is_swept_but_live_owner_survives(self) -> None:
        dead = Path(tempfile.mkdtemp(prefix="hengbot-verify-"))
        live = Path(tempfile.mkdtemp(prefix="hengbot-hunk-"))
        old = time.time() - verify_scope.STALE_WORKTREE_AGE_SECONDS - 60
        verify_scope.worktree_owner_path(dead).write_text(json.dumps({"pid": 2147483647, "started": old}))
        verify_scope.worktree_owner_path(live).write_text(json.dumps({"pid": __import__('os').getpid(), "started": old}))
        try:
            with SyntheticRepo() as repo, mock.patch.object(verify_scope, "process_is_running",
                                                           side_effect=lambda pid: pid == __import__('os').getpid()):
                verify_scope.cleanup_stale_temp_worktrees(repo.root)
            self.assertFalse(dead.exists()); self.assertTrue(live.exists())
        finally:
            if live.exists(): verify_scope.refuse_reparse_points(live); __import__('shutil').rmtree(live)
            verify_scope.worktree_owner_path(live).unlink(missing_ok=True)

    def test_cleanup_removes_directory_then_prunes_registration(self) -> None:
        with SyntheticRepo() as repo:
            worktree = Path(tempfile.mkdtemp(prefix="vgate-prune-"))
            command(repo.root, "git", "worktree", "add", "--detach", str(worktree), "HEAD")
            verify_scope.cleanup_worktree(worktree, repo.root)
            self.assertFalse(worktree.exists())
            self.assertNotIn(str(worktree), command(repo.root, "git", "worktree", "list", "--porcelain"))

    def test_cleanup_removes_inspected_directory_before_unregistering(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "hengbot-verify-order"; path.mkdir()
            events = []
            def fake_git(*args, **kwargs):
                if args[1:3] == ("worktree", "remove"):
                    events.append("unregister")
                return ""
            def fake_rmtree(victim):
                events.append("remove-directory")
                victim.rmdir()
            with mock.patch.object(verify_scope, "git", side_effect=fake_git), \
                 mock.patch.object(verify_scope.shutil, "rmtree", side_effect=fake_rmtree):
                verify_scope.cleanup_worktree(path, Path(parent))
            self.assertEqual(events[:2], ["remove-directory", "unregister"])

    def test_windows_invalid_parameter_pid_is_dead_and_access_denied_is_live(self) -> None:
        if __import__("os").name == "nt":
            import ctypes
            class Kernel:
                def __init__(self, error): self.error = error
                def OpenProcess(self, *_): ctypes.set_last_error(self.error); return 0
                def GetExitCodeProcess(self, *_): raise AssertionError("no handle")
                def CloseHandle(self, *_): raise AssertionError("no handle")
            with mock.patch.object(ctypes, "WinDLL", return_value=Kernel(87)):
                self.assertFalse(verify_scope.process_is_running(999999))
            with mock.patch.object(ctypes, "WinDLL", return_value=Kernel(5)):
                self.assertTrue(verify_scope.process_is_running(1))
        else:
            with mock.patch.object(verify_scope.os, "kill", side_effect=ProcessLookupError()):
                self.assertFalse(verify_scope.process_is_running(999999))

    def test_excluded_test_prefix_is_exact(self) -> None:
        code = verify_scope._test_code("tests.test_cli")
        self.assertIn("test.id().startswith(prefix + '.')", code)
        self.assertIn("test_cli.DecisionTimingTest", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
