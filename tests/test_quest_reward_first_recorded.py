"""Owner 2026-11-02: make room, report and collect the town-map reward first.

「空きを作って報告し、報酬を回収するまでを優先したい」.  The reward of a quest
of FIXED_QUEST_REWARD_POSITIONS lies on its town level only (floor/wild.cpp
wilderness_gen places it, then sets FINISHED), so until it is in the pack
the town-leaving owners wait (town_quest_reward.holds_town) and the
room-making owners take the board.

The board is the recorded n1-c life-098 Telmora reported board of
tests/test_q2_reward_lamp_recorded.py (Q2 status 4, the Feanorian lamp on
(22,42)); there the Magic-Eater staff sequence took the inn to the Outpost
(me-staff:return-outpost) and the lamp was lost.  DECLARED CONSTRUCTED: the
pack is filled to 23/23 with copies of the recorded unidentified 硬革帽子 /
革グローブ (tests/test_quest_report_slot_recorded.py), the board after the
room-making sale has the Slow Monster wand sold at the Magic shop, and the
replies to the posted keys are constructed.  Every decision goes through the
public chooser and is posted through the production executor.
"""
import tests  # noqa: F401

import copy

from hengbot import me_staff_sequence
from hengbot.model import parse_snapshot
from hengbot.town_terminal import rung_terminal, terminal_admission
import tests.test_q2_reward_lamp_recorded as lamp
import tests.test_quest_report_slot_recorded as slot

MAGIC_SHOP_ENTRANCE = (37, 42)  # 02_Telmora store 5
QUEST_REWARD_FIRST = "quest-reward-first"  # town_terminal's refusal code
SOLD_SLOT = "k"  # スロウ・モンスターの魔法棒: the organization sale's pick


class QuestRewardFirstRecordedTest(slot.QuestReportSlotRecordedTest):
    def full_reported_board(self):
        """DECLARED CONSTRUCTED: the recorded reported board with 23/23 slots."""
        raw = copy.deepcopy(self.case["reported_board"])
        raw["inventory"] = self.claim_board(free_slots=0)["inventory"]
        return raw

    def inn_travel_admission(self, policy, raw, producer):
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        policy._terminal_town_travel = (producer, 0)
        try:
            terminal = rung_terminal(policy, "town-teleport", board)
            return terminal, (None if terminal is None
                              else terminal_admission(policy, board, terminal))
        finally:
            policy._terminal_town_travel = None

    def test_room_report_and_reward_before_leaving_telmora(self):
        raw = self.full_reported_board()
        # The staff sequence wants to leave: its inn leg to the Outpost.
        probe = self.policy()
        me_staff_sequence.town_key(probe, parse_snapshot(copy.deepcopy(raw), self.monrace), [])
        self.assertEqual(probe.last_reason, "me-staff:return-to-shop")

        policy = self.policy()
        key = self.decide(policy, raw)
        # Not the inn: the town errand walks toward its shops to make room.
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(policy._fixed_quest_reward_pending, 2)
        # The staff sequence's inn leg is refused while the reward waits.
        terminal, admission = self.inn_travel_admission(policy, raw, "me-staff")
        self.assertEqual(terminal.terminal_id, "inn-travel")
        self.assertEqual(admission.codes, (QUEST_REWARD_FIRST,))
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)

        # DECLARED CONSTRUCTED: the sale at the Magic shop freed one slot.
        raw = following
        raw["inventory"] = [item for item in raw["inventory"] if item["slot"] != SOLD_SLOT]
        raw["player"]["y"], raw["player"]["x"] = MAGIC_SHOP_ENTRANCE
        reasons = []
        for _ in range(30):
            key = self.decide(policy, raw)
            reasons.append((key, policy.last_reason))
            following = self.reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
            if key == "g":
                break
        self.assertEqual(reasons[-1], ("g", "fixedquest:reward-pickup"), reasons)
        self.assertTrue(all(reason.startswith("fixedquest:reward") for _, reason in reasons), reasons)
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        self.assertIn(lamp.LAMP_NAME, [item.name for item in board.inventory])

        # Only now is the town left: the hold is gone and the staff
        # sequence takes its inn leg (the lamp filled the last slot).
        key = self.decide(policy, raw)
        self.assertIsNone(policy._fixed_quest_reward_pending, (key, policy.last_reason))
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")
        self.assertEqual(self.inn_travel_admission(policy, raw, "me-staff"), (None, None))

    reply = staticmethod(lamp.Q2RewardLampRecordedTest.reply)

    # The inherited report-slot cases run in their own module.
    test_full_pack_does_not_report_and_makes_room = None
    test_one_free_slot_reports = None


if __name__ == "__main__":
    import unittest
    unittest.main()
