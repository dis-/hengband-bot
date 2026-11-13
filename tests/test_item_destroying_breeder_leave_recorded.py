import tests  # noqa: F401 -- isolate runtime files for bare module runs

import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import policy_fixtures as fixtures


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

    def on_the_grid_map(self):
        return [monster for monster in self.snapshot.visible_monsters
                if self.snapshot.grid_at(monster.position) is not None
                and self.snapshot.grid_at(monster.position).has_monster]

    def test_incident_board_leaves_before_carried_escape_scrolls_are_lost(self):
        self.assertEqual(self.row["turn"], 13223119)
        self.assertEqual(self.row["recorded_decision"]["reason"], "melee")
        self.assertEqual(self.row["recorded_decision"]["visible_hostiles"], 4)
        self.assertEqual(self.snapshot.floor_key[1], 23)
        self.assertEqual(self.snapshot.player.hp, 1069)
        # The game listed 16; the recorded 4 are those the grid map exported.
        # Since 6cce55f61a the parser keeps the rest at their exported y/x.
        self.assertEqual(len(self.snapshot.visible_monsters), 16)
        self.assertEqual(len(self.on_the_grid_map()), 4)
        self.assertTrue(any(item.is_recall_scroll for item in self.snapshot.inventory))
        self.assertTrue(any(item.is_teleport_scroll for item in self.snapshot.inventory))

        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._skill_exp_request_key = lambda _snapshot: None
        key = policy.choose_key(self.snapshot)

        self.assertEqual(key, "re")
        self.assertEqual(policy.last_reason, "breeder-item-damage:recall")

    def test_reliable_destruction_comes_before_the_floor_exit_scrolls(self):
        """Owner 2026-11-05 (増殖する敵にも「今のまま全部に使う」) and 2026-11-13: the leave uses
        *Destruction* before Teleport Level, Recall and Teleportation.  DECLARED CONSTRUCTED:
        a known staff of *Destruction* in the pack, device skill 60 (80%)."""
        staff = fixtures.item("x", TVAL_STAFF, SV_STAFF_DESTRUCTION, known=True, charges=5,
                              name="*破壊*の杖 (5回分)")
        board = replace(self.snapshot, inventory=[*self.snapshot.inventory, staff],
                        player=replace(self.snapshot.player, device_skill=60))
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._skill_exp_request_key = lambda _snapshot: None

        self.assertEqual((policy.choose_key(board), policy.last_reason),
                         ("ux", "emergency:destruction"))

    def test_three_visible_item_damaging_breeders_keep_the_recorded_fight(self):
        control = replace(
            self.snapshot,
            visible_monsters=self.on_the_grid_map()[:3],
        )
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        policy._skill_exp_request_key = lambda _snapshot: None

        key = policy.choose_key(control)

        self.assertTrue(key)
        self.assertEqual(policy.last_reason, "melee")


if __name__ == "__main__":
    unittest.main()

