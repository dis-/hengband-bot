import tests  # noqa: F401 -- isolate runtime files for bare module runs

import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "item-destroying-breeder-20261006.json"


class ItemDestroyingBreederLeaveRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = json.loads(FIXTURE.read_text(encoding="utf-8"))
        # Race 69 is the visible spawn in the 21:52:00 incident board. Its
        # player-known race data identifies multiplication and an acid touch.
        cls.knowledge = {
            69: MonraceKnowledge(
                max_hp=1,
                speed=110,
                can_summon=False,
                friendly=False,
                can_multiply=True,
                blows=(MonsterBlow("TOUCH", "ACID"),),
            )
        }
        cls.snapshot = parse_snapshot(cls.row, cls.knowledge)

    def test_incident_board_leaves_before_carried_escape_scrolls_are_lost(self):
        self.assertEqual(self.row["turn"], 13223119)
        self.assertEqual(self.row["recorded_decision"]["reason"], "melee")
        self.assertEqual(self.row["recorded_decision"]["visible_hostiles"], 4)
        self.assertEqual(self.snapshot.floor_key[1], 23)
        self.assertEqual(self.snapshot.player.hp, 1069)
        self.assertEqual(len(self.snapshot.visible_monsters), 4)
        self.assertTrue(any(item.is_recall_scroll for item in self.snapshot.inventory))
        self.assertTrue(any(item.is_teleport_scroll for item in self.snapshot.inventory))

        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._skill_exp_request_key = lambda _snapshot: None
        key = policy.choose_key(self.snapshot)

        self.assertEqual(key, "re")
        self.assertEqual(policy.last_reason, "breeder-item-damage:recall")

    def test_three_visible_item_damaging_breeders_keep_the_recorded_fight(self):
        control = replace(
            self.snapshot,
            visible_monsters=self.snapshot.visible_monsters[:3],
        )
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._skill_exp_request_key = lambda _snapshot: None

        key = policy.choose_key(control)

        self.assertTrue(key)
        self.assertEqual(policy.last_reason, "melee")


if __name__ == "__main__":
    unittest.main()

