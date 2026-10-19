"""Recorded pins: town native travel is never posted while the own grid is unseen.

Linux soak c4-a life-014 (Level 24), 2026-10-19 10:38-10:39, town at 22:22
right after a recall arrival.  The worn torch and the pack lantern both had
0 turns of fuel, so every board reported ``can_see_own_grid`` False (the
game's ``!no_lite()``; ``player.status.blind`` was False).  The bot posted the
native-travel macro ``\\x1b`n%.`` (shop:travel); travel-execution.cpp
``decide_travel_step_dir`` refuses every step when ``no_lite()`` or blind
("目が見えない！"), no new board followed, and the entry wait posted the empty
key until ``<no-key-exhausted>`` stopped the bot (twice, before and after a
restart).

Substrate: the restarted process's first three decision inputs, unchanged
(tests/extract_town_unseen_travel_fixture.py), replayed from a fresh policy
through the live response path.  The process restarted, so the fresh policy is
the recorded process's policy; the startup flag
enforce_crossarea_fundraising=True is the recorded one.

DECLARED CONSTRUCTED walls (controls only):
- ``lit``: the same rows with only ``player.can_see_own_grid`` set True -- an
  ordinary town arrival still travels natively;
- ``blind``: the same rows with only ``player.status.blind`` set True -- the
  existing status producer cures blindness with a carried potion first.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "town-unseen-travel-20261019.jsonl.gz"
FIXTURE_SHA256 = "5a3ecdb2a16a1e83c20ef1fb5b779787c4aedd0621fd9627670a729c6c074d81"
DECISIONS = FIXTURE.with_suffix(".decisions.json")
# Input rows consumed before each recorded decision 0, 1, 2.
GROUPS = (4, 2, 3)
TRAVEL_KEY = "\x1b`n%."


def _rows(mode=None):
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    for row in rows:
        if row.get("type") != "player_turn":
            continue
        if mode == "lit":
            row["player"]["can_see_own_grid"] = True
        elif mode == "blind":
            row["player"]["status"]["blind"] = True
    return [json.dumps(row, ensure_ascii=False) + "\n" for row in rows]


class TownUnseenTravelRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        cls.recorded = json.loads(DECISIONS.read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, mode=None):
        lines = _rows(mode)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        policy = _policy(path, self.monrace)
        policy._crossarea_fundraising_enforced = True
        decided, boards, cursor = [], [], 0
        for count in GROUPS:
            _decoded, snapshots = _consume_response_sequence(
                lines[cursor:cursor + count], policy, lambda _key: True,
                self.monrace, knowledge_ledger_path=path / "knowledge.jsonl",
            )
            cursor += count
            board = snapshots[-1]
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            decided.append((key, policy.last_reason))
            boards.append(board)
        return decided, boards

    def test_recorded_process_posted_native_travel_on_unseen_grid(self):
        self.assertEqual(
            [(row["decision_sequence"], row["turn"], row["key"], row["reason"])
             for row in self.recorded],
            [(0, 1068208, "~f\x1b", "periodic:skill-exp-knowledge"),
             (1, 1068208, "~9\x1b\x1b", "home:request-knowledge-scan"),
             (2, 1068208, TRAVEL_KEY, "shop:travel")],
        )
        _decided, boards = self.replay()
        board = boards[2]
        self.assertTrue(board.in_town)
        self.assertIs(board.can_see_own_grid, False)
        self.assertFalse(board.player.blind)
        light = next(item for item in board.equipment if item.is_light)
        self.assertEqual(light.fuel, 0)

    def test_unseen_grid_walks_instead_of_native_travel(self):
        decided, _boards = self.replay()
        self.assertEqual(
            decided[:2],
            [(row["key"], row["reason"]) for row in self.recorded[:2]],
        )
        self.assertEqual(decided[2], ("4", "shop:approach"))

    def test_control_lit_arrival_travels_as_recorded(self):
        decided, boards = self.replay("lit")
        self.assertIs(boards[2].can_see_own_grid, True)
        self.assertEqual(decided[2], (TRAVEL_KEY, "shop:travel"))

    def test_control_blind_arrival_cures_first(self):
        decided, boards = self.replay("blind")
        self.assertTrue(boards[2].player.blind)
        self.assertEqual(decided[2], ("qc", "item:cure-critical"))


if __name__ == "__main__":
    unittest.main()
