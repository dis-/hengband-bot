"""#47 D55 follow-up: the recorded n1-b life-285 upstairs walk past moving mice.

n1-b life-285 (2026-11-01 00:58, build f9c921d32, Lv8 zombie warrior, Yeek
cave 1F, first mining run without escapes or cures): breeding 巨大ハツカネズミ
(race 27, MULTIPLY) filled the corridor south of the door at (17,78) that
leads to the arrival upstairs [23,86].  From decision 1119 to 1136
``fundraise:seek-upstairs`` (``_leave_fundraising_floor`` ->
``_nearest_goal_step`` -> ``_nearest_goal_route``) stepped back onto the cell
it had just left again and again, (15,78)<->(14,77), (13,76)<->(14,75),
(13,75)<->(14,74), HP 111 -> 96, and then meleed the swarm until death.

Root: the goal route was a fresh BFS on every board and live monster cells
are not walkable.  On (15,78) the mouse on (17,78) is in view, so the route
detours north through (14,77) (19 edges); on (14,77) no mouse is in view and
the corridor is open again, so the route goes back through (15,78) (11
edges).  Fix: hengbot/goal_route.py keeps the route the walk chose while
it stays valid (the exploration walk's ``_explore_path`` commitment).

Fixture: tests/fixtures/route-moving-blocker-n1b-285-1101.json.gz
(tests/extract_route_moving_blocker_1101_fixture.py): every board of the
floor visit from the arrival (turn 85511).  A fresh process fed those boards
through the public ``choose_key`` reproduces every recorded key and reason of
decisions 1115-1137 (turns 220409-220640) on the unfixed code; earlier rows
differ by process memory and are not asserted.  The walk's keys go through
the production executor port.
DECLARED CONSTRUCTED: the live argv's --enforce-crossarea-fundraising and
--in-store-shop-ops are set on the policy; the ~f skill reply and the Home
knowledge are the capture's last rows before the arrival; executor replies
are the same board ten game turns later.  A recorded board after a step the
fixed walk would not have taken keeps the recorded position (the capture
cannot show the other cell), so there the walk plans fresh and matches the
record.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_strategies import load_quest_strategies
from tests import test_me_nokey_1031_recorded as nokey
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "route-moving-blocker-n1b-285-1101.json.gz"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
UPSTAIRS = Position(23, 86)
GIANT_MOUSE = 27
WALK_FIRST_TURN = 220409
# Recorded reversals: turn -> (cell stepped from, recorded key back onto it,
# the committed walk's key).
REVERSALS = {
    220457: (Position(15, 78), "3", "9"),
    220473: (Position(15, 78), "3", "7"),
    220525: (Position(13, 76), "9", "1"),
    220587: (Position(13, 75), "9", "1"),
}
OFFSETS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
           "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def _step(position, key):
    dy, dx = OFFSETS[key]
    return Position(position.y + dy, position.x + dx)


def _at(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


class RouteMovingBlockerRecordedTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.case["decisions"]}

    def board(self, turn):
        return next(raw for raw in self.case["boards"] if raw["turn"] == turn)

    def new_policy(self):
        policy = ConservativePolicy(quest_strategies=load_quest_strategies(STRATEGIES))
        policy._monrace_knowledge.update(self.monraces)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv
        first = self.case["boards"][0]
        policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
        policy.consume_home_knowledge(
            tuple(_parse_items(self.case["home"]["knowledge"]["items"], protocol=3)))
        return policy

    def drive(self):
        """Every board through choose_key; the walk's rows (raw, key, reason)."""
        policy, skill, walk = self.new_policy(), self.case["skill"], []
        for raw in self.case["boards"]:
            policy.consume_skill_knowledge(dict(
                copy.deepcopy(skill), turn=raw["turn"],
                player=dict(skill["player"], level=raw["player"]["level"])))
            key = nokey.decide(policy, raw)
            if raw["turn"] >= WALK_FIRST_TURN:
                walk.append((raw, key, policy.last_reason))
                self.post(policy, raw, key)
            if key:
                policy.confirm_key_posted(key)
        return walk

    def test_recorded_rows(self):
        self.assertEqual(self.case["boards"][0]["turn"], 85511)
        self.assertEqual(_at(self.case["boards"][0]), UPSTAIRS)
        self.assertEqual(len(self.recorded), 23)
        for turn, (came_from, back, _) in REVERSALS.items():
            row = self.recorded[turn]
            self.assertEqual((row["key"], row["reason"]), (back, "fundraise:seek-upstairs"))
            self.assertEqual(_step(_at(self.board(turn)), back), came_from, turn)
        # In view from (15,78), out of view from (14,77).
        mice = {(m["y"], m["x"]) for m in self.board(220448)["visible_monsters"]
                if m["race_id"] == GIANT_MOUSE}
        self.assertEqual(mice, {(17, 78)})
        self.assertEqual(self.board(220457)["visible_monsters"], [])
        self.assertEqual((self.recorded[220640]["key"], self.recorded[220640]["reason"]),
                         ("4", "melee"))

    def test_upstairs_walk_keeps_its_route_past_moving_mice(self):
        walk = self.drive()
        previous_step = None
        for raw, key, reason in walk:
            turn, here = raw["turn"], _at(raw)
            if turn in REVERSALS:
                came_from, back, committed = REVERSALS[turn]
                # The recorded board is the cell the walk stepped onto.
                self.assertEqual(here, previous_step, turn)
                self.assertNotEqual(key, back, turn)
                self.assertEqual((key, reason), (committed, "fundraise:seek-upstairs"), turn)
            elif turn in self.recorded:
                row = self.recorded[turn]
                self.assertEqual((key, reason), (row["key"], row["reason"]), turn)
            previous_step = _step(here, key) if key in OFFSETS else None


if __name__ == "__main__":
    unittest.main()
