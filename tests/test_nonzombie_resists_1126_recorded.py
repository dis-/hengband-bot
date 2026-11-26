"""2026-11-26: poison, nether and see invisible for a character that is not a Zombie.

Owner 2026-11-26: 「ゾンビでない種族を扱うならば、毒耐性と地獄耐性の評価をちゃんとした方が良い」
「あと、透明視認も」.  Every character the bot played was a Zombie, whose race gives resist
poison, resist nether, see invisible, hold life, slow digestion and resist cold from CL5
(src/player/race-info-table.cpp, the Zombie row); the Amberite (sustain CON, regeneration) and
the Klackon (resist acid, resist confusion, speed) give none of them.

What changed: see invisible joins the 26F row of the depth table
(policy_constants.DEPTH_ABILITY_REQUIREMENTS) and is worth equipment_utility.SEE_INVISIBLE_BONUS
(+5%) to a character without it intrinsically.  What these tests also pin: the poison and nether
readings were already the character's own flags (the board's abilities and their sources), so a
non-Zombie's loadout search takes a poison resistance and its blow estimate is unreduced.

Recorded board: the n1-a life-464 Zombie Warrior (Lv40) town board of decision 2293,
tests/fixtures/gloves-phase-1102.json.gz, replayed through the public choose_key as
tests.test_gloves_phase_1102_recorded does.

DECLARED CONSTRUCTED (besides the replay's own calibration / ~f / ~9 seams):
- the non-Zombie: the same board with the race's permanent sources taken off the six Zombie
  abilities (an ability the gear also gives stays, with the equipment source only) and the
  calibration's intrinsic abilities and flags without them (``_non_zombie``);
- in the see-invisible tests, the see-invisible flag (TR 78) taken off every owned piece (worn,
  carried, Home), and one Home copy of the worn ドラゴン・グローブ with it added and 2 less AC;
- a fresh search of the constructed board: the replay's running equipment transaction and the
  visit's fixed target (equipment_target, review E3) are dropped (``_fresh_search``), since the
  replay decided them for the recorded Zombie board.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import unittest
from dataclasses import replace

from hengbot import ability_sources, equipment_target
from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.equipment_utility import SEE_INVISIBLE_BONUS, utility_value
from hengbot.monster_ranged_evaluator import _attribute_rates
from hengbot.policy import HengbotPolicy
import test_gloves_phase_1102_recorded as gloves

TR_SEE_INVIS = 78
WORN_GLOVES = "equipped:8f2b0ceb6cf8a721:0"
WORN_HELM = "equipped:c5ae2aa611667f03:0"
# The Home helm with RES_POIS (52) and FREE_ACT (46), [0,+13] (+2).
HOME_POISON_HELM = "home:fa7f0302881ff92a:0"
SI_GLOVES = "home:see-invisible-gloves"
# The Zombie's race abilities (race-info-table.cpp) and their TR flags.
ZOMBIE_ABILITIES = frozenset({"resist_pois", "resist_neth", "see_invisible", "hold_exp",
                              "slow_digest", "resist_cold"})
ZOMBIE_FLAGS = frozenset({52, 60, 78, 47, 80, 51})


def _non_zombie(policy, board, *, see_invisible_worn=True):
    """DECLARED CONSTRUCTED: ``board`` without the Zombie's race sources (see the docstring)."""
    player = board.player
    sources = {name: (frozenset(s for s in held if s != "permanent")
                      if name in ZOMBIE_ABILITIES else held)
               for name, held in player.ability_sources.items()}
    if not see_invisible_worn:
        sources["see_invisible"] = frozenset()
    abilities = frozenset(name for name in player.abilities
                          if name not in ZOMBIE_ABILITIES or sources.get(name))
    calibration = policy._character_calibration
    policy._character_calibration = replace(
        calibration, intrinsic_abilities=calibration.intrinsic_abilities - ZOMBIE_ABILITIES,
        intrinsic_tr_flags=calibration.intrinsic_tr_flags - ZOMBIE_FLAGS)
    return replace(board, player=replace(player, abilities=abilities, ability_sources=sources))


def _fresh_search(policy):
    """DECLARED CONSTRUCTED: the replay's transaction and visit target dropped (see the docstring)."""
    policy._equipment_transaction_session = None
    setattr(policy, equipment_target.VISIT_TARGET_STATE, None)
    equipment_target.invalidate_loadout_search(policy)


def _without_see_invisible(item):
    return replace(item, known_flags=item.known_flags - {TR_SEE_INVIS})


