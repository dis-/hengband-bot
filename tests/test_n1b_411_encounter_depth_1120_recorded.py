"""The loadout is scored against the destination's monsters (n1-b life-411, 2026-11-20).

Owner: 「深い階層では邪以外のスレイ対象は少なくなる。本当にスレイヤーの方が威力が低いか？」
-> 「吸血も評価に入れて直す」.  The unconstrained search scored against every
race up to the deepest known level (127), weighted by rarity alone, and a
64-race sample of the heaviest races held 26% dragons, so ★シミター『アイシング
デス』 (dragon x5, cold brand) out-scored ★首切りソード『スレイヤー』 535.2 to
521.8 melee per action.  Now the destination is the recall landing within the
95F Angband cap, the races are weighted by get_mon_num's highest-of-1-3 draw,
and the melee side reads the whole ordinary pool (12.5% dragons): the
Slayer scores 521.2, Icing Death 516.9.  The ★飛行石 set is still chosen:
the Slayer needs Free Action from another slot.

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
SLAYER = "★首切りソード『スレイヤー』"
HIKOUSEKI = "★飛行石"


class N1b411EncounterDepth1120RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def optimize(self):
        evaluators, depths = [], []
        real = warrior_loadout_evaluator.CachedWarriorLoadoutEvaluator
        real_normal = warrior_optimization.normal_encounters

        def recording(*args, **kwargs):
            evaluator = real(*args, **kwargs)
            evaluators.append(evaluator)
            return evaluator

        def normal(knowledge, depth, **kwargs):
            depths.append(depth)
            return real_normal(knowledge, depth, **kwargs)

        with mock.patch.object(warrior_optimization, "CachedWarriorLoadoutEvaluator", recording), \
                mock.patch.object(warrior_optimization, "normal_encounters", normal):
            board = self.steps[0][1]()
            key = self.policy.choose_key(board)
            self.policy.confirm_key_posted(key)
            chain = self.policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                self.policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            self.policy.choose_key(self.steps[1][1]())
        return evaluators[-1], depths[-1], self.policy._equipment_optimization_preparation

    def test_the_destination_population_ranks_the_slayer_above_icing_death(self):
        evaluator, depth, preparation = self.optimize()
        self.assertEqual(depth, 95)  # was 127, the deepest known race
        worn = preparation.current
        slayer = next(owned for owned in self.policy._equipment_catalog.items
                      if owned.item.name.startswith(SLAYER))
        slots = dict(worn.slots)
        slots["main_hand"] = slayer
        slayer_set = Loadout(tuple(slots.items()), "two_handed")
        dragons = sum(e.weight for e in evaluator.offense_encounters
                      if "DRAGON" in e.knowledge.flags)
        self.assertAlmostEqual(dragons, 0.125, places=3)
        self.assertAlmostEqual(evaluator(worn).metrics.expected_dps, 516.9, places=1)
        self.assertAlmostEqual(evaluator(slayer_set).metrics.expected_dps, 521.2, places=1)
        best = preparation.result.best.loadout
        self.assertTrue(best.item_at("light").item.name.startswith(HIKOUSEKI))
        self.assertFalse(best.item_at("main_hand").item.name.startswith(SLAYER))


if __name__ == "__main__":
    unittest.main()
