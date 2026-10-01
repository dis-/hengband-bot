import tests  # noqa: F401 -- isolate runtime paths

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from inspect_dualwield_recorded import FIXTURE, recorded_inputs
from hengbot.equipment_encounters import EncounterTarget
from hengbot.equipment_optimizer import Loadout, optimize_loadout
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.warrior_equipment_evaluator import evaluate_warrior_melee
from hengbot.warrior_loadout_search import enumerate_warrior_loadouts
from hengbot.warrior_optimization import (
    WarriorEvaluatorCache, _append_loadout_report, prepare_warrior_optimization,
)


class RecordedDualWieldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, cls.snapshot, cls.items, calibration = recorded_inputs()
        encounters = []
        for row in data["encounters"]:
            monster = dict(row["knowledge"])
            monster["flags"] = frozenset(monster["flags"])
            monster["abilities"] = frozenset(monster["abilities"])
            monster["blows"] = tuple(MonsterBlow(**b) for b in monster["blows"])
            encounters.append(EncounterTarget(row["race_id"], row["weight"], MonraceKnowledge(**monster)))
        cache = WarriorEvaluatorCache()
        with patch("hengbot.warrior_optimization.normal_encounters", return_value=tuple(encounters)):
            cls.preparation = prepare_warrior_optimization(
                cls.snapshot, cls.items, {t.race_id: t.knowledge for t in encounters},
                depth=None, home_scan_complete=True, calibration=calibration,
                evaluator_cache=cache, timeout_seconds=25,
            )
        cls.evaluator = cache.evaluator
        cls.current = cls.preparation.current
        armor = tuple((s, i) for s, i in cls.current.slots if s not in {"main_hand", "sub_hand"})
        cls.spear = Loadout(tuple(sorted(armor + (("main_hand", cls.current.item_at("main_hand")),))), "two_handed")
        cls.scythe = Loadout(tuple(sorted(armor + (("main_hand", cls.current.item_at("sub_hand")),))), "two_handed")

    def test_recorded_bytes_and_skill_inputs(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                         "5634dda1f03cf7b9fa094b746d00899340ccfcfa6f8b33b9731a66cafa7b0250")
        self.assertEqual(self.snapshot.player.two_weapon_skill, 4556)
        self.assertEqual(self.evaluator.inputs.combat.melee_skill, 175)
        self.assertEqual((self.evaluator.inputs.combat.natural_str,
                          self.evaluator.inputs.combat.natural_dex), (155, 69))

    def test_per_hand_arithmetic_reproduces_game_and_dump(self):
        hands = self.evaluator(self.current).melee.hands
        self.assertEqual([(h.to_hit, h.to_damage, h.blows) for h in hands],
                         [(-57, 11, 5), (-82, 10, 4)])
        self.assertEqual([h.hit_reliability for h in hands], [37, -47])
        self.assertEqual([h.hit_chance_ac100 for h in hands], [0.05, 0.05])
        weapons = (self.current.item_at("main_hand"), self.current.item_at("sub_hand"))
        self.assertEqual([(h.to_hit + w.item.to_h + 175 // 3,
                           h.to_damage + w.item.to_d) for h, w in zip(hands, weapons)],
                         [(12, 21), (-16, 18)])

    def test_corrected_four_loadouts_and_real_optimizer_entry(self):
        result = self.preparation.result
        self.assertEqual(result.timed_out, False)
        self.assertEqual(result.chosen_depth, 20)
        self.assertEqual(result.best.loadout.hand_mode, "two_handed")
        self.assertEqual(result.best.loadout.item_at("main_hand").id,
                         self.current.item_at("main_hand").id)
        self.assertEqual(result.best.loadout.item_at("sub_hand"), None)
        for loadout, expected in ((self.spear, 87.23033856),
                                  (self.scythe, 153.10963194),
                                  (self.current, 15.19430805),
                                  (result.best.loadout, 87.23033856)):
            with self.subTest(mode=loadout.hand_mode, weapon=loadout.item_at("main_hand").id):
                self.assertAlmostEqual(self.evaluator(loadout).metrics.expected_dps, expected, places=7)
        self.assertAlmostEqual(result.chosen_decision.melee_free, 153.10963194, places=7)

    def test_optional_resist_survival_cannot_erase_most_melee_at_fixed_depth(self):
        result = optimize_loadout(
            self.items, lambda loadout: self.evaluator(loadout).metrics,
            depth=20, current_item_ids=self.current.item_ids,
            candidate_loadouts=enumerate_warrior_loadouts(
                self.items, current_item_ids=self.current.item_ids, require_light=True,
            ),
        )
        self.assertEqual(result.best.loadout.hand_mode, "two_handed")
        self.assertEqual(result.best.loadout.item_at("main_hand").id,
                         self.spear.item_at("main_hand").id)

    def test_two_handed_bonus_includes_both_rings(self):
        ring = self.spear.item_at("sub_ring")
        improved = replace(ring, item=replace(ring.item, to_h=2, to_d=3))
        loadout = replace(self.spear, slots=tuple(
            (s, improved if s == "sub_ring" else i) for s, i in self.spear.slots
        ))
        baseline = evaluate_warrior_melee(self.spear, self.evaluator.inputs.combat).hands[0]
        hand = evaluate_warrior_melee(loadout, self.evaluator.inputs.combat).hands[0]
        self.assertEqual((hand.to_hit - baseline.to_hit, hand.to_damage - baseline.to_damage), (2, 3))

    def test_search_report_keeps_actual_combat_inputs_and_hand_terms(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.jsonl"
            _append_loadout_report(path, 127, self.preparation.result,
                                   self.evaluator, self.evaluator.inputs.defense)
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["combat_inputs"]["two_weapon_skill"], 4556)
        self.assertEqual(report["combat_inputs"]["melee_skill"], 175)
        self.assertEqual(report["candidates"][0]["melee_hands"][0]["to_hit"], 28)
        self.assertEqual(report["candidates"][0]["melee_hands"][0]["hit_reliability"], 292)


if __name__ == "__main__":
    unittest.main()
