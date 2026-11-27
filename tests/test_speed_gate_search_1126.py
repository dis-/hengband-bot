"""The single-slot loadout search completes a set that reaches a depth's speed by two swaps.

n1-c life-222 (Magic-Eater, Angband 80F, 2026-11-25; the server's jsonlog/loadout-report.jsonl
and equipment-visit.jsonl, the snapshots of 04:13-19:46): +19 worn (スピードの指輪 +12 and +8,
★炎の鉄ゲタ -1), ★ハーゲンのスピア (+3) in the Home from 04:09 and ☆破隼 (+3) from 15:57, both
fully known.  The Home was past the single-slot threshold, so every search was one swap from
the worn set: the spear alone (+22) or the armour alone (+22) never reached the 81F +25, neither
scored better at 80F, and the 81F band read ``no-set`` for 15 hours until the level 49 made the
spear the 80F choice (19:46:23, then the armour, +25).
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import destruction_use, haste_sustain

from hengbot.equipment_optimizer import (
    SLOT_BODY, SLOT_FEET, SLOT_LIGHT, SLOT_MAIN_HAND, SLOT_MAIN_RING, SLOT_SUB_RING,
    LoadoutMetrics, optimize_loadout, required_abilities,
)
from hengbot.equipment_optimizer import ABILITY_FLAG
from hengbot.policy_constants import (
    DESTRUCTION_GATE_LABEL, MID_SPEED_GATE_LABEL, SPEED_GATE_LABEL, SPEED_GATE_MINIMA,
    SPEED_GATE_MINIMUM, required_depth_gates, required_speed,
)
from hengbot.policy_observation import ObservationMixin
from hengbot.warrior_defense_evaluator import TR_SPEED
from hengbot.warrior_loadout_search import (
    SPEED_COMPLETION_LIMIT, SpeedGate, enumerate_single_slot_variants, speed_gates,
)
from test_warrior_loadout_search import owned

BASE_SPEED = 110


def equipped(item_id, tval, slot, **kw):
    return replace(owned(item_id, tval, **kw), origin="equipped", equipped_slot=slot)


def _metrics_for(melee: dict):
    """Speed read from the worn speed pvals (the evaluator's player_speed); the scythe and the
    plate score better than the speed pieces, as the 80F choice did on the board."""
    def metrics(loadout):
        gear = sum(item.item.pval for _, item in loadout.slots if TR_SPEED in item.flags)
        # The main hand's melee (a second weapon adds nothing here) and the plate's share.
        value = sum(melee.get(item.id, 0.0) for slot, item in loadout.slots
                    if slot in (SLOT_MAIN_HAND, SLOT_BODY))
        if loadout.hand_mode == "dual_wield":
            value /= 2  # two heavy polearms without the two-weapon skill (two_weapon_skill 0)
        return LoadoutMetrics(
            expected_dps=value, survival_turns=100.0, combat_margin=1.0, secondary_value=0.0,
            speed_bonus=gear, relevant_traits=frozenset(), evaluation_complete=True)
    return metrics


class LifeTwoTwentyTwoSpeedTest(unittest.TestCase):
    def setUp(self):
        self.light = equipped("palantir", 39, SLOT_LIGHT)
        self.ring12 = equipped("speed-ring-12", 45, SLOT_MAIN_RING, flags=(TR_SPEED,), pval=12)
        self.ring8 = equipped("speed-ring-8", 45, SLOT_SUB_RING, flags=(TR_SPEED,), pval=8)
        self.geta = equipped("geta", 30, SLOT_FEET, flags=(TR_SPEED,), pval=-1, ac=6, to_a=20)
        self.plate = equipped("olog-plate", 37, SLOT_BODY, ac=35, to_a=21)
        self.scythe = equipped("scythe", 22, SLOT_MAIN_HAND, dice=(8, 4), to_h=15, to_d=8)
        self.spear = owned("hagen-spear", 22, flags=(TR_SPEED,), pval=3, dice=(1, 6),
                           to_h=11, to_d=13)
        self.hayabusa = owned("hayabusa", 36, flags=(TR_SPEED,), pval=3, ac=5, to_a=10)
        self.items = (self.light, self.ring12, self.ring8, self.geta, self.plate, self.scythe,
                      self.spear, self.hayabusa)
        self.current = frozenset(item.id for item in self.items if item.origin == "equipped")
        self.target = frozenset(self.current - {"olog-plate", "scythe"}
                                | {"hagen-spear", "hayabusa"})
        self.evaluate = _metrics_for({"scythe": 1000.0, "hagen-spear": 900.0,
                                      "olog-plate": 50.0})

    def search(self, gates=()):
        return list(enumerate_single_slot_variants(
            self.items, current_item_ids=self.current, require_light=True,
            speed_gates=gates))

    def test_the_two_swaps_are_searched_only_with_the_speed_gate(self):
        plain = {loadout.item_ids for loadout in self.search()}
        self.assertNotIn(self.target, plain)
        found = {loadout.item_ids: loadout
                 for loadout in self.search(speed_gates(BASE_SPEED, SPEED_GATE_MINIMA))}
        self.assertIn(self.target, found)
        gate = SpeedGate(BASE_SPEED, SPEED_GATE_MINIMUM)
        self.assertEqual(gate.skill(found[self.target]), 25)
        self.assertTrue(gate.opens(found[self.target]))
        # Every completion reaches the gate; the plain neighbours are all still there.
        for ids in set(found) - plain:
            self.assertTrue(gate.opens(found[ids]))
        self.assertTrue(plain <= set(found))

    def test_the_eighty_one_band_takes_the_completed_set(self):
        intrinsic = required_abilities(81)
        without = optimize_loadout(
            self.items, self.evaluate, depth=None, intrinsic_abilities=intrinsic,
            has_destruction=True, current_item_ids=self.current,
            candidate_loadouts=self.search(), require_light=True, require_body=True)
        self.assertEqual(without.band_decisions[0].band, 81)
        self.assertEqual(without.band_decisions[0].refusal_reason, "no-set")
        self.assertLess(without.chosen_depth, 81)
        result = optimize_loadout(
            self.items, self.evaluate, depth=None, intrinsic_abilities=intrinsic,
            has_destruction=True, current_item_ids=self.current,
            candidate_loadouts=self.search(speed_gates(BASE_SPEED, SPEED_GATE_MINIMA)),
            require_light=True, require_body=True)
        self.assertEqual(result.chosen_depth, 81)
        best = result.best.loadout
        self.assertTrue({"hagen-spear", "hayabusa"} <= best.item_ids)
        self.assertEqual(best.item_at(SLOT_MAIN_HAND).id, "hagen-spear")
        self.assertTrue(SpeedGate(BASE_SPEED, SPEED_GATE_MINIMUM).opens(best))

    def test_a_met_gate_adds_nothing(self):
        fast = SpeedGate(BASE_SPEED + 6, SPEED_GATE_MINIMUM)
        self.assertEqual({loadout.item_ids for loadout in self.search((fast,))},
                         {loadout.item_ids for loadout in self.search()})

    def test_many_speed_pieces_stay_bounded(self):
        # A Home of +1 pieces in every armour slot: each slot keeps its two best swaps and at
        # most SPEED_COMPLETION_LIMIT combinations are completed.
        extra = tuple(
            owned(f"plus1-{tval}-{index}", tval, flags=(TR_SPEED,), pval=1 + index % 2, ac=1)
            for tval in (30, 31, 32, 35, 36, 40) for index in range(6))
        items = self.items + extra
        base = list(enumerate_single_slot_variants(
            items, current_item_ids=self.current, require_light=True))
        found = list(enumerate_single_slot_variants(
            items, current_item_ids=self.current, require_light=True,
            speed_gates=(SpeedGate(BASE_SPEED - 4, SPEED_GATE_MINIMUM),)))
        self.assertLessEqual(len(found) - len(base), SPEED_COMPLETION_LIMIT)
        self.assertGreater(len(found), len(base))


class SeventyFloorSpeedGateTest(unittest.TestCase):
    """Supervisor 2026-11-26: 70-80F ask a speed of +10 (five of the seven deaths at 76-80F before it
    had +9 or less); since 2026-11-27 permanent, or sustained by Speed doses (haste_sustain)."""

    def test_the_rows(self):
        self.assertNotIn(MID_SPEED_GATE_LABEL, required_depth_gates(69))
        for depth in (70, 76, 80):
            gates = required_depth_gates(depth)
            self.assertIn(MID_SPEED_GATE_LABEL, gates)
            self.assertNotIn(SPEED_GATE_LABEL, gates)
            self.assertIn(DESTRUCTION_GATE_LABEL, gates)
        self.assertIn(SPEED_GATE_LABEL, required_depth_gates(81))
        self.assertNotIn(MID_SPEED_GATE_LABEL, required_depth_gates(81))
        self.assertEqual([required_speed(depth) for depth in (69, 70, 80, 81)],
                         [0, 120, 120, 135])
        self.assertEqual(sorted(SPEED_GATE_MINIMA), [120, 135])

    def test_the_gate_reads_the_permanent_speed(self):
        # The one predicate of the stairs, the recall landing and the floor's gap.
        def board(speed, colour=""):
            player = SimpleNamespace(speed=speed, abilities=frozenset(ABILITY_FLAG),
                                     speed_display=(speed - 110, "", colour, False))
            return SimpleNamespace(player=player)

        def missing(snapshot, depth):
            return ObservationMixin._missing_required_abilities(
                SimpleNamespace(), snapshot, depth)

        with patch.object(destruction_use, "holds_means", return_value=True),                 patch.object(haste_sustain, "uses", return_value=0):
            self.assertEqual(missing(board(119), 69), frozenset())
            self.assertEqual(missing(board(119), 70), {MID_SPEED_GATE_LABEL})
            self.assertEqual(missing(board(119), 80), {MID_SPEED_GATE_LABEL})
            self.assertEqual(missing(board(120), 80), frozenset())
            # A haste's +10 is no permanent speed.
            self.assertEqual(missing(board(125, "yellow"), 75), {MID_SPEED_GATE_LABEL})
            # 81F asks +25 alone (it includes +10).
            self.assertEqual(missing(board(130), 81), {SPEED_GATE_LABEL})
        # Supervisor 2026-11-27: doses sustained for the dive meet the 70-80F row, never 81F's.
        with patch.object(destruction_use, "holds_means", return_value=True),                 patch.object(haste_sustain, "uses", return_value=haste_sustain.RETURN_RESERVE_USES):
            self.assertEqual(missing(board(113), 75), frozenset())
            self.assertEqual(missing(board(130), 81), {SPEED_GATE_LABEL})


if __name__ == "__main__":
    unittest.main()
