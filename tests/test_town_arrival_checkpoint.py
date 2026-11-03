"""Owner 2026-11-03: save the policy at each town arrival and put it in the stop records.

A viewing bot runs one process for most of a life, so the incident capture's
policy-state.json and decision tail could not rebuild a town visit (three town
stops of 2026-11-03 could not be reproduced).  The flight recorder now keeps
the pre-decision checkpoint of the newest three town arrivals with the visit's
journal, and an incident capture copies the newest one.

The live run below is the recorded 2026-10-05 town visit of the ownership
corpus (s33 window 013108: Home scan, three shop visits, save, dump, restock
wait) decided through the public choose_key with the production flight
recorder and decision-row writer around it, as cli._run_follow does.  Its
incident capture is then replayed by tests/replay_town_arrival.py.
"""
import tests  # noqa: F401  -- live runtime-file isolation

import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot.cli import _consume_response_sequence, _write_decision
from hengbot.flight_recorder import FlightRecorder
from hengbot.policy import staged_prompt_chain_matches
from hengbot import town_arrival_checkpoint
from hengbot.town_arrival_checkpoint import (
    DIRECTORY, JOURNAL_FILE, KEEP_VISITS, TRUNCATED_FILE, TownArrivalRecorder,
    copy_latest_into, visits,
)
from replay_town_arrival import replay
from town_work_corpus import MANIFEST, monraces, new_policy, read_json


WINDOW = ("s33-phase2b-shadow-20261004/autorecover-20261005-013108-"
          "town-blocked-departure-unsatisfiable.bot-decisions.jsonl.gz")
# The CLI's wall-clock timers fired on these recorded decisions.
TIMERS = {"periodic:game-save": "request_game_save",
          "periodic:character-dump": "request_character_dump"}


def live_visit(root: Path) -> tuple[Path, list[str]]:
    """Decide the recorded visit as the follow loop does; freeze its capture."""
    window = {w["name"]: w for w in read_json(MANIFEST)["windows"]}[WINDOW]
    policy = new_policy(root)
    policy._crossarea_fundraising_enforced = True
    policy._in_store_ops_enabled = True
    log = root / "jsonlog" / "bot-decisions.jsonl"
    log.parent.mkdir()
    recorder = FlightRecorder(log.parent, root / "incident-captures")
    keys = []
    for index, step in enumerate(window["steps"]):
        lines = [json.dumps(raw) + "\n" for raw in step["inputs"]]
        recorder.record_snapshot_lines(lines)
        _, boards = _consume_response_sequence(
            lines, policy, lambda _key: True, monraces(),
            knowledge_ledger_path=root / "knowledge.jsonl")
        board = boards[-1]
        if index == 0:
            policy.prime(board)
        if step["reason"] in TIMERS:
            getattr(policy, TIMERS[step["reason"]])()
        recorder.before_decision(policy, board, lines[-1].rstrip("\n"), None)
        key = policy.choose_key(board)
        recorder.decided(policy, key)
        _write_decision(log, board, key, policy.last_reason, policy)
        recorder.after_decision(policy, board)
        keys.append(key)
        if not key:
            break
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    capture = recorder.freeze("town-blocked-test", policy, board, log, [policy.last_reason])
    return capture, keys


class TownArrivalCheckpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory(prefix="town-arrival-")
        cls.capture, cls.keys = live_visit(Path(cls.directory.name))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_only_the_newest_three_arrivals_are_kept(self):
        with TemporaryDirectory() as raw:
            recorder = TownArrivalRecorder(Path(raw) / DIRECTORY)
            policy = SimpleNamespace(_floor_key=None, _decision_sequence=0)
            for turn in range(1, 6):
                board = SimpleNamespace(in_town=True, floor_key=(0, 0, 1), turn=turn)
                policy._floor_key = (1, 5, 0)  # back from the dungeon
                recorder.before_decision(policy, board, f'{{"turn":{turn}}}', None)
                policy.last_reason = "town:wait"
                recorder.decided(policy, "5")
            kept = visits(recorder.root)
            self.assertEqual(len(kept), KEEP_VISITS)
            self.assertEqual([path.name.rpartition("-turn")[2] for path in kept],
                             ["3", "4", "5"])
            for visit in kept:
                self.assertEqual(sorted(p.name for p in visit.iterdir()), [
                    "arrival.json", "board.json", JOURNAL_FILE, "policy.pkl"])

    def test_capped_journal_stops_and_a_final_journal_is_linked(self):
        """2026-11-03: 11-57 MB captures; a capped or final journal is shared."""
        with TemporaryDirectory() as raw:
            recorder = TownArrivalRecorder(Path(raw) / DIRECTORY)
            policy = SimpleNamespace(_floor_key=(1, 5, 0), _decision_sequence=7,
                                     last_reason="town:wait")
            board = SimpleNamespace(in_town=True, floor_key=(0, 0, 1), turn=1)
            original = town_arrival_checkpoint.JOURNAL_LIMIT_BYTES
            town_arrival_checkpoint.JOURNAL_LIMIT_BYTES = 1
            try:
                for _ in range(3):
                    recorder.before_decision(policy, board, '{"turn":1}', None)
                    recorder.decided(policy, "5")
                    policy._floor_key = board.floor_key  # the same visit goes on
                    policy._decision_sequence += 1
            finally:
                town_arrival_checkpoint.JOURNAL_LIMIT_BYTES = original
            visit = recorder.visit
            with gzip.open(visit / JOURNAL_FILE, "rt", encoding="utf-8") as stream:
                self.assertEqual(len(stream.readlines()), 1)  # the prefix stays
            self.assertEqual(json.loads((visit / TRUNCATED_FILE).read_text(
                encoding="utf-8"))["first_unjournalled_decision_sequence"], 8)
            self.assertIsNone(recorder.growing_visit())
            capture = Path(raw) / "capture"
            capture.mkdir()
            copy_latest_into(recorder.root, capture, b"",
                             growing=recorder.growing_visit())
            self.assertTrue(os.path.samefile(capture / DIRECTORY / JOURNAL_FILE,
                                             visit / JOURNAL_FILE))

    def test_incident_capture_holds_the_arrival_checkpoint_and_visit_rows(self):
        visit = self.capture / DIRECTORY
        meta = json.loads((self.capture / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(meta["town_arrival"])
        for name in ("policy.pkl", "board.json", "arrival.json", JOURNAL_FILE,
                     "decisions.jsonl"):
            self.assertTrue((visit / name).is_file(), name)
        with gzip.open(visit / JOURNAL_FILE, "rt", encoding="utf-8") as stream:
            journal = [json.loads(line) for line in stream]
        rows = [json.loads(line) for line in
                (visit / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([entry["key"] for entry in journal], self.keys)
        # The decision-log rows of the visit (the arrival's row and on).
        self.assertEqual([row["key"] for row in rows[-len(self.keys):]], self.keys)
        self.assertLessEqual(len(rows), len(self.keys) + 1)
        self.assertEqual((visit / "board.json").read_text(encoding="utf-8"),
                         journal[0]["line"])

    def test_replay_from_the_capture_decides_the_recorded_keys(self):
        result = replay(self.capture)
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(self.keys))
        self.assertGreaterEqual(result.matched_rows, 5)


if __name__ == "__main__":
    unittest.main()
