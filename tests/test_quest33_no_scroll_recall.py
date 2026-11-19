"""QUEST_33 (クローン地獄): no Word of Recall for a shortage of Teleportation scrolls (owner 2026-11-19).

n1-b failed Quest 33 at 2026-11-19 10:32: nine Teleportation scrolls read to disengage from summons
and two more burned left two in the pack, under the plan's ``abort_conditions.recall_below_teleports``
3, and the plan read Word of Recall (the ONCE quest failed, quest.cpp leave_quest_check).

Owner 2026-11-19, verbatim: 「Q33内ではテレポートの巻物の不足による帰還は却下する」.  QUEST_33 names
``recall_below_teleports`` 0 (once_quest_recall.below_scroll_floor: never below), so its recall
hold (``held``) stays on whatever the scroll count, HP line or not, and the plan's give-up rung
(quest_plan_base._give_up) never reads.  The HP line and the 即死 rung still teleport while a
scroll or the absorbed Teleportation is left; with none left, below the line a potion is drunk.

DECLARED CONSTRUCTED: every board is the recorded n1-b town arrival of 2026-11-19
(tests/fixtures/quest32-one-turn-kill-1119, Magic-Eater Lv50, 15 Scrolls of Teleportation) moved onto
the Q33 floor with the quest map as known grids (tests/test_quest33_summon_answer), a Dagon of the
roster in view that has not summoned, and the Teleportation scrolls cut to the count the test names.
The n1-b failure itself is not recorded in this tree; the boards stand for its situation.  The
control puts back the shipped value before this change (3) on the loaded profile.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from dataclasses import replace

from hengbot import once_quest_recall, quest_plan_base, quest_room_sweep, threat_tiers
from hengbot.model import SV_SCROLL_TELEPORT, TVAL_SCROLL
from hengbot.monrace_knowledge import _strip_jsonc
from tests.test_quest33_alignment_split import DAGON, QUEST, STRATEGIES
from tests import test_quest33_summon_answer as summon_tests

RECALL_REASON = quest_plan_base.RECALL_REASON


def _is_teleport_scroll(item):
    return item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_TELEPORT


class Quest33NoScrollRecallTest(summon_tests.Quest33SummonAnswerTest):
    """The summon-answer floor boards (module docstring); its own tests are not re-run here."""

    def setUp(self):
        super().setUp()
        self.profile = self.policy.approved_quest_strategy(QUEST)

    def with_scrolls(self, snapshot, count):
        """DECLARED CONSTRUCTED: the pack's Teleportation scrolls cut to ``count``."""
        inventory = [
            replace(item, count=count) if _is_teleport_scroll(item) else item
            for item in snapshot.inventory if not (_is_teleport_scroll(item) and count == 0)]
        return replace(snapshot, inventory=inventory)

    def q33_board(self, scrolls, *, player_hp=None, max_melee=0, cell=(15, 41)):
        snapshot = self.board_of((15, 38), DAGON, cell, player_hp=player_hp, max_melee=max_melee,
                                 summoned=False)
        return self.with_scrolls(snapshot, scrolls)

    def scroll_count(self, snapshot):
        return self.policy._quest_named_item_count(snapshot, "required_scrolls", "teleport")

    def test_the_shipped_plan_names_no_scroll_count(self):
        self.assertEqual(self.profile.abort_conditions["recall_below_teleports"], 0)
        self.assertEqual(self.profile.abort_conditions["hp_ratio"], 0.4)
        data = json.loads(_strip_jsonc((STRATEGIES / "QUEST_33.jsonc").read_text(encoding="utf-8")))
        self.assertIn("Q33内ではテレポートの巻物の不足による帰還は却下する",
                      data["review_plan"]["withdrawal"])

    def test_two_scrolls_and_an_enemy_read_no_recall(self):
        snapshot = self.q33_board(2)
        self.assertEqual(self.scroll_count(snapshot), 2)
        self.assertTrue(snapshot.visible_monsters[0].hostile)
        self.assertIs(once_quest_recall.below_scroll_floor(self.policy, snapshot, self.profile), False)
        self.assertTrue(once_quest_recall.held(self.policy, snapshot))
        self.assertIsNone(quest_plan_base._give_up(self.policy, snapshot, self.profile))
        quest_room_sweep.key(self.policy, snapshot)
        self.assertNotEqual(self.policy.last_reason, RECALL_REASON)
        self.assertIsNone(once_quest_recall.read_key(self.policy, snapshot))
        # The policy's public entry on the next board decides the same.
        key = self.policy.choose_key(self.q33_board(2))
        self.assertNotIn("recall", self.policy.last_reason, key)

    def test_control_the_old_count_of_three_reads_recall(self):
        # Revert-proof: the value shipped before the owner's ruling reads Recall on the same board.
        self.profile.abort_conditions["recall_below_teleports"] = 3
        snapshot = self.q33_board(2)
        self.assertTrue(once_quest_recall.below_scroll_floor(self.policy, snapshot, self.profile))
        self.assertFalse(once_quest_recall.held(self.policy, snapshot))
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual(self.policy.last_reason, RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)
        key = self.policy.choose_key(self.q33_board(2))
        self.assertEqual(self.policy.last_reason, RECALL_REASON, key)

    def test_no_scroll_below_the_line_holds_the_recall(self):
        # Below the HP line with no scroll: neither the line nor the empty pack releases the hold.
        self.without_absorbed_teleportation()
        snapshot = self.q33_board(0, player_hp=self.board.player.max_hp // 4)
        self.assertEqual(self.scroll_count(snapshot), 0)
        self.assertIsNone(self.policy._find_teleport_scroll(snapshot))
        self.assertTrue(once_quest_recall.held(self.policy, snapshot))
        self.assertIsNone(once_quest_recall.read_key(self.policy, snapshot))
        # What the plan then does: below the line with no Teleportation, a potion.
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertNotIn("recall", self.policy.last_reason)
        self.assertTrue(key.startswith("q"), (key, self.policy.last_reason))

    def test_below_the_line_two_scrolls_still_teleport(self):
        # The HP 40% line is unchanged: Teleportation first (the scroll; no absorbed power here).
        self.without_absorbed_teleportation()
        snapshot = self.q33_board(2, player_hp=self.board.player.max_hp // 4)
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("re", quest_plan_base.TELEPORT_REASON))

    def test_instant_death_with_two_scrolls_still_teleports(self):
        self.without_absorbed_teleportation()
        snapshot = self.q33_board(2, player_hp=30, max_melee=300, cell=(15, 39))
        self.assertTrue(threat_tiers.instant_death(self.policy, snapshot).holds)
        key = quest_room_sweep.key(self.policy, snapshot)
        self.assertEqual((key, self.policy.last_reason), ("re", quest_plan_base.TELEPORT_REASON))


# The base class's own tests run in their module; here only this module's.
for _name in [name for name in vars(summon_tests.Quest33SummonAnswerTest) if name.startswith("test_")]:
    setattr(Quest33NoScrollRecallTest, _name, None)


if __name__ == "__main__":
    unittest.main()
