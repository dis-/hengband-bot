"""n1-c life-217, Quest 33 段3 (2026-11-20 00:45-01:22): the sweep walked round with nothing found.

The run (tests/fixtures/n1c-217-q33-walk-1120.json.gz, extracted by
tests/extract_n1c_217_q33_walk_1120_fixture.py from C:/hengband-backups/pdca/captures/n1c-217-q33-walk-1120)
answered 1,772 decisions, every one quest-strategy:sweep-walk, until the floor-dwell watcher halted it.
The walk went the Freesias' stand [25,73] -> the column [20,39] -> the Fangs' stand [25,6] and back, a
dozen rounds: the 段3 stops that read light found their rooms lit, those that wait had nothing coming
(quest_wait_placement), the last targets' doors stood open; no board showed a hostile, and the quest was
still open.

Owner 2026-11-13 (verbatim): 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して
探す」 and 2026-11-20: 「残りの敵を探す時は感知を使うこと」.  Now a round of the stops with no hostile on any
board, the quest open and no tracked summoner alive (quest_alignment_split no longer refuses a cell),
hands the floor to kill_all_patrol: its detection first, then the walk to what it shows, else its patrol.

DECLARED CONSTRUCTED: the policy is n1-c life-217's town arrival of the same day
(tests/fixtures/quest32-one-turn-kill-1119/n1c-217, tests/test_quest33_alignment_split ``recorded``) with
the recorded board's skill lists given; the tracked summoners' kill lines are set on the navigator as dead
(the run walked only the 段3 stops, which wait for the Queens' death); the player is put on the last stop
(the Freesias' stand [25,73]) with the navigator on it, so that the round ends on the first decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import kill_all_patrol, quest_room_sweep
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import BOKRUG, DAGON, GACHAPIN, IT, QUEEN, QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-q33-walk-1120.json.gz"
DEAD = {IT: 3, DAGON: 3, BOKRUG: 3, QUEEN: 3, GACHAPIN: 3}


class N1c217Q33WalkTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            self.case = json.load(stream)
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.plan = self.policy.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]

    def on_last_stop(self, kills):
        raw = copy.deepcopy(self.case["board"])
        raw["player"]["y"], raw["player"]["x"] = 25, 73
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        snapshot = replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0))
        navigator = _navigator(self.policy, snapshot, QUEST)
        navigator.split_kills = dict(kills)
        stops = quest_room_sweep._stops(self.plan)
        navigator.sweep_stage = len(stops) - 1
        self.assertEqual(stops[-1].get("stand"), [25, 73])
        return snapshot, navigator

    def test_the_recorded_rounds(self):
        self.assertEqual(self.case["reasons"], {quest_room_sweep.WALK_REASON: 1772})
        self.assertEqual(self.case["boards_with_hostiles"], 0)
        turns = [tuple(cell) for cell in self.case["turns"]]
        self.assertGreaterEqual(turns.count((25, 73)), 10)
        self.assertGreaterEqual(turns.count((25, 6)), 10)

    def test_a_round_with_nothing_found_hands_the_floor_to_the_patrol(self):
        snapshot, navigator = self.on_last_stop(DEAD)
        # The last stop passed: the round ends with no hostile met, and the same board is the
        # patrol's (n1-a life-537 2026-11-25: the hand-over comes before the rounds' bound).
        self.policy.choose_key(snapshot)
        self.assertTrue(navigator.sweep_found_nothing)
        self.assertTrue(self.policy.last_reason.startswith(kill_all_patrol.DETECT_REASON), self.policy.last_reason)
        self.policy.choose_key(replace(snapshot, turn=snapshot.turn + 1))
        self.assertTrue(self.policy.last_reason.startswith(kill_all_patrol.REASON), self.policy.last_reason)

    def test_a_tracked_summoner_alive_keeps_the_sweep(self):
        # A Queen alive (and never seen here): the plan's 段2 goes on, its remaining-enemy detection
        # first (quest_detect_remaining), and the split keeps refusing; the patrol is not asked.
        alive = {**DEAD, QUEEN: 2}
        snapshot, navigator = self.on_last_stop(alive)
        self.policy.choose_key(snapshot)
        self.assertTrue(self.policy.last_reason.startswith("me-power:quest-remaining-unseen"), self.policy.last_reason)
        navigator.sweep_found_nothing = True
        self.policy.choose_key(replace(snapshot, turn=snapshot.turn + 1))
        self.assertFalse(self.policy.last_reason.startswith(kill_all_patrol.REASON), self.policy.last_reason)


if __name__ == "__main__":
    unittest.main()
