"""2026-10-31 n1-c life-072: Q14 refused for want of Potions of Healing.

QUEST_14 (Warg problem) asks for two heal potions.  Its readiness counted only
Potions of Healing, which no store stocks regularly
(store/articles-on-sale.cpp), so the Lv18 Magic-Eater carrying ten Potions
of Cure Critical Wounds never requested the quest: decision 10375 recorded
fixedquest_readiness quest 14 ``strategy-force`` failed ["heal_potions"]
measured 1 required 2, then read Word of Recall to another dungeon; each
town visit also sent it to the Temple and the Black market for Healing.
Owner 2026-10-31: 「致命傷の治癒でよい」 -- QUEST_14 names Cure Critical
Wounds as its ``heal_potion_kind``.

The recorded town board goes through the public ``choose_key`` and the
posted key through the production executor.  Fixture:
tests/extract_q14_heal_ccw_fixture.py.

DECLARED RECONSTRUCTED: a new process on the recorded board, with the
repository's quest, monster, strategy and town-map data the CLI loads, the
recorded skill and Home knowledge rows, and the staff-sequence record of
the 23:23 checkpoint (stage 3, every stage absorbed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.model import (
    SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, TVAL_POTION, _parse_items, parse_snapshot,
)
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "q14-heal-ccw-20261031.json.gz"
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def town_maps():
    maps = {0: parse_town_map(find_outpost_map(Path(__file__)))}
    for town_index in range(2, 6):
        path = find_town_map(town_index, Path(__file__))
        if path is not None:
            maps[town_index - 1] = parse_town_map(path)
    return maps


class Q14HealCureCriticalRecordedTest(executor_harness.ProductionHarness):
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
        # DECLARED CONSTRUCTED: the carried Stone to Mud wand as already
        # absorbed, so its own Tower trip (another owner) does not take the
        # board (test_me_nokey_1031_recorded does the same).
        record.absorbed["wand:6"] = 12
        policy.consume_skill_knowledge(dict(self.case["skill"], turn=raw["turn"]))
        policy.consume_home_knowledge(
            _parse_items(self.case["home"]["knowledge"]["items"], protocol=3))
        return policy, raw

    def test_recorded_decision_refused_q14_on_heal_potions(self):
        decision = self.case["decision"]
        self.assertEqual((decision["decision_sequence"], decision["reason"]),
                         (10375, "town:recall-to-alt-dungeon"))
        readiness = decision["fixedquest_readiness"]
        self.assertEqual((readiness["quest_id"], readiness["reason"]), (14, "strategy-force"))
        self.assertEqual(readiness["strategy_force"]["failed"], ["heal_potions"])
        self.assertEqual(readiness["strategy_force"]["heal_potions"],
                         {"measured": 1, "required": 2})
        potions = {item["sval"]: item["count"] for item in self.case["board"]["inventory"]
                   if item["tval"] == TVAL_POTION}
        self.assertEqual((potions[SV_POTION_CURE_CRITICAL], potions[SV_POTION_HEALING]), (10, 1))

    def test_only_quest_14_counts_cure_critical(self):
        from hengbot.quest_strategies import heal_potion_sval  # absent before the fix
        self.assertEqual(heal_potion_sval(self.strategies[14].required_force),
                         SV_POTION_CURE_CRITICAL)
        for quest_id in (1, 2, 22, 31, 34):
            with self.subTest(quest=quest_id):
                self.assertEqual(heal_potion_sval(self.strategies[quest_id].required_force),
                                 SV_POTION_HEALING)

    def test_recorded_board_requests_q14_with_cure_critical_wounds(self):
        policy, raw = self.recorded_policy()
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        readiness = policy._fixed_quest_readiness
        self.assertEqual(readiness["quest_id"], 14)
        self.assertEqual(readiness["strategy_force"]["heal_potions"],
                         {"measured": 10, "required": 2})
        self.assertEqual(readiness["strategy_force"]["failed"], [])
        self.assertTrue(readiness["verdict"])
        # Recorded: the Black market ('$') for a Potion of Healing.
        self.assertEqual(policy.last_reason, "fixedquest:request:approach")
        self.assertIn(key, DIRECTIONS)
        # DECLARED CONSTRUCTED: the engine's reply to the walk step.
        following = copy.deepcopy(raw)
        dy, dx = DIRECTIONS[key]
        following["player"]["y"] += dy
        following["player"]["x"] += dx
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, raw, key, following)


if __name__ == "__main__":
    import unittest
    unittest.main()
