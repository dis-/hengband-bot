"""n1-b life-411 (Magic-Eater Lv50), 2026-11-18 22:40: stall:town:wait-recall.

Recorded: tests/fixtures/n1b-411-1118/town-wait-recall-2240.json.gz (the capture's last board
before 「rea」, its last board, and the decision rows from the read onwards).

In town the bot read Word of Recall at game turn 7478763 and waited ('5') 103 times.  The recall
was armed (player.recalling from the next board on) and every wait consumed game time (~2.8 game
turns each at speed +26): at the stop only 283 game turns had passed.  Hengband counts the recall
down once per TURNS_PER_TICK (10) game turns from randint0(21) + 15 ticks
(spell-kind/spells-world.cpp recall_player, world/world-movement-processor.cpp execute_recall), so
the countdown may run 350 game turns and was still legitimately pending.  The server's stall
watcher saw ~100 identical rows (20 KB each, its whole 2 MB tail) and halted the bot: the decision
rows did not carry the one fact that bounds the hold, ``player.recalling``.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import _decision_record
from hengbot.model import parse_snapshot

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-1118" / "town-wait-recall-2240.json.gz"
READ_TURN = 7478763
STOP_TURN = 7479046
# randint0(21) + 15 ticks of TURNS_PER_TICK game turns.
RECALL_MAX_GAME_TURNS = (20 + 15) * 10


def case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def board(fixture, turn):
    raw = next(row for row in fixture["rows"] if row["turn"] == turn)
    return parse_snapshot(copy.deepcopy(raw))


class TownWaitRecallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = case()

    def test_recorded_scene(self):
        reasons = [(row["turn"], row["key"], row["reason"]) for row in self.case["decisions"]]
        self.assertIn((READ_TURN, "rea", "town:recall-to-angband"), reasons)
        waits = [row for row in self.case["decisions"] if row["turn"] > READ_TURN]
        self.assertEqual(len(waits), 103)
        self.assertTrue(all((row["key"], row["reason"]) == ("5", "town:wait-recall") for row in waits))
        # Every wait advanced the game clock; the countdown was still within its range.
        turns = [row["turn"] for row in waits]
        self.assertEqual(turns, sorted(turns))
        self.assertLess(STOP_TURN - READ_TURN, RECALL_MAX_GAME_TURNS)
        self.assertFalse(board(self.case, READ_TURN).player.recalling)
        self.assertTrue(board(self.case, STOP_TURN).player.recalling)

    def test_the_decision_row_carries_the_recall_countdown(self):
        """An external watcher can tell the bounded recall hold from a stall by the row alone."""
        waiting = _decision_record(board(self.case, STOP_TURN), "5", "town:wait-recall")
        self.assertIs(waiting["player"]["recalling"], True)
        before = _decision_record(board(self.case, READ_TURN), "rea", "town:recall-to-angband")
        self.assertIs(before["player"]["recalling"], False)


if __name__ == "__main__":
    unittest.main()
