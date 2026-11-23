"""The dedicated 99F/100F loadout order (equipment_optimizer ``finale``, owner 2026-11-20, 11-24).

Owner, verbatim: 「装備は加速耐性テレパシーー知力耐久力を優先。ACや近接攻撃力は求めない。」,
「呪力耐性も要求する。これはオベロンの血の呪い、サーペントの破滅の手が致死的であるためである。」,
「耐盲目か耐閃光を条件に入れる」, then (2026-11-24) 「加速+25 知力18/150 耐久18/200 閃光轟音時間以外の
耐性を必須とする。それ以降は加点式。」 and 「ほぼ推奨案で良いが、閃光と時間の耐性は1% 轟音は5% 成功率は
不足1%につき5%」.
``finale_rank``: the gates (resist curse, resist blindness or light, telepathy, speed +25, INT
18/150, CON 18/200, every element but light, sound and time) and the number met, then the score
(HP times the energy per game turn, the optional resistances' shares, the Rockets' shortfall);
AC and melee only between loadouts it holds equal; the band descent's half-melee limit is not
asked.

DECLARED CONSTRUCTED: the catalog items (one light, rings of the flags each test names) and the
evaluator's metrics (the combat margin standing in for AC and melee).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest

from hengbot.equipment_optimizer import (
    FINALE_REQUIRED_RESISTANCES, SLOT_HEAD, SLOT_MAIN_RING, EvaluatedLoadout, FinaleReading,
    Loadout, LoadoutMetrics, OwnedEquipment, finale_rank, optimize_loadout, required_abilities,
)
from hengbot.model import InventoryItem

TR_INT, TR_CON, TR_TELEPATHY, TR_RES_CURSE = 1, 4, 79, 148
TR_RES_BLIND, TR_RES_LITE = 56, 54
TR_RES_FIRE, TR_RES_COLD, TR_IM_FIRE, TR_RES_NETHER = 50, 51, 42, 60


def gear(item_id, tval, flags=(), pval=0):
    item = InventoryItem(slot=item_id, name=item_id, count=1, tval=tval, sval=1, aware=True,
                         known=True, fully_known=True, is_equipment=True, pval=pval,
                         known_flags=frozenset(flags))
    return OwnedEquipment(item_id, item, "home")


TR_RES_SOUND, TR_RES_TIME = 58, 143
# Every gate but the stats: the rings of the score's cases carry them.
GATES = frozenset({TR_RES_CURSE, TR_TELEPATHY}) | FINALE_REQUIRED_RESISTANCES


def metrics(margin, *, speed=140, dps=None, hp=1000, intelligence=200, constitution=220,
            success=100):
    return LoadoutMetrics(expected_dps=margin if dps is None else dps, survival_turns=margin,
                          combat_margin=margin, player_speed=speed, finale_power_success=success,
                          finale_reading=FinaleReading(hp, intelligence, constitution))


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
            # a gate met over speed: resist blindness or light (owner 2026-11-20 Q6), either one
            ((gear("blind", 45, (TR_RES_BLIND,)), metrics(10, speed=140)),
             (gear("fast", 45), metrics(10, speed=150)), "blind"),
            ((gear("lite", 45, (TR_RES_LITE,)), metrics(10, speed=140)),
             (gear("fast", 45), metrics(10, speed=150)), "lite"),
            # a required element over speed (an immunity counts as its element)
            ((gear("immune", 45, (TR_IM_FIRE,)), metrics(10, speed=140)),
             (gear("fast", 45), metrics(10, speed=150)), "immune"),
            # CON 18/200 over HP and speed
            ((gear("con", 45, GATES), metrics(10, speed=135, hp=900, constitution=218)),
             (gear("weak", 45, GATES), metrics(10, speed=150, hp=1500, constitution=217)), "con"),
            # INT 18/150 likewise
            ((gear("int", 45, GATES), metrics(10, speed=135, intelligence=168)),
             (gear("dull", 45, GATES), metrics(10, speed=150, intelligence=167)), "int"),
            # the score: HP times the energy (HP 1100 at +25, 35, over HP 1000 at +28, 37)
            ((gear("hp", 45, GATES), metrics(10, speed=135, hp=1100)),
             (gear("speed", 45, GATES), metrics(10, speed=138, hp=1000)), "hp"),
            # resist sound 5%, resist light 1%
            ((gear("sound", 45, GATES | {TR_RES_SOUND}), metrics(10)),
             (gear("light", 45, GATES | {TR_RES_LITE, TR_RES_TIME}), metrics(10)), "sound"),
            # each percent of the Rockets' success short of 100 takes 5% (99%: 0.95 < 1.04)
            ((gear("sure", 45, GATES), metrics(10, hp=1000)),
             (gear("bigger", 45, GATES), metrics(10, hp=1040, success=99)), "sure"),
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

    def test_the_conditions_come_before_the_armour_fill(self):
        """n1-c life-221 2026-11-23 (owner 「★賢者マーリンの魔法の鏡を使用して条件を満たす装備を作れる」):
        the finale's conditions are requirements of its search, so a set meeting them is not
        dropped for one filling more armour slots (the fill tier); the ordinary search keeps it."""
        guard = gear("guard", 45, GATES)
        plain, helm = gear("plain", 45), gear("helm", 32)
        bare = Loadout((("light", self.light), (SLOT_MAIN_RING, guard)), "empty")
        helmed = Loadout((("light", self.light), (SLOT_MAIN_RING, plain), (SLOT_HEAD, helm)),
                         "empty")
        scores = {guard.id: metrics(10), plain.id: metrics(500)}

        def best(finale):
            result = optimize_loadout(
                (self.light, guard, plain, helm),
                lambda loadout: scores[loadout.item_at(SLOT_MAIN_RING).id],
                depth=1, candidate_loadouts=(bare, helmed), finale=finale,
                require_armor_slots=frozenset({SLOT_HEAD}))
            return result.best.loadout.item_at(SLOT_MAIN_RING).id

        self.assertEqual(best(False), "plain")
        self.assertEqual(best(True), "guard")


class FinaleExhaustiveSearchTest(unittest.TestCase):
    """warrior_loadout_search.finale_exhaustive_search against every combination of a small
    catalog (owner 2026-11-24 「装備が最適化されていない」: the single-slot climb missed a set
    changing six slots at once).  DECLARED CONSTRUCTED: the items (rings, an amulet, a light,
    a helm, boots of fixed-seed random flags and pvals) and the character's figures."""

    def figures(self):
        from hengbot.warrior_loadout_search import FinaleFigures
        return FinaleFigures(
            base_speed=110, intrinsic_flags=frozenset({TR_RES_COLD}),
            intelligence=lambda bonus: 140 + 10 * bonus,
            constitution=lambda bonus: 180 + 10 * bonus,
            max_hp=lambda bonus: 900 + 25 * bonus,
            power_success=lambda bonus, flags: min(100, 90 + bonus))

    def test_the_best_key_over_every_combination(self):
        import itertools
        import random
        from hengbot.warrior_loadout_search import finale_exhaustive_search
        rng = random.Random(1124)
        pool = sorted(GATES | {TR_RES_SOUND, TR_RES_LITE, TR_RES_TIME})
        kinds = {"ring": 45, "neck": 40, "light": 39, "head": 32, "feet": 30}
        stats = (12, TR_INT, TR_CON)  # TR_SPEED, INT, CON
        items = []
        for kind, tval in kinds.items():
            for index in range(5 if kind == "ring" else 4):
                flags = set(rng.sample(pool, 6)) | {rng.choice(stats)}
                items.append(gear(f"{kind}{index}", tval, flags, pval=rng.randint(1, 6)))
        figures = self.figures()

        def key(loadout):
            def total(flag):
                return sum(item.item.pval for _, item in loadout.slots if flag in item.flags)
            return figures.rank_key(total(12), total(TR_INT), total(TR_CON), loadout.flags)

        rings = [item for item in items if item.item.tval == 45]
        slots = {tval: [item for item in items if item.item.tval == tval]
                 for tval in (40, 39, 32, 30)}
        names = {40: "neck", 39: "light", 32: "head", 30: "feet"}
        best = None
        for pair in itertools.combinations(rings, 2):
            for choice in itertools.product(*slots.values()):
                loadout = Loadout(((SLOT_MAIN_RING, pair[0]), ("sub_ring", pair[1]),
                                   *((names[item.item.tval], item) for item in choice)), "empty")
                if best is None or key(loadout) > best:
                    best = key(loadout)
        found = finale_exhaustive_search(
            items, figures, require_light=True, fill_slots=frozenset({"head", "feet"}))
        self.assertTrue(found.complete)
        self.assertEqual(key(found.loadouts[0]), best)


if __name__ == "__main__":
    unittest.main()
