"""q2-live-1105: Q2's plan survives a teleport and a restart.

Recorded: n1-b life-316 (Zombie Magic-Eater, Lv20, HP 257) in Q2 下水道, 2026-11-05 15:21:59-15:22:14
(tests/fixtures/q2-live-20261105.json.gz, tests/extract_q2_live_1105_fixture.py).  Replayed on the
pre-fix code every decided board but the first gave the recorded reason: 41 of 42 in the first
process, 156 of 156 after the restart.

The first process walked beside a puddle, waited there, read Teleport at HP 252/257, landed at
[13,60] and waited 37 times there, because the map reader read Q2's water corridors as walls and
no route led back.  The restart then took the known cells around the landing for progress past
the blue icky things.

DECLARED CONSTRUCTED: the skill row is the n1-c life-098 row of the breeder-swarm fixture; the
first board's Light power is not in that row (the recorded first key was the absorbed Light, the
replay's is the shot of the second board); boards do not follow from any key the fixed code
decides differently from the record.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from hengbot.policy_constants import Q2_POST_BLUE_SEQUENCE
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "q2-live-20261105.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    CASE = json.load(_stream)
FIRST = CASE["first"]
RESTART = CASE["restart"]
RECOMMIT = "quest-strategy:q2-breeder-recommit"
APPROACH = "quest-strategy:q2-approach-residual-multiplier"
CONTACT = 3  # [1,3], beside the puddle
LANDING_WAIT = 5  # the first row at [13,60] with nothing in view


def new_policy(row, *, from_town=False):
    case = {"boards": [row["board"]], "home": None}
    policy = loops.new_policy(case, swarm.CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(find_quest_definitions(Path(__file__)))
    if from_town:
        policy._q2_reconnect_recovery_floor = None
    return policy


def replay(rows, policy):
    """Decide ``rows`` in order; (key, reason) per row."""
    decided = []
    for row in rows:
        key = loops.decide(policy, copy.deepcopy(row["board"]))
        decided.append((key, policy.last_reason))
        if key:
            policy.confirm_key_posted(key)
    return decided


class PuddleContactTest(swarm.PostedSwarmKey):
    def test_a_touching_puddle_is_left_for_a_cell_with_a_clear_lane(self):
        # [1,3]: the rat at [3,1] behind the puddle at [2,2], which just touched the player.
        policy = new_policy(FIRST[0], from_town=True)
        replay(FIRST[:CONTACT], policy)
        row = FIRST[CONTACT]
        key = loops.decide(policy, copy.deepcopy(row["board"]))
        self.assertEqual((row["key"], row["reason"]), ("rh", "no-wait:escape-scroll"))
        # To [2,4]: two from either puddle, on the way to [3,4] level with the rat.
        self.assertEqual((key, policy.last_reason), ("3", APPROACH))
        self.post(policy, row["board"], key)


class TeleportLandingTest(swarm.PostedSwarmKey):
    def test_the_landing_has_a_route_back_to_the_rat(self):
        # The rat last seen at [3,1] is 80 steps away over the shallow water.
        policy = new_policy(FIRST[0], from_town=True)
        replay(FIRST[:LANDING_WAIT], policy)
        row = FIRST[LANDING_WAIT]
        key = loops.decide(policy, copy.deepcopy(row["board"]))
        self.assertEqual((row["key"], row["reason"]), ("5", "quest:blocked:q2-breeder-recommit"))
        self.assertEqual((key, policy.last_reason), ("9", RECOMMIT))
        self.post(policy, row["board"], key)

    def test_a_last_seen_cell_no_walk_reaches_gives_way_to_the_plan(self):
        # DECLARED CONSTRUCTED: the phases past the blue icky things are done (the state of no
        # recorded board) and the breeder was last seen on the deep water of the blue room.
        row = FIRST[LANDING_WAIT]
        policy = new_policy(row)
        policy._q2_reconnect_recovery_floor = None
        policy._q2_breach_complete = policy._q2_blue_recovery_complete = True
        policy._q2_cleared_races.update({86, 153, 252})
        policy._q2_surveyed_placements.update(
            cell for _, _, placements in Q2_POST_BLUE_SEQUENCE for cell in placements)
        policy._q2_breeder_last_seen = Position(10, 45)
        policy._q2_breeder_last_seen_floor = (0, 15, 2)
        key = loops.decide(policy, copy.deepcopy(row["board"]))
        self.assertIsNone(policy._q2_breeder_last_seen)
        self.assertNotEqual(key, "5", policy.last_reason)
        self.assertTrue(policy.last_reason.startswith("quest-strategy:q2-phase-"), policy.last_reason)
        self.post(policy, row["board"], key)


if __name__ == "__main__":
    unittest.main()
