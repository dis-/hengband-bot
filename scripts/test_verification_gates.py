"""Synthetic-repository regression tests for both verification gates."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
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
    def test_live_artifact_survives_copy_cleanup_and_simulated_kill(self) -> None:
        with SyntheticRepo() as repo, tempfile.TemporaryDirectory(prefix="vgate-live-") as live_name:
            live = Path(live_name)
            (live / "evidence").mkdir(); marker = live / "evidence/keep.bin"; marker.write_bytes(b"live")
            worktree = Path(tempfile.mkdtemp(prefix="vgate-copy-"))
            command(repo.root, "git", "worktree", "add", "--detach", str(worktree), "HEAD")
            verify_scope.copy_runtime_artifacts(live, worktree)
            verify_scope._ACTIVE_WORKTREES.add(worktree.resolve())
            verify_scope.cleanup_active_worktrees()  # the atexit/simulated-kill path
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
            try:
                (root / "link").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(RuntimeError): verify_scope.refuse_reparse_points(root)

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

    def test_indented_docstring_only_hunk_is_nonbehavioral(self) -> None:
        body = ["-    \"\"\"old prose\"\"\"\n", "+    \"\"\"new prose\"\"\"\n"]
        self.assertNotEqual(hunk_guard.classify(body), "behavioral")

    def test_file_grouping_keeps_interdependent_hunks_together(self) -> None:
        hunks = [{"file": "src/hengbot/x.py", "line_start": 1, "line_end": 2},
                 {"file": "src/hengbot/x.py", "line_start": 5, "line_end": 6},
                 {"file": "src/hengbot/y.py", "line_start": 1, "line_end": 1}]
        self.assertEqual([len(group) for group in hunk_guard.group_hunks(hunks)], [2, 1])

    def test_dead_allowance_is_emitted_and_fails_main(self) -> None:
        with SyntheticRepo() as repo, mock.patch.object(verify_scope, "ROOT", repo.root), \
             mock.patch.object(verify_scope, "KNOWN_FAILURES", ({"module":"never", "pattern":"dead", "reason":"x", "date":"x"},)), \
             mock.patch.object(verify_scope, "KNOWN_LINT_FAILURES", {}), io.StringIO() as output, contextlib.redirect_stdout(output):
            rc = verify_scope.main(["--derive-only"])
            self.assertEqual(rc, 1)
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

    def test_cleanup_removes_directory_then_prunes_registration(self) -> None:
        with SyntheticRepo() as repo:
            worktree = Path(tempfile.mkdtemp(prefix="vgate-prune-"))
            command(repo.root, "git", "worktree", "add", "--detach", str(worktree), "HEAD")
            verify_scope.cleanup_worktree(worktree, repo.root)
            self.assertFalse(worktree.exists())
            self.assertNotIn(str(worktree), command(repo.root, "git", "worktree", "list", "--porcelain"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
