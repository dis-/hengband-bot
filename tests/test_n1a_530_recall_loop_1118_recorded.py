"""Two dives in a row spent at once on the means-spent Recall stop the next 50F+ departure.

n1-a life-530 (2026-11-18 10:29-12:50) went to 51F/52F without the *Destruction* means about
250 times; each dive read Word of Recall on its arrival board (destruction_use.
means_spent_recall_key) and nothing named the loop for over two hours.  The last pair before
the fatal dive, both to 古城 51F: decision 4442 (turn 13135701) and 4542 (13140981); the town
visit after the second read Recall to 51F again at 12:50:43 and the character died there.

means_spent_loop counts a dive whose arrival board starts the means-spent return; two in a row
to the same arrival make the town-to-dungeon boundary (policy_navigation._dungeon_entry_allowed)
refuse a 50F+ departure under the policy final stop ``town:blocked:destruction-means-spent-loop``
(a named stop, not a new destination).

Boards: tests/fixtures/n1a-530-recall-loop-1118.json.xz
(tests/extract_n1a_530_recall_loop_1118_fixture.py), decided in order by one fresh policy
through the public ``choose_key`` (``confirm_key_posted`` after each key).  Only the two arrival
boards' decisions are compared with the record: the town boards are fed for the floor changes,
and a fresh policy without the Home's knowledge does not decide them as the live one did.

DECLARED RECONSTRUCTION (pin_vacuity): the skill knowledge is supplied before each decision (as
tests/test_n1a_525_flee_haste_1115_recorded.py does).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import means_spent_loop
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-recall-loop-1118.json.xz"
FIRST_ARRIVAL, SECOND_ARRIVAL, LAST_TOWN = 13135701, 13140981, 13141224


class N1a530RecallLoop1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def replay(self, boards):
        """One fresh policy deciding ``boards`` in order: (policy, {turn: (board, key, reason,
        streak)})."""
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        answers = {}
        for raw in boards:
            policy.consume_skill_knowledge({
                "player": {"level": raw["player"]["level"]},
                "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
            })
            board = parse_snapshot(copy.deepcopy(raw), self.races)
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            loop = getattr(policy, means_spent_loop.MEMORY, None)
            answers[raw["turn"]] = (board, str(key), policy.last_reason,
                                    loop.streak if loop is not None else None)
        return policy, answers

    def test_the_recorded_arrivals(self):
        for turn in (FIRST_ARRIVAL, SECOND_ARRIVAL):
            self.assertEqual(self.recorded[turn]["reason"], "return:recall", turn)
        floors = {raw["turn"]: (raw["floor"]["dungeon_id"], raw["floor"]["level"])
                  for raw in self.payload["boards"]}
        self.assertEqual((floors[FIRST_ARRIVAL], floors[SECOND_ARRIVAL]), ((12, 51), (12, 51)))
        self.assertEqual(floors[LAST_TOWN], (0, 0))
        self.assertIn(means_spent_loop.STOP_REASON, POLICY_FINAL_STOP_REASONS)

    def test_two_dives_spent_at_once_stop_the_next_deep_departure(self):
        policy, answers = self.replay(self.payload["boards"])
        for turn in (FIRST_ARRIVAL, SECOND_ARRIVAL):
            _board, key, reason, _streak = answers[turn]
            row = self.recorded[turn]
            self.assertEqual((key, reason), (row["key"], row["reason"]), turn)
        self.assertEqual(answers[FIRST_ARRIVAL][3], 1)
        self.assertEqual(answers[SECOND_ARRIVAL][3], 2)
        board = answers[LAST_TOWN][0]
        self.assertTrue(board.in_town)
        self.assertFalse(policy._dungeon_entry_allowed(board, via_recall=True, destination_depth=51))
        self.assertEqual(policy.last_reason, means_spent_loop.STOP_REASON)
        # A destination short of 50F is no part of the loop.
        self.assertFalse(means_spent_loop.looping(policy, 49))

    def test_one_dive_spent_at_once_does_not_stop(self):
        boards = self.payload["boards"]
        start = next(index for index, raw in enumerate(boards) if raw["turn"] == SECOND_ARRIVAL) - 1
        policy, answers = self.replay(boards[start:])
        self.assertEqual(answers[SECOND_ARRIVAL][3], 1)
        self.assertFalse(means_spent_loop.looping(policy, 51))


if __name__ == "__main__":
    unittest.main()
