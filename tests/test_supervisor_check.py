"""The supervision checker's verdicts over synthetic artifact directories.

Every case builds its own jsonlog/ under a temporary directory and stubs
process identity, so no test reads or writes the live bot's runtime files and
none of them touches the scheduled task.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "supervisor_check.py"
NOW = datetime(2026, 9, 23, 18, 20, 0, tzinfo=timezone(timedelta(hours=9)))


def load_checker():
    spec = importlib.util.spec_from_file_location("supervisor_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def stamp(offset_seconds: float) -> str:
    return (NOW - timedelta(seconds=offset_seconds)).isoformat()


class SyntheticTree:
    """A jsonlog/ tree with exactly the artifacts a case needs."""

    def __init__(self, directory: Path):
        self.root = directory
        self.runtime = directory / "jsonlog"
        self.runtime.mkdir(parents=True, exist_ok=True)

    def bot_pid(self, value: int) -> "SyntheticTree":
        (self.runtime / "bot.pid").write_text(str(value), encoding="utf-8")
        return self

    def decisions(self, age_seconds: float, sequence: int) -> "SyntheticTree":
        row = {"time": stamp(age_seconds), "decision_sequence": sequence,
               "reason": "fundraise:seek-treasure"}
        (self.runtime / "bot-decisions.jsonl").write_text(
            json.dumps(row) + "\n", encoding="utf-8")
        return self

    def metrics(self, rows: list[dict]) -> "SyntheticTree":
        (self.runtime / "ownership-metrics.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return self

    def progress(self, session: str, samples: list[tuple[float, int]]) -> "SyntheticTree":
        rows = [{"time": stamp(samples[0][0] + 60), "kind": "session-start",
                 "session": session, "pid": 4242}]
        rows += [{"time": stamp(age), "kind": "decision-progress", "session": session,
                  "decisions": count, "decision_sequence": count - 1}
                 for age, count in samples]
        return self.metrics(rows)

    def hold(self, reason: str) -> "SyntheticTree":
        (self.runtime / "maintenance.hold").write_text(reason, encoding="utf-8")
        return self


class SupervisorCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = load_checker()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="hengbot-supervisor-test-"))
        self.tree = SyntheticTree(self.directory / "checkout")
        self.state = self.directory / "state"
        self.identities = {}
        original = self.checker.identified_alive
        self.addCleanup(setattr, self.checker, "identified_alive", original)
        self.checker.identified_alive = self._identified_alive

    def _identified_alive(self, pid, needle):
        """Stub for the real process lookup; no live process is consulted."""
        if not pid:
            return False, "no pid recorded"
        command = self.identities.get(pid)
        if command is None:
            return False, f"pid {pid} holds no process (stale pid)"
        if needle.lower() not in command.lower():
            return False, f"pid {pid} is {command} (stale pid)"
        return True, f"pid {pid} alive as python.exe"

    def check(self):
        return self.checker.check(self.tree.root, NOW, "hengbot")

    def front(self, name):
        return self.check()["fronts"][name]

    # -- bot front ------------------------------------------------------

    def test_live_bot_with_fresh_decisions_is_ok(self):
        self.identities[13008] = "python.exe -m hengbot --state-file ..."
        self.tree.bot_pid(13008).decisions(4, 1242)
        front = self.front("bot")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("pid 13008 alive", front["evidence"])
        self.assertIn("#1242", front["evidence"])

    def test_stale_pid_is_a_stall_with_stale_pid_evidence(self):
        """The 2026-09-23 regression: bot.pid held a dead pid for six hours."""
        self.tree.bot_pid(13008).decisions(6 * 3600 + 17 * 60, 1573)
        front = self.front("bot")
        self.assertFalse(front["ok"])
        self.assertIn("stale pid", front["evidence"])
        self.assertIn("6h17m", front["evidence"])
        self.assertIn("no maintenance.hold", front["evidence"])

    def test_recycled_pid_belonging_to_another_program_is_a_stall(self):
        self.identities[13008] = "notepad.exe"
        self.tree.bot_pid(13008).decisions(6 * 3600, 1573)
        front = self.front("bot")
        self.assertFalse(front["ok"])
        self.assertIn("stale pid", front["evidence"])

    def test_missing_pid_file_without_hold_is_a_stall(self):
        self.tree.decisions(300, 1573)
        front = self.front("bot")
        self.assertFalse(front["ok"])
        self.assertIn("no pid recorded", front["evidence"])

    def test_stopped_bot_under_maintenance_hold_is_ok(self):
        self.tree.decisions(6 * 3600, 1573).hold("swapping the exe\n")
        front = self.front("bot")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("swapping the exe", front["evidence"])

    def test_empty_maintenance_hold_does_not_excuse_a_stopped_bot(self):
        self.tree.decisions(6 * 3600, 1573).hold("")
        front = self.front("bot")
        self.assertFalse(front["ok"])
        self.assertIn("carries no reason", front["evidence"])

    def test_live_bot_whose_decision_log_froze_is_a_stall(self):
        self.identities[13008] = "python.exe -m hengbot"
        self.tree.bot_pid(13008).decisions(600, 1242)
        front = self.front("bot")
        self.assertFalse(front["ok"])
        self.assertIn("10m00s", front["evidence"])

    # -- measurement front ----------------------------------------------

    def test_measurement_stalls_when_the_decision_count_does_not_advance(self):
        self.identities[13008] = "python.exe -m hengbot"
        self.tree.bot_pid(13008).decisions(4, 1242)
        self.tree.progress("13008-a", [(65, 1216), (5, 1216)])
        front = self.front("measurement")
        self.assertFalse(front["ok"])
        self.assertIn("stuck at 1216", front["evidence"])

    def test_measurement_is_ok_when_the_count_advances(self):
        self.identities[13008] = "python.exe -m hengbot"
        self.tree.bot_pid(13008).decisions(4, 1242)
        self.tree.progress("13008-a", [(65, 862), (5, 1216)])
        front = self.front("measurement")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("+354", front["evidence"])

    def test_measurement_stalls_when_progress_rows_stop_while_the_bot_runs(self):
        self.identities[13008] = "python.exe -m hengbot"
        self.tree.bot_pid(13008).decisions(4, 1242)
        self.tree.progress("13008-a", [(900, 862), (600, 1216)])
        front = self.front("measurement")
        self.assertFalse(front["ok"])
        self.assertIn("10m00s old", front["evidence"])

    def test_measurement_does_not_duplicate_the_bot_front_when_no_bot_runs(self):
        self.tree.decisions(6 * 3600, 1573)
        verdict = self.check()
        self.assertFalse(verdict["fronts"]["bot"]["ok"])
        self.assertTrue(verdict["fronts"]["measurement"]["ok"])
        self.assertEqual(verdict["stalled"], ["bot"])

    def test_session_end_while_the_process_lives_is_a_measurement_stall(self):
        self.identities[13008] = "python.exe -m hengbot"
        self.tree.bot_pid(13008).decisions(4, 1242)
        self.tree.metrics([
            {"time": stamp(400), "kind": "session-start", "session": "13008-a"},
            {"time": stamp(300), "kind": "decision-progress", "session": "13008-a",
             "decisions": 100},
            {"time": stamp(200), "kind": "session-end", "session": "13008-a",
             "how": "process-exit"},
        ])
        front = self.front("measurement")
        self.assertFalse(front["ok"])
        self.assertIn("ended while the bot process still runs", front["evidence"])

    # -- review front ---------------------------------------------------

    def test_review_is_ok_without_a_git_repository(self):
        front = self.front("review")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("no git repository", front["evidence"])

    def test_review_reports_the_age_of_the_oldest_unpushed_commit(self):
        outputs = {
            ("rev-list", "--count", "origin/main..main"): "3",
            ("log", "--reverse", "--format=%cI %h %s", "origin/main..main"):
                f"{stamp(95 * 60)} 047aa24 Record the choke commitment\n"
                f"{stamp(20 * 60)} deadbee Later commit",
        }
        self._stub_git(outputs)
        front = self.front("review")
        self.assertFalse(front["ok"])
        self.assertIn("3 unpushed commits", front["evidence"])
        self.assertIn("1h35m old", front["evidence"])
        self.assertIn("047aa24", front["evidence"])

    def test_review_is_ok_while_unpushed_commits_are_young(self):
        self._stub_git({
            ("rev-list", "--count", "origin/main..main"): "1",
            ("log", "--reverse", "--format=%cI %h %s", "origin/main..main"):
                f"{stamp(10 * 60)} 047aa24 Record the choke commitment",
        })
        front = self.front("review")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("10m00s old", front["evidence"])

    def test_review_is_ok_with_nothing_unpushed(self):
        self._stub_git({("rev-list", "--count", "origin/main..main"): "0"})
        front = self.front("review")
        self.assertTrue(front["ok"], front["evidence"])
        self.assertIn("no unpushed commits", front["evidence"])

    def _stub_git(self, outputs):
        original = self.checker.git_output
        self.addCleanup(setattr, self.checker, "git_output", original)
        self.checker.git_output = lambda root, *arguments: outputs.get(tuple(arguments))

    # -- command line ---------------------------------------------------

    def test_cli_exits_one_and_writes_a_verdict_file_when_a_front_is_stalled(self):
        self.tree.bot_pid(999999).decisions(6 * 3600, 1573)
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.tree.root),
             "--state-dir", str(self.state), "--source", "task",
             "--now", NOW.isoformat()],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("bot stalled:", run.stdout)
        verdict = json.loads((self.state / "verdict-task.json").read_text(encoding="utf-8"))
        self.assertEqual(verdict["stalled"], ["bot"])
        self.assertFalse((self.tree.runtime / "waker.json").exists())

    def test_cli_exits_zero_when_every_front_is_ok(self):
        self.tree.decisions(30, 1573).hold("held for the exe swap")
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.tree.root),
             "--state-dir", str(self.state), "--now", NOW.isoformat()],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for name in ("bot", "measurement", "review"):
            self.assertIn(f"{name} ok:", run.stdout)
        self.assertTrue((self.state / "verdict-session.json").exists())


class TailRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = load_checker()

    def test_tail_skips_the_row_cut_in_half_by_the_seek(self):
        directory = Path(tempfile.mkdtemp(prefix="hengbot-supervisor-tail-"))
        path = directory / "rows.jsonl"
        rows = [{"index": index, "padding": "x" * 200} for index in range(100)]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        tail = self.checker.tail_rows(path, 3, tail_bytes=1000)
        self.assertEqual([row["index"] for row in tail], [97, 98, 99])

    def test_tail_of_a_missing_file_is_empty(self):
        self.assertEqual(self.checker.tail_rows(Path("nope.jsonl"), 5), [])


if __name__ == "__main__":
    unittest.main()
