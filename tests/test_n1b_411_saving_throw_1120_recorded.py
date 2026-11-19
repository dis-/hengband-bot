"""The loadout evaluator scores each set's own saving throw (n1-b life-411, 2026-11-20).

Owner: 「呪力耐性が生存にどれくらい寄与しているか確認」.  Every candidate was
scored with the board's saving throw (119, ★運命のオーブ worn: resist curse +30
and +3 WIS), so the ★飛行石 set kept the Orb's +30.  calc_saving_throw
(src/player/player-status.cpp) gives that set 88: -30 for the resist curse and
-1 for adj_wis_sav of the lower WIS index.  Its survival falls from 134.3 to
133.4 turns, its ratio from 130.66 to 129.71; the 飛行石 set is still chosen
(the Orb set is under the 95% melee line).

Recorded: the town-arrival checkpoint of the 06:01 visit and journal rows 0-1
(tests/extract_n1b_411_loadout_search_1120_fixture.py); row 1 runs the
optimizer.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import warrior_loadout_evaluator, warrior_optimization
from hengbot.equipment_optimizer import Loadout
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-loadout-search-1120"
HIKOUSEKI = "★飛行石"


class N1b411SavingThrow1120RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def optimize(self):
        """Row 1's optimization; the evaluator it built and the worn loadout."""
        evaluators = []
        real = warrior_loadout_evaluator.CachedWarriorLoadoutEvaluator

        def recording(*args, **kwargs):
            evaluator = real(*args, **kwargs)
            evaluators.append(evaluator)
            return evaluator

        with mock.patch.object(warrior_optimization, "CachedWarriorLoadoutEvaluator", recording):
            board = self.steps[0][1]()
            key = self.policy.choose_key(board)
            self.policy.confirm_key_posted(key)
            chain = self.policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                self.policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            self.policy.choose_key(self.steps[1][1]())
        preparation = self.policy._equipment_optimization_preparation
        return evaluators[-1], preparation

    def test_the_hikouseki_set_loses_the_orbs_saving_throw(self):
        evaluator, preparation = self.optimize()
        worn = preparation.current
        hikouseki = next(owned for owned in self.policy._equipment_catalog.items
                         if owned.item.name.startswith(HIKOUSEKI))
        slots = dict(worn.slots)
        slots["light"] = hikouseki
        hikouseki_set = Loadout(tuple(slots.items()), worn.hand_mode)
        saving = warrior_loadout_evaluator.loadout_defense_inputs
        self.assertEqual(evaluator.inputs.defense.saving_skill, 119)
        self.assertEqual(saving(worn, evaluator.inputs).saving_skill, 119)
        self.assertEqual(saving(hikouseki_set, evaluator.inputs).saving_skill, 88)
        self.assertAlmostEqual(evaluator(worn).metrics.survival_turns, 137.3, places=1)
        # Was 134.3 with the board's 119.
        self.assertAlmostEqual(evaluator(hikouseki_set).metrics.survival_turns, 133.4, places=1)
        best = preparation.result.best.loadout
        self.assertTrue(best.item_at("light").item.name.startswith(HIKOUSEKI))


if __name__ == "__main__":
    unittest.main()
