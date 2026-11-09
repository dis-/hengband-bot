"""n1-b life-283: a taken Q34 keeps its twenty torches.

Recorded (2026-10-31, build bot-404e73286, again on bot-13e2f14d0): the new
Lv1 zombie warrior bought fifteen torches for Q34's twenty
(QUEST_34 throwing_items.lit_torch; owner 2026-10-30 「松明20本はキープして」)
and accepted the quest at turn 75210.  From then on the town's carry owner
(_carry_procurement_strategy -> _quest_strategy_for_errand_or_floor) chose
Q1 -- the generic (level, id) order ties the two level-five quests -- whose
carry is five torches, so the fifteen became surplus and were shelved at
Home at turn 75416.  Q34's entry readiness still asked for twenty, the shop
plan wanted none, and the town waited for a useless restock until
loop-detected and owner-retired-burst, spending the gold on re-bought
torches that were shelved again.  The test drives the recorded board of turn
75692 (five torches carried, gold 55, the General Store shelf observed)
until the bot steps onto Q34's entrance (its quest-entry question answered).

Harness, declarations and engine replies: tests/test_unid_deposit_recorded.py
(DECLARED RECONSTRUCTED boundary, DECLARED CONSTRUCTED replies).  Fixture:
tests/extract_q34_taken_torches_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from pathlib import Path

from hengbot.cli import _movement_destination as movement_destination
from hengbot.model import parse_snapshot
from hengbot.policy_constants import QUEST_STATUS_TAKEN, STORE_HOME
import tests.support.recorded as executor_harness
import tests.test_unid_deposit_recorded as recorded


class Q34TakenTorchesRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    fixture = Path(__file__).with_name("fixtures") / "q34-taken-torches-20261031.json.gz"

    entered = False

    def post(self, policy, raw, key, following):
        """DECLARED CONSTRUCTED: cmd-move.cpp asks before a quest entrance step."""
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        if key in recorded.DIRECTIONS and raw.get("store") is None:
            target = board.grid_at(movement_destination(board.player.position, key))
            if target is not None and target.has_quest_enter:
                screens = [executor_harness.prompt_screen("クエストに入りますか？[y/n]")]
                self.execute(policy, raw, key, following, screens, [raw], [key, "y"])
                self.entered = True
                return None
        return super().post(policy, raw, key, following)

    def torches(self, raw):
        return sum(item["count"] for item in raw["inventory"] if item["tval"] == 39)

    def test_recorded_stop(self):
        policy, _ = self.boundary()
        accepted = parse_snapshot(copy.deepcopy(self.case["accepted"]), policy._monrace_knowledge)
        self.assertEqual(accepted.quests[34].status, QUEST_STATUS_TAKEN)
        self.assertEqual(self.torches(self.case["accepted"]), 20)
        # The town's carry owner works for the taken quest, at its own count.
        strategy = policy._carry_procurement_strategy(accepted)
        self.assertEqual(strategy.quest_id, 34)
        self.assertEqual(strategy.required_force["throwing_items"]["lit_torch"], 20)
        # Turn 75692: five carried, the fifteen on the recorded Home page.
        self.assertEqual(self.torches(self.case["board"]), 5)
        home = next(row["store"] for row in reversed(self.case["observations"])
                    if row["type"] == "store" and row["store"]["store_type"] == STORE_HOME)
        self.assertEqual(sum(item["count"] for item in home["items"] if item["tval"] == 39), 15)

    def test_taken_quest_restores_its_torches_before_the_entrance(self):
        policy, raw = self.boundary()
        raw, reasons = self.drive(policy, raw, limit=30,
                                  done=lambda reason, key: self.entered)
        self.assertNotIn("deposit", [kind for kind, _ in self.events], reasons)
        self.assertEqual(self.torches(raw), 20, (self.events, reasons))

    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


if __name__ == "__main__":
    import unittest
    unittest.main()
