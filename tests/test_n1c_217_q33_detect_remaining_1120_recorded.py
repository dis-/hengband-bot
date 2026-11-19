"""n1-c life-217, Quest 33 段2: the remaining enemies looked for with the detection first.

Owner 2026-11-20 (verbatim): 「残りの敵を探す時は感知を使うこと」.  The Queens were never on the board in
段2 (placed at [20,69] [20,72] [22,70], beyond the telepathy's 20 from every cell the plan stood on:
tests/fixtures/n1c-217-q33-queen-wait-1119.json.gz, the 20:31-20:59 run), and the plan chose its
waits and its approach from those placements; the Gachapins were on the board only within the
telepathy (tests/fixtures/n1c-217-q33-open-path-1119.json.gz, the 23:52 run).

Now (quest_detect_remaining): a tracked race with members living and no cell known (on the board, or
kept from an earlier board for at most the time it takes to make 10 moves at its speed) is detected
first: the Magic-Eater's absorbed Rod of Detection (detect_all, every monster within 30, 45 through
Powerful Activation, which me_powers uses when safe, owner 2026-11-01 「安全なら強力発動で使う」).  A
detected monster stays on the board for the next board or two (core/player-processor.cpp:410-418);
the plan keeps its cell and the wait reader reads it in place of the placement.  The detection is not
cast again from where it covered within that time.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``)
with the recorded board's skill lists given (the restarted process read them first); the kill lines of
the Its, Dagons and Bokrugs are set on the navigator (the seeded restart record held them); the board
the detection shows is the recorded one with the three Queens added as detected at the cells named.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import me_powers, quest_detect_remaining, quest_lure_approach, quest_wait_placement
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, GACHAPIN, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURES = Path(__file__).with_name("fixtures")
KILLS = {IT: 3, DAGON: 3, BOKRUG: 3}
QUEENS_SHOWN = [(21, 70), (20, 72), (22, 69)]


class N1c217Q33DetectRemainingTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
        with gzip.open(FIXTURES / "n1c-217-q33-queen-wait-1119.json.gz", "rt", encoding="utf-8") as stream:
            self.raw = json.load(stream)["board"]

    def board(self, raw, turn=None):
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        snapshot = replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0))
        if turn is not None:
            snapshot = replace(snapshot, turn=turn)
        return snapshot

    def navigator(self, snapshot):
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.split_kills = dict(KILLS)
        return navigator

    def with_queens(self):
        raw = copy.deepcopy(self.raw)
        record = next(m for m in raw["detected_monsters"] if m["race_id"] == GACHAPIN)
        for index, (y, x) in enumerate(QUEENS_SHOWN):
            raw["detected_monsters"].append({**record, "race_id": QUEEN, "index": 200 + index, "y": y, "x": x,
                                             "detected": True, "esp": False})
        return raw

    def test_the_queens_were_never_on_the_board(self):
        snapshot = self.board(self.raw)
        self.assertFalse([m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters) if m.race_id == QUEEN])
        navigator = self.navigator(snapshot)
        self.assertEqual(quest_detect_remaining.missing(self.policy, snapshot, navigator, self.plan), [QUEEN])

    def test_the_first_decision_detects(self):
        snapshot = self.board(self.raw)
        self.navigator(snapshot)
        self.policy.choose_key(snapshot)
        self.assertTrue(self.policy.last_reason.startswith(
            f"{me_powers.REASON}:quest-remaining-unseen:detect-all"), self.policy.last_reason)
        navigator = self.policy._quest_navigators[QUEST]
        self.assertEqual(len(navigator.remain_detections), 1)
        # The same board again (nothing shown yet): no second detection from here, the plan goes on.
        self.policy.choose_key(snapshot)
        self.assertEqual(self.policy.last_reason, quest_lure_approach.LURE_WALK_REASON)

    def test_the_detected_cells_are_kept_and_read_in_place_of_the_placements(self):
        shown = self.board(self.with_queens())
        navigator = self.navigator(shown)
        quest_detect_remaining.observe(self.policy, shown, navigator, self.plan)
        self.assertEqual(quest_detect_remaining.missing(self.policy, shown, navigator, self.plan), [])
        # The next board: the mark gone (core/player-processor.cpp), the cells kept while fresh.
        later = self.board(self.raw, turn=shown.turn + 40)
        quest_detect_remaining.observe(self.policy, later, navigator, self.plan)
        read = quest_wait_placement.reader(self.policy, later, navigator, self.plan)
        queens = sorted(row.cell for row in read.rows if row.race == QUEEN)
        self.assertEqual(queens, sorted(QUEENS_SHOWN))
        self.assertFalse([row for row in read.rows if row.key[0] == "placed" and row.race == QUEEN])
        self.assertEqual(quest_detect_remaining.missing(self.policy, later, navigator, self.plan), [])
        # A Queen (+10: 20 energy a game turn, monster-processor.cpp) may make 10 moves in 50 game turns.
        self.assertEqual(quest_detect_remaining.stale_turns(self.policy, QUEEN), 50)
        stale = self.board(self.raw, turn=shown.turn + 51)
        self.assertEqual(quest_detect_remaining.missing(self.policy, stale, navigator, self.plan), [QUEEN])


if __name__ == "__main__":
    unittest.main()
