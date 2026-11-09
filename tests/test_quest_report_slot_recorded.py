"""Owner 2026-11-02: no quest report while the pack has no free slot.

「空きが1つもないときはクエストの報告をしない」.  Reporting a quest of
FIXED_QUEST_REWARD_POSITIONS puts its reward on a town cell
(market/building-quest.cpp castle_quest sets REWARDED; floor/wild.cpp
wilderness_gen places it and sets FINISHED), and the reward exists only on
that town level.  With 23/23 slots the pickup cannot happen, so the report
waits for the room-making town owners instead.

The board is the recorded n1-c life-098 Telmora claim board of
tests/test_q2_reward_lamp_recorded.py (decision 2520, 21/23 slots, Q2
COMPLETED, one step from the castle).  The pack contents are DECLARED
CONSTRUCTED from it: copies of the recorded unidentified 硬革帽子 / 革グローブ
fill it to 23/23 (no free slot) or 22/23 (one free slot).  Every decision goes
through the public chooser and is posted through the production executor.
"""
import tests  # noqa: F401

import copy

from hengbot.model import Position, parse_snapshot
from hengbot.town_terminal import rung_terminal, terminal_admission
import tests.support.recorded as executor_harness
import tests.test_q2_reward_lamp_recorded as lamp

GENERAL_STORE_ENTRANCE = Position(32, 56)


class QuestReportSlotRecordedTest(executor_harness.ProductionHarness):
    setUpClass = classmethod(lamp.Q2RewardLampRecordedTest.setUpClass.__func__)
    policy = lamp.Q2RewardLampRecordedTest.policy
    post = lamp.Q2RewardLampRecordedTest.post
    decide = lamp.Q2RewardLampRecordedTest.decide

    def claim_board(self, free_slots):
        """DECLARED CONSTRUCTED: the recorded claim board with ``free_slots`` left."""
        raw = copy.deepcopy(self.case["claim_board"])
        inventory = raw["inventory"]
        self.assertEqual(len(inventory), 21)
        copies = [item for item in inventory if item["slot"] in {"p", "q"}]
        for slot, item in zip("vw", copies[:2 - free_slots]):
            inventory.append(dict(copy.deepcopy(item), slot=slot))
        self.assertEqual(23 - len(inventory), free_slots)
        return raw

    def test_full_pack_does_not_report_and_makes_room(self):
        policy = self.policy()
        raw = self.claim_board(free_slots=0)
        key = self.decide(policy, raw)
        self.assertNotIn("q", key)
        self.assertEqual(policy.last_reason, "shop:travel")
        # The town errand walks to the General Store to sell first.
        self.assertEqual(policy._shopping_approach_goal, GENERAL_STORE_ENTRANCE)
        plan = policy._town_errand_plan
        self.assertIn("shop-sell", plan.requester_families[plan.stops[plan.index]])
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        terminal = rung_terminal(policy, "_fixed_quest_key#2", board)
        self.assertEqual((terminal.terminal_id, terminal.args), ("quest-claim", (2,)))
        self.assertEqual(terminal_admission(policy, board, terminal).codes,
                         ("free_pack_slots_ready",))
        self.assertIsNone(policy._fixed_quest_reward_pending)
        # DECLARED CONSTRUCTED reply: native travel stopped one step on.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["player"]["y"] += 1
        self.post(policy, raw, key, following)

    def test_one_free_slot_reports(self):
        policy = self.policy()
        raw = self.claim_board(free_slots=1)
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), (lamp.CLAIM_KEY, "fixedquest:claim"))
        self.assertEqual(policy._fixed_quest_reward_pending, 2)
        reported = copy.deepcopy(self.case["reported_board"])
        reported["inventory"] = copy.deepcopy(raw["inventory"])
        self.post(policy, raw, key, reported)


if __name__ == "__main__":
    import unittest
    unittest.main()
