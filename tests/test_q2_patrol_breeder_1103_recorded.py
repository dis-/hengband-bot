"""q2-patrol-breeder-1103: a latched kill-all quest floor is left, and fought until then.

Recorded: n1-c life-120 (Magic-Eater, Lv21) in Q2 下水道 (KILL_ALL, PRESET+ONCE),
2026-11-03 17:45, the last boards of the stall capture (stall:floor-dwell;
tests/fixtures/q2-patrol-breeder-20261103.json.gz,
tests/extract_q2_patrol_breeder_1103_fixture.py).  36-40 冥界イモムシの大群
(race 213, MULTIPLY) in view; the recorded build walked the final patrol through
them: the breakthrough latch (jsonlog/breeder-floor.json on the server) hid every
weak breeder from the quest's own attack logic (_strategic_subset), and the
navigator, which owns an approved quest's floor, returns above the breakthrough
rung that would have left.

Owner 2026-11-02: 「全滅要求のクエストは達成できないので放棄。」; 2026-11-03: 「Q2で
イモムシを減らす努力が見られない。」

DECLARED CONSTRUCTED: the skill row is the n1-c life-098 row of the breeder-swarm
fixture (the capture holds player_turn rows only); ``_fixed_quest_speed_attempted``
is true; the latch is set by hand where the test says so (the capture's process
had it, the capture's diagnostic state does not hold it); the stalemate case sets
the window to 19 actions at count 36; the recalling boards set ``recalling``
(the recorded process never read the scroll).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from tests import test_breeder_swarm_1102_recorded as swarm
from tests import test_me_staff_loops_1031_recorded as loops


FIXTURE = Path(__file__).with_name("fixtures") / "q2-patrol-breeder-20261103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8", errors="surrogateescape") as _stream:
    CASE = json.load(_stream)
QUEST_FLOOR = (0, 15, 2)
PATROL = "quest-strategy:q2-final-patrol"
RECALL_SLOT = "e"


def new_policy(*, latched):
    policy = loops.new_policy(dict(CASE, home=None), swarm.CASE["skill"], monraces=CASE["monraces"])
    policy._quest_knowledge = load_quest_knowledge(find_quest_definitions(Path(__file__)))
    policy._fixed_quest_speed_attempted = True
    if latched:
        policy._breeder_breakthrough_floor = QUEST_FLOOR
    return policy


def recalling(raw):
    raw = copy.deepcopy(raw)
    raw["player"]["recalling"] = True
    return raw


class Q2LatchedFloorRecordedTest(swarm.PostedSwarmKey):
    def test_recorded_boards_walked_the_patrol_through_the_worms(self):
        self.assertTrue(all(row["reason"] == PATROL for row in CASE["decisions"]))
        self.assertEqual([len(raw["visible_monsters"]) for raw in CASE["boards"]], [40, 38, 36])

    def test_latched_floor_reads_recall_then_fights_until_it_takes_effect(self):
        policy = new_policy(latched=True)
        raw = CASE["boards"][-1]
        key = loops.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("r" + RECALL_SLOT, "breeder-breakthrough:recall"))
        self.assertTrue(policy._returning_to_town)
        self.post(policy, raw, key)
        # The recall delay: the worms in view are attacked, not walked past.
        fired, melee = CASE["boards"][0], CASE["boards"][-1]
        self.assertEqual((loops.decide(policy, recalling(fired)), policy.last_reason),
                         ("fj6", "quest-strategy:q2-fire"))
        self.assertEqual((loops.decide(policy, recalling(melee)), policy.last_reason),
                         ("6", "quest-strategy:melee"))

    def test_twentieth_action_without_a_reduction_leaves(self):
        policy = new_policy(latched=False)
        first, second = CASE["boards"][:2]
        policy._breeder_engagement_floor = QUEST_FLOOR
        policy._breeder_engagement_start_count = 36
        policy._breeder_engagement_start_turn = first["turn"] - 190
        policy._breeder_engagement_actions = 19
        policy._breeder_engagement_last_turn = first["turn"] - 10
        self.assertEqual(loops.decide(policy, first), "fj6")
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)
        self.assertEqual((loops.decide(policy, second), policy.last_reason),
                         ("r" + RECALL_SLOT, "breeder-breakthrough:recall"))


if __name__ == "__main__":
    unittest.main()