class NonZombieResistancesRecordedTest(unittest.TestCase):
    setUpClass = classmethod(
        gloves.DragonGlovesNotJunkRecordedTest.setUpClass.__func__)
    setUp = gloves.DragonGlovesNotJunkRecordedTest.setUp
    _replay = gloves.DragonGlovesNotJunkRecordedTest._replay

    def _board(self, *, zombie):
        policy, _decided = self._replay(gloves.OUTSIDE_ROW)
        board = policy._decision_input_snapshot
        _fresh_search(policy)
        return policy, (board if zombie else _non_zombie(policy, board))

    def _see_invisible_case(self, *, zombie):
        """The board with see invisible only on the Home gloves copy (see the docstring)."""
        policy, _decided = self._replay(gloves.OUTSIDE_ROW)
        board = policy._decision_input_snapshot
        _fresh_search(policy)
        board = replace(board,
                        equipment=tuple(_without_see_invisible(i) for i in board.equipment),
                        inventory=tuple(_without_see_invisible(i) for i in board.inventory))
        if not zombie:
            board = _non_zombie(policy, board, see_invisible_worn=False)
        catalog = policy._equipment_catalog
        for item_id, owned in list(catalog._home.items()):
            catalog._home[item_id] = replace(owned, item=_without_see_invisible(owned.item))
        worn = next(entry for entry in catalog.items if entry.id == WORN_GLOVES)
        catalog._home[SI_GLOVES] = OwnedEquipment(SI_GLOVES, replace(
            worn.item, to_a=worn.item.to_a - 2,
            known_flags=worn.item.known_flags | {TR_SEE_INVIS}), "home")
        return policy, board

    def test_recorded_board_is_a_zombie(self):
        _policy, board = self._board(zombie=True)
        sources = ability_sources.ability_source_map(board.player)
        for ability in ("resist_pois", "resist_neth", "see_invisible", "hold_exp", "slow_digest"):
            self.assertIn("permanent", sources[ability], ability)

    # --- the gate ------------------------------------------------------------------------------

    def test_zombie_gates_unchanged(self):
        policy, board = self._see_invisible_case(zombie=True)
        for depth in (20, 25, 26, 31, 40):
            self.assertEqual(policy._missing_required_abilities(board, depth), frozenset(), depth)

    def test_non_zombie_gates_name_poison_see_invisible_and_nether(self):
        policy, board = self._see_invisible_case(zombie=False)
        self.assertEqual(policy._missing_required_abilities(board, 25), frozenset())
        self.assertEqual(policy._missing_required_abilities(board, 26),
                         frozenset({"resist_pois", "see_invisible"}))
        self.assertEqual(policy._missing_required_abilities(board, 40),
                         frozenset({"resist_pois", "see_invisible", "resist_neth"}))

    # --- the loadout search --------------------------------------------------------------------

    def test_non_zombie_wears_see_invisible_below_the_gate(self):
        policy, board = self._see_invisible_case(zombie=False)
        preparation = policy._prepare_equipment_optimization(board, depth_override=20)
        self.assertEqual(preparation.blockers, ())
        best = preparation.result.best
        self.assertEqual(best.loadout.item_at("arms").id, SI_GLOVES)
        self.assertEqual(best.metrics.utility_value, SEE_INVISIBLE_BONUS)

    def test_zombie_keeps_the_higher_ac_gloves(self):
        policy, board = self._see_invisible_case(zombie=True)
        preparation = policy._prepare_equipment_optimization(board, depth_override=20)
        self.assertEqual(preparation.blockers, ())
        best = preparation.result.best
        self.assertEqual(best.loadout.item_at("arms").id, WORN_GLOVES)
        self.assertEqual(best.metrics.utility_value, 0.0)

    def test_non_zombie_takes_the_poison_resistance_helm(self):
        # No item constructed: the search reads the character's own resistances.
        for zombie, helm in ((True, WORN_HELM), (False, HOME_POISON_HELM)):
            with self.subTest(zombie=zombie):
                policy, board = self._board(zombie=zombie)
                preparation = policy._prepare_equipment_optimization(board)
                self.assertEqual(preparation.blockers, ())
                self.assertEqual(preparation.result.best.loadout.item_at("head").id, helm)

    # --- the damage estimates ------------------------------------------------------------------

    def test_poison_and_nether_estimates_read_the_character(self):
        _policy, zombie = self._board(zombie=True)
        _policy, other = self._board(zombie=False)
        # A poison blow of 100 (calc_blow_poison: one layer 100 -> 40).
        self.assertEqual(HengbotPolicy._maximum_melee_blow_damage(zombie, "POISON", 100), 40)
        self.assertEqual(HengbotPolicy._maximum_melee_blow_damage(other, "POISON", 100), 100)
        zombie_flags = ability_sources.held_ability_flags(zombie.player)
        other_flags = ability_sources.held_ability_flags(other.player)
        self.assertEqual(_attribute_rates("POIS", other_flags), (100,))
        self.assertLess(max(_attribute_rates("POIS", zombie_flags)), 100)
        self.assertEqual(_attribute_rates("NETHER", other_flags), (100,))
        self.assertEqual(_attribute_rates("NETHER", zombie_flags), (75, 66, 60, 54))


class SeeInvisibleUtilityTest(unittest.TestCase):
    """equipment_utility: the bonus is for a worn source of a character without it."""

    class _Piece:
        def __init__(self, flags):
            self.flags = frozenset(flags)
            self.item = type("Item", (), {"pval": 0})()

    def test_worn_see_invisible(self):
        self.assertEqual(utility_value([self._Piece({TR_SEE_INVIS})], frozenset()),
                         SEE_INVISIBLE_BONUS)

    def test_intrinsic_see_invisible_levels_every_loadout(self):
        self.assertEqual(utility_value([self._Piece({TR_SEE_INVIS})], frozenset({TR_SEE_INVIS})),
                         0.0)
        self.assertEqual(utility_value([self._Piece(())], frozenset({TR_SEE_INVIS})), 0.0)


if __name__ == "__main__":
    unittest.main()
