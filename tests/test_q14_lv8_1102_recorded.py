"""2026-11-02 n1-c life-102: Q14 refused by the three-turn-threat gate.

After the Potion of Speed left QUEST_14's acceptance (5cbca1214), the
three-turn-threat gate still refused the quest on every board of the life:
four Wargs adjacent at maximum dice for three turns against half of max HP.
Decision 1783 (04:12:50, turn 910377) recorded fixedquest_readiness
quest 14 ``three-turn-threat`` worst_adjacent 116 (hasted) >= 146 x 0.50 and
read Word of Recall to the dungeon instead; the Lv8 board of 03:59 (max HP
129, unhasted) projected 188.  Owner 2026-11-02: 「Lv.8で受けられる程度に
受注要件を下げる。実際にはそこまで脅威になることはない。」 -- QUEST_14's
engagement_plan.max_damage_ratio is 1.6, so a character at the file's Lv8
floor (min_hp 120, reference_ac 20: 184 < 192) is accepted.

The recorded town board goes through the public ``choose_key`` and the
posted key through the production executor.  Fixture:
tests/extract_q14_lv8_1102_fixture.py.

DECLARED RECONSTRUCTED: a new process on the recorded board, with the
repository's quest, monster, strategy and town-map data the CLI loads, the
recorded skill and Home knowledge rows, and the staff-sequence record of
the 04:27 incident checkpoint (every sequence staff absorbed at 04:09).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_q14_heal_ccw_recorded import ROOT, town_maps
import tests.support.recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "q14-lv8-1102.json.gz"


class Q14Lv8ThreatRecordedTest(executor_harness.ProductionHarness):
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
        record.absorbed = dict(recorded["absorbed"])
        policy.consume_skill_knowledge(self.case["skill"])
        policy.consume_home_knowledge(
            _parse_items(self.case["home"]["knowledge"]["items"], protocol=3))
        return policy, raw

    def test_recorded_decision_refused_q14_on_three_turn_threat(self):
        decision = self.case["decision"]
        self.assertEqual((decision["decision_sequence"], decision["turn"], decision["reason"]),
                         (1783, 910377, "town:recall-to-angband"))
        readiness = decision["fixedquest_readiness"]
        self.assertEqual((readiness["quest_id"], readiness["reason"]), (14, "three-turn-threat"))
        self.assertEqual((readiness["worst_adjacent"], readiness["hp_healing_budget"],
                          readiness["max_damage_ratio"]), (116, 146, 0.5))
        player = self.case["board"]["player"]
        self.assertEqual((player["level"], player["max_hp"]), (11, 146))

    def test_recorded_board_requests_q14_under_the_lv8_budget(self):
        policy, raw = self.recorded_policy()
        self.assertTrue(me_staff_sequence.complete(policy))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        readiness = policy._fixed_quest_readiness
        self.assertEqual(readiness["quest_id"], 14)
        self.assertEqual(readiness["strategy_force"]["failed"], [])
        self.assertEqual((readiness["worst_adjacent"], readiness["max_damage_ratio"]), (116, 1.6))
        self.assertEqual(readiness["simultaneous_melee"], 4)
        self.assertEqual(readiness["reason"], "ready")
        self.assertTrue(readiness["verdict"])
        self.assertEqual(policy.last_reason, "fixedquest:request:approach")
        # DECLARED CONSTRUCTED: the engine's reply to the step toward the
        # quest giver's building.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, raw, key, following)

    def test_only_quest_14_raises_the_budget(self):
        self.assertEqual(self.strategies[14].engagement_plan["max_damage_ratio"], 1.6)
        self.assertEqual(self.strategies[14].engagement_plan["max_simultaneous_melee"], 4)
        self.assertEqual(self.strategies[14].abort_conditions["hp_ratio"], 0.30)
        self.assertEqual(self.strategies[14].consumable_plan["heal_threshold_ratio"], 0.55)
        self.assertEqual(self.strategies[14].required_force["min_hp"], 120)
        self.assertEqual(self.strategies[31].engagement_plan["max_damage_ratio"], 1.0)
        for quest_id in (1, 2, 22):
            with self.subTest(quest=quest_id):
                self.assertNotIn("max_damage_ratio", self.strategies[quest_id].engagement_plan)


if __name__ == "__main__":
    import unittest
    unittest.main()
