"""#47: Q1's kit lowered to what the gold buys (owner 2026-10-31 「Q1の要求値を下げ、受注可能にする」).

The recorded n1-c life-058 opening boards (084721, Lv7 Magic-Eater, ring rows
207-222, tests/fixtures/me-nokey-20261031.json.gz) are driven through the
public ``choose_key`` as in test_me_nokey_1031_recorded.Q1TorchForceTest; the
key is sent through the production executor.

DECLARED CONSTRUCTED: the gold of every board is 2, below the one missing
torch (19 carried, 20 required): the recorded stop's shape (the full kit
costs more than the gold; there 7,450 against 223) with the current torch
force.  Unfixed, the route stops with stop:unaffordable-quest-reserve; with
the strategy's carry floor (QUEST_1 carry_floor_by_class 16: 9 torches) it
takes Q1 with the 19 torches it has.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot.model import parse_snapshot
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_nokey_1031_recorded as nokey

GOLD = 2


class Q1AffordableKitTest(nokey.PostedKey):
    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()

    def drive(self, gold):
        opening = copy.deepcopy(nokey.CASE["opening"])
        boards = opening["boards"]
        for raw in boards:
            if "player" in raw:
                raw["player"]["gold"] = gold
        policy, _ = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=nokey.CASE["monraces"], snapshot=boards[0],
            knowledge=[opening["skill"], opening["home"]], state={"modes_and_latches": {}}))
        for raw in boards:
            key = nokey.decide(policy, raw, opening["skill"])
            if not key or policy.last_reason.startswith("fixedquest:request"):
                # The recorded run went on to the General store; past the
                # first step to the quest giver the ring no longer follows.
                break
        return policy, raw, key

    def test_unaffordable_torch_lowers_the_kit_and_takes_q1(self):
        policy, raw, key = self.drive(GOLD)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None), policy.last_reason)
        self.assertEqual(policy.last_reason, "fixedquest:request:approach", key)
        self.assertEqual(policy._quest_carry_lowered,
                         (1, {"lit_torch": 19, "heal_potions": 0, "speed_potions": 0}))
        self.assertEqual([row[1:3] for row in policy._opening_q1_requirements(board)],
                         [(19, 19), (0, 0), (0, 0)])
        self.assertEqual(policy._opening_q1_plan(board)[0], "quest")
        profile = policy.approved_quest_strategy(1)
        self.assertTrue(policy._approved_strategy_force_ready(board, profile))
        force = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual(force["lit_torch"], {"measured": 19, "required": 19})
        self.post(policy, raw, key)

    def test_full_kit_is_kept_when_the_gold_buys_it(self):
        # The recorded 223 gold buys the torch: nothing is lowered.
        policy, raw, _key = self.drive(raw_gold := 223)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(board.player.gold, raw_gold)
        self.assertIsNone(policy._quest_carry_lowered)
        self.assertEqual([row[1:3] for row in policy._opening_q1_requirements(board)],
                         [(20, 19), (0, 0), (0, 0)])

    def test_below_the_floor_still_stops_by_name(self):
        # DECLARED CONSTRUCTED: 8 torches carried (under the floor of 9) and
        # 2 gold: the floor itself is unaffordable, the named stop stays.
        policy, raw, key = self.drive(GOLD)
        raw = copy.deepcopy(raw)
        torches = [item for item in raw["inventory"] if (item.get("tval"), item.get("sval")) == (39, 0)]
        self.assertEqual([item["count"] for item in torches], [6, 12, 1])
        torches[1]["count"] = 2  # 6 + 2: the 'g' torch is taken out
        raw["inventory"].remove(torches[2])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(policy._opening_q1_plan(board)[0], "stop:unaffordable-quest-reserve")


if __name__ == "__main__":
    unittest.main()
