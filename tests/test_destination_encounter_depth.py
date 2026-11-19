"""The floor an unconstrained loadout search scores against (warrior_optimization)."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from types import SimpleNamespace

from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.warrior_optimization import destination_encounter_depth


def knowledge(*levels):
    return {index + 1: MonraceKnowledge(max_hp=10, speed=110, can_summon=False,
                                        friendly=False, level=level)
            for index, level in enumerate(levels)}


class DestinationEncounterDepthTest(unittest.TestCase):
    def test_the_deepest_reached_floor_not_the_recall_side_dungeon(self):
        # n1-c life-205: recall set to 23F of dungeon 3, 80F reached in Angband.
        board = SimpleNamespace(recall_dungeon_id=3, recall_depth=23,
                                dungeon_recall_depths={1: 80, 3: 23, 12: 62})
        self.assertEqual(destination_encounter_depth(board, knowledge(10, 127)), 80)

    def test_angband_is_capped_at_95(self):
        board = SimpleNamespace(recall_dungeon_id=1, recall_depth=99,
                                dungeon_recall_depths={1: 99, 12: 65})
        self.assertEqual(destination_encounter_depth(board, knowledge(127)), 95)

    def test_no_depth_and_shallow_knowledge(self):
        board = SimpleNamespace(recall_dungeon_id=0, recall_depth=0, dungeon_recall_depths={})
        self.assertEqual(destination_encounter_depth(board, knowledge(5, 40)), 40)
        deep = SimpleNamespace(recall_dungeon_id=1, recall_depth=60, dungeon_recall_depths={1: 60})
        self.assertEqual(destination_encounter_depth(deep, knowledge(5, 40)), 40)


if __name__ == "__main__":
    unittest.main()
