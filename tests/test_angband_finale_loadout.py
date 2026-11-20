"""The dedicated 99F/100F loadout order (equipment_optimizer ``finale``, owner 2026-11-20).

Owner, verbatim: 「装備は加速耐性テレパシーー知力耐久力を優先。ACや近接攻撃力は求めない。」 and
「呪力耐性も要求する。これはオベロンの血の呪い、サーペントの破滅の手が致死的であるためである。」
``finale_rank``: resist curse, then the permanent speed, the resisted elements, telepathy, INT,
CON; AC and melee only between loadouts it holds equal; the band descent's half-melee limit is
not asked.

DECLARED CONSTRUCTED: the catalog items (one light, rings of the flags each test names) and the
evaluator's metrics (the combat margin standing in for AC and melee).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot.equipment_optimizer import (
    SLOT_MAIN_RING, EvaluatedLoadout, Loadout, LoadoutMetrics, OwnedEquipment, finale_rank,
    optimize_loadout, required_abilities,
)
from hengbot.model import InventoryItem

TR_INT, TR_CON, TR_TELEPATHY, TR_RES_CURSE = 1, 4, 79, 148
TR_RES_FIRE, TR_RES_COLD, TR_IM_FIRE, TR_RES_NETHER = 50, 51, 42, 60


def gear(item_id, tval, flags=(), pval=0):
    item = InventoryItem(slot=item_id, name=item_id, count=1, tval=tval, sval=1, aware=True,
                         known=True, fully_known=True, is_equipment=True, pval=pval,
                         known_flags=frozenset(flags))
    return OwnedEquipment(item_id, item, "home")


def metrics(margin, *, speed=140, dps=None):
    return LoadoutMetrics(expected_dps=margin if dps is None else dps, survival_turns=margin,
                          combat_margin=margin, player_speed=speed)


class FinaleLoadoutTest(unittest.TestCase):
    def setUp(self):
        self.light = gear("light", 39)

    def loadout(self, ring):
        return Loadout((("light", self.light), (SLOT_MAIN_RING, ring)), "empty")

    def best(self, rings, scores, *, finale, depth=1, **options):
        loadouts = tuple(self.loadout(ring) for ring in rings)
        by_ring = {ring.id: score for ring, score in zip(rings, scores)}
        result = optimize_loadout(
            (self.light, *rings), lambda loadout: by_ring[loadout.item_at(SLOT_MAIN_RING).id],
            depth=depth, candidate_loadouts=loadouts, finale=finale, **options)
        return result.best.loadout.item_at(SLOT_MAIN_RING).id

    def test_resist_curse_first_over_ac_and_melee(self):
        curse, strong = gear("curse", 45, (TR_RES_CURSE,)), gear("strong", 45)
        scores = (metrics(10), metrics(500))
        self.assertEqual(self.best((curse, strong), scores, finale=False), "strong")
        self.assertEqual(self.best((curse, strong), scores, finale=True), "curse")

    def test_the_order(self):
        cases = (
            # speed over the resistances
            ((gear("fast", 45), metrics(10, speed=150)),
             (gear("resists", 45, (TR_RES_FIRE, TR_RES_COLD)), metrics(10, speed=140)), "fast"),
            # the resistances over telepathy (an immunity counts as its element)
            ((gear("immune", 45, (TR_IM_FIRE, TR_RES_NETHER)), metrics(10)),
             (gear("esp", 45, (TR_TELEPATHY, TR_RES_FIRE)), metrics(10)), "immune"),
            # telepathy over INT
            ((gear("esp", 45, (TR_TELEPATHY,)), metrics(10)),
             (gear("int", 45, (TR_INT,), pval=5), metrics(10)), "esp"),
            # INT over CON
            ((gear("int", 45, (TR_INT,), pval=2), metrics(10)),
             (gear("con", 45, (TR_CON,), pval=5), metrics(10)), "int"),
        )
        for (first, first_score), (second, second_score), winner in cases:
            with self.subTest(winner=winner):
                self.assertEqual(self.best((first, second), (first_score, second_score),
                                           finale=True), winner)
                self.assertEqual(self.best((second, first), (second_score, first_score),
                                           finale=True), winner)
                ranks = {ring.id: finale_rank(EvaluatedLoadout(self.loadout(ring), score))
                         for ring, score in ((first, first_score), (second, second_score))}
                loser = second.id if winner == first.id else first.id
                self.assertGreater(ranks[winner], ranks[loser])

    def test_no_half_melee_limit_in_the_band_descent(self):
        """depth None (the band descent): at 81F a set with under half the free melee is refused
        (``_within_half_melee``) unless the finale asks nothing of melee."""
        everything = required_abilities(81)
        curse, strong = gear("curse", 45, (TR_RES_CURSE,)), gear("strong", 45)
        scores = (metrics(10, dps=10), metrics(10, dps=100))
        options = dict(depth=None, intrinsic_abilities=everything, has_destruction=True)
        self.assertEqual(self.best((curse, strong), scores, finale=False, **options), "strong")
        self.assertEqual(self.best((curse, strong), scores, finale=True, **options), "curse")


if __name__ == "__main__":
    unittest.main()
