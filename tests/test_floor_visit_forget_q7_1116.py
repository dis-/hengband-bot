"""Every memory keyed by the floor key alone is forgotten on a floor change (owner 2026-11-15, Q7).

Owner 「階が変わったら全部消す」: the floor key is (dungeon, level, quest), so a later level of the same
depth has the same key; a memory compared with the key alone was read on that new level.  The
floor change forgets every row of floor_visit_memory ``VISIT_MEMORIES`` (one registry; the memories
kept on purpose are its ``KEPT``, each with its reason, and scripts/cross_rule_lint.py fails on a
memory stored with the floor key that is in neither).

Recorded: n1-b life-397's 60F visit (tests/test_n1b_397_deep_stuck_1115_recorded), its stuck board
answered through the public ``choose_key`` with the absorbed Stone to Mud: the stuck escape records
the goals it reached (deep_teleport ``STUCK_MEMORY``).  DECLARED CONSTRUCTED: a goal reached
there (the arrival stairs), kept on a later board of the same level and forgotten on the next
board on a level below (the same board with the level 61).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import deep_teleport, floor_visit_memory
from tests import test_n1b_397_deep_stuck_1115_recorded as stuck


class FloorChangeForgetsTest(unittest.TestCase):
    def test_the_stuck_goals_are_forgotten_by_a_floor_change(self):
        _after, policy, raw, _key, _reasons = stuck._replay(sent_away=False)
        stuck._with_stone_to_mud(policy, raw)
        key, reason, _board = stuck._decide(policy, raw)
        self.assertEqual(reason, deep_teleport.STUCK_MELT_REASON + stuck.CAST_SUFFIX)
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED: a goal the stuck escape reached on this level.
        board = policy.with_known_skill_exp(stuck.parse_snapshot(copy.deepcopy(raw), stuck.MONRACE))
        setattr(policy, deep_teleport.STUCK_MEMORY,
                (board.floor_key, frozenset({stuck.ARRIVAL_STAIRS})))
        same = dict(copy.deepcopy(raw), turn=raw["turn"] + 50, messages=[])
        stuck._decide(policy, same)
        self.assertEqual(getattr(policy, deep_teleport.STUCK_MEMORY)[0], board.floor_key)
        below = copy.deepcopy(raw)
        below["floor"]["level"] = 61
        below["turn"] = raw["turn"] + 100
        below["messages"] = []
        stuck._decide(policy, below)
        self.assertIsNone(getattr(policy, deep_teleport.STUCK_MEMORY, None))

    def test_the_registry_holds_the_memories_of_the_review(self):
        rows = {row[0] for row in floor_visit_memory.VISIT_MEMORIES}
        for attribute in ("_deep_stuck_reached", "_mining_scroll_used_floor", "_anaguma_retry",
                          "_blind_cure_futile_floor", "_tunnel_attempt_memory"):
            self.assertIn(attribute, rows)
        self.assertFalse(rows & set(floor_visit_memory.KEPT))


if __name__ == "__main__":
    unittest.main()
