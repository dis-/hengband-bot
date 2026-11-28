"""Owner 2026-11-17: the equipment selection values speed (speed_valuation).

「装備最適化のスピードの評価を上げて。特にspeed+20までは生存に大きく寄与する」 and, asked what to
raise, 「時間あたりの打撃＋+20までを強く」.  Every damage the selection compares is per
game time (``speed_energy`` of the loadout's permanent speed) and the survival /
kill ratio is weighted by the speed up to +20; the depth requirements, the half
melee floor and the speed +25 requirement (SPEED_GATE_DEPTH: 81F when written, 91F since the
owner's 2026-11-28 「80Fから90Fまでは危険度に大きな変化はない」) stay hard, the last read as one fact
(the permanent speed) by the optimizer and the arrival check alike.  The recorded bands of 80 were
the deepest band short of the +25 row then; the same loadouts now reach the band below the moved
row (SPEED_GATE_DEPTH - 1, equipment_optimizer.DEPTH_BANDS 90).

Recorded: the optimizer inputs of the three viewing bots at their 2026-11-17 town
arrivals (tests/extract_speed_valuation_1117_fixtures.py; n1-c's calibration and
~f skill are DECLARED CONSTRUCTED there) and the choices their loadout reports
recorded on the same boards (fixtures/speed-valuation-1117/recorded.json).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import destruction_use
from hengbot.equipment_optimizer import (
    ABILITY_FLAG,
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OwnedEquipment,
    _stable_operational_best,
    divable_depth,
    optimize_loadout,
)
from hengbot.model import InventoryItem
from hengbot.policy_constants import SPEED_GATE_DEPTH, SPEED_GATE_LABEL, speed_energy
from hengbot.policy_observation import ObservationMixin
from hengbot.speed_valuation import (
    loadout_speed,
    meets_speed_gate,
    permanent_player_speed,
    time_melee,
)
from hengbot.warrior_optimization import prepare_warrior_optimization

FIXTURE = Path(__file__).with_name("fixtures") / "speed-valuation-1117"
BELOW_SPEED_GATE = SPEED_GATE_DEPTH - 1   # the deepest band without the +25 row
RECORDED = json.loads((FIXTURE / "recorded.json").read_text(encoding="utf-8"))
SPEED_RING_7 = "スピードの指輪 (+7) {+速}"
VITALITY_SPEED_RING = "活力のスピードの指輪 (+6) {+速;活}"


def recorded_choice(bot):
    snapshot, items, knowledge, kwargs = pickle.loads(
        lzma.decompress((FIXTURE / f"{bot}.pkl.xz").read_bytes()))
    preparation = prepare_warrior_optimization(
        snapshot, items, knowledge, **{**kwargs, "timeout_seconds": 600.0})
    return preparation, {slot: item.item.name for slot, item in preparation.result.best.loadout.slots}


def gear(item_id, slot, *, flags=()):
    item = InventoryItem(
        slot=item_id, name=item_id, count=1, tval=45, sval=1, aware=True, known=True,
        fully_known=True, is_equipment=True, known_flags=frozenset(flags))
    return OwnedEquipment(item_id, item, "home"), slot


def entry(name, *, dps, survival, margin, speed):
    owned, slot = gear(name, "feet")
    return EvaluatedLoadout(
        Loadout(((slot, owned),), "empty"),
        LoadoutMetrics(expected_dps=dps, survival_turns=survival, combat_margin=margin,
                       speed_bonus=speed - 110, player_speed=speed))


def chosen(*entries):
    return _stable_operational_best(entries, frozenset()).loadout.slots[0][1].id


class RecordedSpeedChoicesTest(unittest.TestCase):
    """The three viewing bots, before (recorded) and after."""

    def test_n1c_wears_both_speed_rings(self):
        before = RECORDED["n1-c"]
        self.assertEqual((before["speed"], round(before["melee_output"], 1)), (2, 493.9))
        self.assertEqual(before["slots"]["main_ring"], "ダメージの指輪 (+16)")
        self.assertEqual(before["slots"]["sub_ring"], "追加攻撃の指輪 (+1攻撃) {+攻}")
        preparation, after = recorded_choice("n1-c")
        best = preparation.result.best.metrics
        self.assertEqual({after["main_ring"], after["sub_ring"]}, {SPEED_RING_7, VITALITY_SPEED_RING})
        self.assertGreaterEqual(best.speed_bonus, 15)
        # Fewer blows per action, far more per game time.
        self.assertLess(best.expected_dps, before["melee_output"])
        self.assertGreater(time_melee(best), before["melee_output"] * speed_energy(112) / 10)
        self.assertEqual(preparation.result.chosen_depth, BELOW_SPEED_GATE)

    def test_n1b_reaches_plus_ten_and_keeps_the_damage_ring(self):
        before = RECORDED["n1-b"]
        self.assertEqual(before["speed"], 7)
        self.assertEqual(before["slots"]["main_ring"], "ダメージの指輪 (+11)")
        preparation, after = recorded_choice("n1-b")
        self.assertEqual(preparation.result.best.metrics.speed_bonus, 10)
        self.assertEqual(after["main_ring"], "ダメージの指輪 (+11)")
        self.assertEqual(after["sub_ring"], SPEED_RING_7)
        self.assertEqual(preparation.result.chosen_depth, BELOW_SPEED_GATE)

    def test_n1b_arrival_leaves_the_iron_geta(self):
        """The arrival board chose the ★炎の鉄ゲタ (-1) and 腕力の指輪 over the speed ring
        (recorded 14:11:13, melee 254.0); the next boards chose +7: the two alternated."""
        before = RECORDED["n1-b-arrival"]
        self.assertEqual((before["speed"], round(before["melee_output"], 1)), (-1, 254.0))
        self.assertIn("炎の鉄ゲタ", before["slots"]["feet"])
        preparation, after = recorded_choice("n1-b-arrival")
        self.assertEqual(preparation.result.best.metrics.speed_bonus, 10)
        self.assertEqual(after["feet"], "ドラゴン・ブーツ [5,+19] {r暗}")
        self.assertEqual(after["sub_ring"], SPEED_RING_7)
        # The arrival and the later board now choose the same set.
        self.assertEqual(after, recorded_choice("n1-b")[1])

    def test_n1a_keeps_wielding_the_speed_artifact(self):
        before = RECORDED["n1-a"]
        self.assertEqual(before["speed"], 2)
        self.assertIn("ワーウィンドル", before["slots"]["sub_hand"])
        preparation, after = recorded_choice("n1-a")
        self.assertIn("ワーウィンドル", after["sub_hand"])
        self.assertEqual(preparation.result.best.metrics.speed_bonus, 2)
        self.assertEqual(preparation.result.chosen_depth, before["chosen_band"])


class SelectionTest(unittest.TestCase):
    def test_damage_is_compared_per_game_time(self):
        # 80 per action at +10 (energy 20) is 160 per time, 100 at +0 is 100.
        self.assertEqual(chosen(
            entry("slow", dps=100, survival=40, margin=10, speed=110),
            entry("fast", dps=80, survival=40, margin=10, speed=120)), "fast")

    def test_speed_up_to_twenty_counts_squared_on_the_ratio(self):
        # Equal damage per time; the ratio of the +0 set is higher, weighted it is lower.
        self.assertEqual(chosen(
            entry("plain", dps=100, survival=40, margin=10, speed=110),
            entry("hasty", dps=50, survival=40, margin=6, speed=120)), "hasty")

    def test_beyond_twenty_the_energy_alone_applies(self):
        # +30 (energy 38) vs +20 (30): the same damage per time, no extra weight.
        self.assertEqual(chosen(
            entry("twenty", dps=38, survival=40, margin=10, speed=130),
            entry("thirty", dps=30, survival=40, margin=9.8, speed=140)), "twenty")

    def test_n1b_iron_geta_case(self):
        """n1-b life-411 2026-11-17 13:41 (loadout report row 1432, band 49).

        Recorded: ★炎の鉄ゲタ set 187.35 per action, ratio 13.736, survival 41.3,
        speed +9; the ドラゴン・ブーツ [5,+19] set 184.59 (98.5%), ratio 14.369, survival
        43.6, speed +10 - chosen: the ゲタ.  Both cleared the 30-turn floor, so the
        boots set fell at the 95% cut, anchored at a set of more than 194.3 per
        action (184.59 / 0.95) that the ratio band then dropped.  That set's
        metrics are not in the report: DECLARED CONSTRUCTED as 196 per action at
        +6 with ratio 12.  Per game time the boots set is the strongest.
        """
        geta = entry("geta", dps=187.35, survival=41.25, margin=13.736, speed=119)
        boots = entry("boots", dps=184.59, survival=43.61, margin=14.369, speed=120)
        heavy = entry("heavy", dps=196.0, survival=35.0, margin=12.0, speed=116)
        self.assertEqual(chosen(geta, boots, heavy), "boots")

    def test_one_speed_field_is_compared_as_before(self):
        # Same speed everywhere: no weight, the damage per time scales them all alike.
        self.assertEqual(chosen(
            entry("strong", dps=100, survival=40, margin=10, speed=117),
            entry("tough", dps=96, survival=60, margin=10.2, speed=117)), "tough")


class HardRequirementTest(unittest.TestCase):
    def test_a_speed_ring_does_not_replace_a_depth_resistance(self):
        """20F requires resist fire: the faster, stronger set without it is refused."""
        fire, _ = gear("ring of fire resistance", "main_ring", flags=(ABILITY_FLAG["resist_fire"],))
        speed, _ = gear("ring of speed", "main_ring")
        metric = {
            "ring of fire resistance": LoadoutMetrics(
                expected_dps=50, survival_turns=40, combat_margin=5, player_speed=110),
            "ring of speed": LoadoutMetrics(
                expected_dps=100, survival_turns=80, combat_margin=20, speed_bonus=20,
                player_speed=130),
        }
        result = optimize_loadout(
            (fire, speed),
            lambda loadout: metric[loadout.slots[0][1].id],
            depth=20,
            intrinsic_abilities=frozenset({"free_action"}),
            candidate_loadouts=(Loadout((("main_ring", fire),), "empty"),
                                Loadout((("main_ring", speed),), "empty")),
            require_light=False, require_body=False, require_armor_slots=frozenset(),
        )
        self.assertEqual(result.best.loadout.slots[0][1].id, "ring of fire resistance")

    def test_the_speed_gate_reads_the_permanent_speed(self):
        # Gear +25 on a slowed (overweight) base 108 is 133: refused; gear +20 on a
        # base 115 (an intrinsic +5) is 135: met.
        self.assertFalse(meets_speed_gate(108 + 25))
        self.assertTrue(meets_speed_gate(115 + 20))
        empty = Loadout((), "empty")
        abilities = frozenset(ABILITY_FLAG)
        self.assertEqual(divable_depth(empty, intrinsic_abilities=abilities,
                                       has_destruction=True, player_speed=133), BELOW_SPEED_GATE)
        self.assertEqual(divable_depth(empty, intrinsic_abilities=abilities,
                                       has_destruction=True, player_speed=135), SPEED_GATE_DEPTH)
        self.assertEqual(loadout_speed(LoadoutMetrics(1, 1, 1, speed_bonus=25)), 135)

    def test_a_haste_does_not_open_the_speed_gate(self):
        def board(speed, colour):
            player = SimpleNamespace(speed=speed, abilities=frozenset(ABILITY_FLAG),
                                     speed_display=(speed - 110, "", colour, False))
            return SimpleNamespace(player=player)

        hasted = board(140, "yellow")  # +30 shown, +20 of it permanent
        slowed = board(127, "violet")  # +17 shown, +27 permanent
        self.assertEqual(permanent_player_speed(hasted), 130)
        self.assertEqual(permanent_player_speed(slowed), 137)
        self.assertEqual(permanent_player_speed(board(135, "")), 135)
        with patch.object(destruction_use, "holds_means", return_value=True):
            self.assertIn(SPEED_GATE_LABEL, ObservationMixin._missing_required_abilities(
                SimpleNamespace(), hasted, SPEED_GATE_DEPTH))
            self.assertNotIn(SPEED_GATE_LABEL, ObservationMixin._missing_required_abilities(
                SimpleNamespace(), slowed, SPEED_GATE_DEPTH))


if __name__ == "__main__":
    unittest.main()
