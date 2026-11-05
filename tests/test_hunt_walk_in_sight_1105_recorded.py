"""The walk to the hunted target does not trade steps with seek-loot (hunt_target.route_key).

Recorded n1-a life-485, Zombie warrior Lv34, Angband 38F, RANDOM quest 45, target
『マニマニのあくま』 (race 1293, NEVER_MOVE) at (16,116); retired 2026-11-05 08:48 on
loop-detected at cells (16,95), (16,96), (16,97).  Every board of the floor is recorded
(tests/extract_hunt_walk_in_sight_1105_fixture.py) and every decision goes through the
public choose_key.

 - (16,96) is 20 from the target, the game's sight limit, along a straight corridor.  The
   live bot's hunt:detected-target stopped there because a hostile was in sight, the hunt
   rung (8) and the ranged ladder (10) did not reach it, so seek-loot read ``4`` toward
   the floor items left at x 93 and below; at (16,95) the target was out of sight, and the
   walk, above loot in the ladder, read ``6``.
 - (21,121) / (22,121), earlier on the floor: the walk gave the cell up at (21,121), where
   no frontier was closer than the player; seek-loot read ``2``; at (22,121) a detection
   showed the target again, the same frontier was closer than the player, and the walk
   read ``8``.

DECLARED CONSTRUCTED: the skill list the live process had read; the player moved along the
recorded corridor to 10 from the target; the pack without its ammunition.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import hunt_target
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from test_esp_threat_rest_recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "hunt-walk-in-sight-1105.json.xz"
TARGET_RACE = 1293
LOOP_FIRST_TURN, LOOP_LAST_TURN = 2567768, 2568135
FIRST_SIGHT_TURN = 2567768  # (16,96); recorded seek-loot ``4``
BLIND_TURN = 2567773  # (16,95), the board after it on the record
FRONTIER_GIVEN_UP_TURN = 2567249  # (21,121); recorded seek-loot ``2``
FRONTIER_RETURN_TURN = 2567253  # (22,121); recorded hunt:detected-target ``8``
AMMO_TVAL = 18


class HuntWalkInSightRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lines = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.boards = [json.loads(line) for line in lines]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        policy = HengbotPolicy(monrace_knowledge=cls.races)
        # DECLARED: the skill list the live process had read.
        policy.consume_skill_knowledge(
            {"knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}, "player": {"level": 34}})
        policy.prime(parse_snapshot(cls.boards[0], cls.races))
        cls.decisions = {}
        cls.before = {}
        for raw in cls.boards:
            if raw["turn"] in (FIRST_SIGHT_TURN, BLIND_TURN):
                cls.before[raw["turn"]] = copy.deepcopy(policy)
            cls.decisions[raw["turn"]] = cls.decide(policy, raw)

    @classmethod
    def decide(cls, policy, raw):
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), cls.races)))
        return key, policy.last_reason

    def board(self, turn):
        return next(raw for raw in self.boards if raw["turn"] == turn)

    def test_the_walk_goes_on_when_the_target_comes_into_sight(self):
        raw = self.board(FIRST_SIGHT_TURN)
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (16, 96))
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]],
                         [(TARGET_RACE, 16, 116)])
        self.assertEqual(self.decisions[FIRST_SIGHT_TURN], ("6", hunt_target.REASON))

    def test_no_board_of_the_recorded_loop_steps_back(self):
        loop = {turn: decision for turn, decision in self.decisions.items()
                if LOOP_FIRST_TURN <= turn <= LOOP_LAST_TURN}
        self.assertGreater(len(loop), 35)
        self.assertEqual({key for key, _reason in loop.values()}, {"6"})

    def test_a_shown_target_does_not_send_the_walk_back_to_a_spent_frontier(self):
        self.assertEqual(self.decisions[FRONTIER_GIVEN_UP_TURN], ("2", "seek-loot"))
        self.assertEqual(self.decisions[FRONTIER_RETURN_TURN], ("2", "seek-loot"))

    def test_the_walk_ends_in_the_shot(self):
        raw = copy.deepcopy(self.board(FIRST_SIGHT_TURN))
        raw["player"]["x"] = 106  # DECLARED: 10 from the target, along the row
        policy = copy.deepcopy(self.before[FIRST_SIGHT_TURN])
        _key, reason = self.decide(policy, raw)
        self.assertEqual(reason, "ranged:fire-target")

    def test_without_ammunition_the_cell_is_given_up_and_loot_is_collected(self):
        # DECLARED: the pack without its ammunition.  The hunt rung refuses this target's
        # melee, so no rung would take it at the end of the walk.
        policy = copy.deepcopy(self.before[FIRST_SIGHT_TURN])
        for turn in (FIRST_SIGHT_TURN, BLIND_TURN):
            raw = copy.deepcopy(self.board(turn))
            raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != AMMO_TVAL]
            self.assertEqual(self.decide(policy, raw), ("4", "seek-loot"), turn)


if __name__ == "__main__":
    unittest.main()
