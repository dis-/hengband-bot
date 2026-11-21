"""n1-b life-413: the 49F band kept the Light Crossbow over ★森の狩人ロビンフッドのショート・ボウ.

Owner 2026-11-22 (verbatim), asked whether the launcher comparison should count the melee its
DEX and to-hit modifiers add: 「近接の増え方も入れて全体で比べる」; then
「ちなみに射撃威力も★ロビンフッドの方が高いはずだが、強力射撃を計算に入れてる？」 and
「射撃武器の比較には店で買える並の矢弾を使って。」.

What happened: the optimizer compared the launchers on their own before the whole loadout, each
with the best rounds it could get: the worn ライト・クロスボウ (x3) (1.20turn) (+10,+10) with the
owned 鋼鉄のクロスボウの矢 (3d5) (+2,+5): (9 + 5 + 10) x 3 / 1.2 = 60 a turn; the Short Bow
(x3 with its extra might) (1.00turn) (+15,+17) with plain arrows (1d4): (2.5 + 17) x 3 = 58.5.
The extra might was counted; the ammunition basis was not the same, and the bow's +2 DEX (4 -> 5
blows) never reached that comparison, so the crossbow stayed.

Now every launcher shoots the plain store round of its kind (launcher_damage.
plain_ammo_turn_damage: hit chance and criticals as shoot.cpp) inside the evaluator's
``ranged_dps``, and the loadout is chosen whole: the Short Bow's loadout has more melee and more
shot.

Recorded: the flip test's fixture (tests/fixtures/n1b-413-launcher-flip-1122, the town-arrival
checkpoint of 00:17:35, the 49F band), searched on its board (the checkpoint's memo was searched
by the code of its time).  Fails with the change reverted: the crossbow.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.launcher_damage import launcher_average_damage
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-flip-1122"
ROBIN = "★森の狩人ロビンフッドのショート・ボウ"
CROSSBOW = "ライト・クロスボウ"


class LauncherTotalRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        board = steps[0][1]()
        with contextlib.redirect_stdout(io.StringIO()):
            policy.choose_key(board)
            cls.preparation = policy._prepare_equipment_optimization(
                policy._with_cached_skill_exp(board))
        cls.policy = policy
        cls.evaluator = policy._warrior_evaluator_cache.evaluator

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def launcher(self, prefix):
        return next(item for item in self.policy._equipment_catalog.items
                    if item.item.ammo_tval is not None and item.item.name.startswith(prefix))

    def test_the_49f_band_wears_the_artifact_short_bow(self):
        result = self.preparation.result
        self.assertEqual(result.chosen_decision.band, 49)
        bow = result.best.loadout.item_at("bow")
        self.assertTrue(bow.item.name.startswith(ROBIN), bow.item.name)

    def test_the_short_bow_wins_on_melee_and_on_the_shot(self):
        """The chosen loadout against itself with the crossbow in the bow slot: the +2 DEX
        raises the blows 4 -> 5, and the plain-round shot is higher too."""
        best = self.preparation.result.best.loadout
        crossbow = self.launcher(CROSSBOW)
        swapped = replace(best, slots=tuple(
            (slot, crossbow if slot == "bow" else item) for slot, item in best.slots))
        robin, xbow = self.evaluator(best), self.evaluator(swapped)
        self.assertEqual(robin.melee.hands[0].blows, 5)
        self.assertEqual(xbow.melee.hands[0].blows, 4)
        self.assertGreater(robin.metrics.expected_dps, xbow.metrics.expected_dps)
        self.assertGreater(robin.metrics.ranged_dps, xbow.metrics.ranged_dps)
        # Per shot with the plain rounds: (2.5 + 17) x 3 against (3 + 10) x 3.
        self.assertEqual(launcher_average_damage(self.launcher(ROBIN).item), 58.5)
        self.assertEqual(launcher_average_damage(crossbow.item), 39.0)


if __name__ == "__main__":
    unittest.main()
