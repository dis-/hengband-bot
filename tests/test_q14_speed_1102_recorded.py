"""2026-11-02 n1-c life-102: Q14 refused for want of a Potion of Speed.

QUEST_14 (Warg problem) asked for one Potion of Speed.  No store but the
Black market sells it (store/articles-on-sale.cpp has no Potion of Speed),
so the Lv8 Magic-Eater with ten Potions of Cure Critical Wounds waited on
the Black market's random shelf: decision 5697 (turn 860272) recorded
fixedquest_readiness quest 14 ``strategy-force`` failed ["speed_potions"]
measured 0 required 1, and the same refusal held from 03:59:35 until the
Black market stocked two at 04:12:48.  Owner 2026-11-02: 「Q14の受注要件から
スピードの薬を外す」 -- QUEST_14's required_force.speed_potions is 0; a
carried potion is still quaffed per its consumable_plan.

The recorded town board goes through the public ``choose_key`` and the
posted key through the production executor.  Fixture:
tests/extract_q14_speed_1102_fixture.py.

DECLARED RECONSTRUCTED: a new process on the recorded board, with the
repository's quest, monster, strategy and town-map data the CLI loads, the
recorded skill and Home knowledge rows, and the staff-sequence record of
the 03:47 incident checkpoint (stage 1, nothing absorbed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_capability, me_staff_sequence
from hengbot.model import SV_POTION_SPEED, TVAL_POTION, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_q14_heal_ccw_recorded import ROOT, town_maps
import tests.support.recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "q14-speed-1102.json.gz"


class Q14SpeedPotionRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.maps = town_maps()
        cls.races = load_monrace_knowledge(find_monrace_definitions(ROOT, None))
        cls.quests = load_quest_knowledge(find_quest_definitions(ROOT))
        cls.strategies = load_quest_strategies(ROOT / "strategy" / "quests")

    def recorded_policy(self):
        raw = copy.deepcopy(self.case["board"])
        policy = ConservativePolicy(
            town_map=self.maps[0], town_maps=self.maps,
            monrace_knowledge=self.races, quest_knowledge=self.quests,
            quest_strategies=self.strategies,
        )
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        recorded = self.case["staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.stage = recorded["stage"]
        record.powers_read = recorded["powers_read"]
        record.absorbed = {int(sval): count for sval, count in recorded["absorbed"].items()}
        policy.consume_skill_knowledge(self.case["skill"])
        policy.consume_home_knowledge(
            _parse_items(self.case["home"]["knowledge"]["items"], protocol=3))
        return policy, raw

    def test_recorded_decision_refused_q14_on_speed_potions(self):
        decision = self.case["decision"]
        self.assertEqual((decision["decision_sequence"], decision["turn"]), (5697, 860272))
        readiness = decision["fixedquest_readiness"]
        self.assertEqual((readiness["quest_id"], readiness["reason"]), (14, "strategy-force"))
        self.assertEqual(readiness["strategy_force"]["failed"], ["speed_potions"])
        self.assertEqual(readiness["strategy_force"]["speed_potions"],
                         {"measured": 0, "required": 1})
        self.assertFalse(any(item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_SPEED
                             for item in self.case["board"]["inventory"]))

    def test_only_quest_14_drops_the_speed_potion(self):
        self.assertEqual(self.strategies[14].required_force["speed_potions"], 0)
        self.assertEqual(self.strategies[14].consumable_plan["speed_potion"], "conditional")
        for quest_id, count in ((1, 1), (2, 2), (22, 1), (31, 1)):
            with self.subTest(quest=quest_id):
                self.assertEqual(self.strategies[quest_id].required_force["speed_potions"], count)

    def test_recorded_board_passes_q14_strategy_force_without_speed(self):
        policy, raw = self.recorded_policy()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        readiness = policy._fixed_quest_readiness
        self.assertEqual(readiness["quest_id"], 14)
        force = readiness["strategy_force"]
        self.assertEqual(force["speed_potions"], {"measured": 0, "required": 0})
        self.assertEqual(force["failed"], [])
        # Acceptance, entry and the purchase rung read the same count.
        self.assertEqual(me_capability.force_count(
            policy, board, self.strategies[14].required_force, "speed_potions"), 0)
        self.assertNotIn("quest:speed", {
            category for category, _kind, _carried, required
            in policy._strategy_potion_needs(board, self.strategies[14].required_force)
            if required > 0})
        # The next gate: four wargs adjacent for three turns (188) against
        # max HP 129 x 1.6 -- owner 2026-11-02 「Lv.8で受けられる程度に受注要件を
        # 下げる」 (tests.test_q14_lv8_1102_recorded).  This Lv8 board passes;
        # its staff sequence (stage 1) still owns the town step first.
        self.assertEqual((readiness["worst_adjacent"], readiness["max_damage_ratio"]), (188, 1.6))
        self.assertEqual(readiness["reason"], "ready")
        self.assertTrue(readiness["verdict"])
        self.assertEqual(policy.last_reason, "shop:travel")
        # DECLARED CONSTRUCTED: the engine's reply to the travel macro.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, raw, key, following)


if __name__ == "__main__":
    import unittest
    unittest.main()
