"""A vampiric weapon's drain counts in survival (n1-b life-411, 2026-11-20).

Owner: 「吸血も評価に入れて直す」 (★首切りソード『スレイヤー』 |吸).  A hit on a
living monster (not DEMON, UNDEAD or NONLIVING) above 5 damage heals
2d(damage/6), one hand at most 50 HP a player turn
(src/player-attack/blood-sucking-processor.cpp, player-attack.cpp
MAX_VAMPIRIC_DRAIN).  On n1-b's 95F pool 72.3% is living and the Slayer's
seven blows reach the cap: 36 HP a turn, more than the mix-averaged incoming
damage, so the drain restores everything one engagement takes - the kill
turns (1.38) are added to the survival turns (92.2 -> 93.6).  The ★飛行石 set
with Icing Death is still chosen.

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


class N1b411Vampiric1120RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def optimize(self):
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
        return evaluators[-1], self.policy._equipment_optimization_preparation

    def test_the_slayers_drain_adds_one_engagement_of_survival(self):
        evaluator, preparation = self.optimize()
        worn = preparation.current
        slayer = next(owned for owned in self.policy._equipment_catalog.items
                      if owned.item.name.startswith(SLAYER))
        slots = dict(worn.slots)
        slots["main_hand"] = slayer
        slayer_set = Loadout(tuple(slots.items()), "two_handed")
        self.assertAlmostEqual(evaluator._living_share, 0.723, places=3)
        result = evaluator(slayer_set)
        with mock.patch.object(warrior_loadout_evaluator, "drains", lambda loadout: False):
            dry = warrior_loadout_evaluator.CachedWarriorLoadoutEvaluator(
                evaluator.inputs, evaluator.encounters, evaluator.offense_encounters)(slayer_set)
        self.assertAlmostEqual(dry.metrics.survival_turns, 92.2, places=1)
        self.assertAlmostEqual(result.metrics.survival_turns, 93.6, places=1)
        self.assertAlmostEqual(result.metrics.survival_turns - dry.metrics.survival_turns,
                               result.melee.expected_kill_turns, places=6)
        # Icing Death drains nothing.
        self.assertFalse(warrior_loadout_evaluator.drains(worn))
        best = preparation.result.best.loadout
        self.assertTrue(best.item_at("light").item.name.startswith(HIKOUSEKI))


if __name__ == "__main__":
    unittest.main()
