"""2026-11-26: poison for a character without poison resistance; the 36F nether row; the
see-invisible row is bought, not drunk.

Supervisor 2026-11-26 (on the owner's 「ゾンビでない種族を扱うならば、毒耐性と地獄耐性の評価をちゃんと
した方が良い」「あと、透明視認も」): every character before was a Zombie, which resists poison
(src/player/race-info-table.cpp) and was never poisoned, so the rules that said 「not poisoned」 had
never been met.  The game (status_cure's poison block): a poisoned player loses 1 HP a tick with no
message and no regeneration, the loss disturbs any rest, and Cure Critical Wounds, Healing, the
Potion and the Mushroom of Cure Poison cure it.

* status_cure.poison_cure_key: the cure is drunk on a quiet board when HP is below half (or the
  low-HP line) or the estimated rest of the poison is more than 15% of max HP; a light poison runs
  out while the player explores on;
* status_cure.loss_is_an_attack: a poisoned player's loss counts as an attack's when an attack
  message or its size shows one, so an unseen bite is answered as without the poison;
* policy_constants.DEPTH_ABILITY_REQUIREMENTS: nether from 36F;
* ability_sources.lasting_abilities: a temporary-only ability (a Potion of See Invisible) meets no
  depth row; ability_gear buys the Ring of See Invisible for the missing row.

Recorded boards:

* the Forest 32F boards 532 and 534 of tests/test_low_hp_no_unchecked_walk.py (Zombie Warrior,
  HP 731): 532 explores with nothing in view; 534 is the unseen bite at HP 420;
* the n1-c life-218 town visit of tests/test_equip_e4b_shelf_evaluation_1122_recorded.py (Zombie
  Magic-Eater, landing 49F).

DECLARED CONSTRUCTED:

* the poison: ``poisoned`` set on the board, its HP (and once the previous board's HP) and messages (the onset line
  「毒に侵されてしまった！」 of bad-status-setter.cpp) as each test says, and the turn moved on by one
  tick;
* the non-Zombie of the town visit: the race's permanent sources taken off its abilities (see
  invisible also off the worn kit, as for a character without it); a shelf Ring of See Invisible
  made from that test's shelf ring (sval 22, flag 78), and no owned see-invisible piece
  (``owned_unworn_sources`` patched to none, as that test does);
* the Potion of See Invisible: see invisible on the board with the ``temporary`` source only.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hengbot import ability_gear, ability_sources, status_cure
from hengbot.cli import _consume_response_sequence
from hengbot.model import SV_POTION_CURE_CRITICAL
from hengbot.policy_constants import required_depth_gates
import test_equip_e4b_shelf_evaluation_1122_recorded as e4b
import test_low_hp_no_unchecked_walk as low_hp

ONSET = "毒に侵されてしまった！"
TR_SEE_INVIS = 78
ZOMBIE_ABILITIES = frozenset({"resist_pois", "resist_neth", "see_invisible", "hold_exp",
                              "slow_digest", "resist_cold"})


class PoisonRecordedTest(low_hp._Boards):
    def _quiet(self):
        """Board 532 (nothing in view, HP 731/731), decided once so the next board compares HP."""
        _decoded, snapshots = _consume_response_sequence(
            [self.boards[532]], self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl")
        board = snapshots[-1]
        self.assertFalse([m for m in board.visible_monsters if m.hostile])
        self.policy.confirm_key_posted(self.policy.choose_key(board))
        return board

    def _poisoned(self, board, *, hp, onset, ticks=1):
        # DECLARED CONSTRUCTED: the poison (module docstring).
        return replace(board, player=replace(board.player, hp=hp, poisoned=True),
                       messages=[ONSET] if onset else [], turn=board.turn + 10 * ticks)

    def _decide(self, board):
        key = str(self.policy.choose_key(board))
        self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason

    def _cure_key(self, board):
        potion = next(item for item in board.inventory
                      if item.is_potion and item.sval == SV_POTION_CURE_CRITICAL)
        return "q" + potion.slot

    def test_a_heavy_poison_is_cured_on_the_next_quiet_board(self):
        quiet = self._quiet()
        bitten = self._poisoned(quiet, hp=611, onset=True)     # 120 lost: the poisoning hit
        key, reason = self._decide(bitten)
        self.assertNotEqual(reason, status_cure.POISON_CURE_REASON)   # the hit's board
        self.assertEqual(status_cure.poison_remaining(self.policy, bitten), 130)
        tick = self._poisoned(bitten, hp=610, onset=False)
        self.assertEqual(self._decide(tick), (self._cure_key(tick), status_cure.POISON_CURE_REASON))

    def test_a_light_poison_runs_out_while_exploring(self):
        quiet = self._quiet()
        bitten = self._poisoned(quiet, hp=725, onset=True)     # 6 lost: 16 estimated
        self.assertEqual(self._decide(bitten), ("3", "explore"))
        tick = self._poisoned(bitten, hp=724, onset=False)
        self.assertEqual(self._decide(tick), ("3", "explore"))
        self.assertFalse(status_cure.loss_is_an_attack(self.policy, tick))
        self.assertTrue(status_cure.poison_tick_only(self.policy, tick))
        self.assertEqual(self.policy._unexplained_damage_streak, 0)

    def test_below_half_hp_the_poison_is_cured(self):
        quiet = self._quiet()
        # No onset seen (a restart while poisoned): only the HP line decides.
        low = self._poisoned(quiet, hp=300, onset=False)
        # DECLARED CONSTRUCTED: the previous board's HP one tick above (a poison tick, not a hit).
        self.policy._last_hp = 301
        key, reason = self._decide(low)
        self.assertEqual((key, reason), (self._cure_key(low), status_cure.POISON_CURE_REASON))

    def test_an_unseen_bite_while_poisoned_is_answered_as_without_it(self):
        answers = []
        for poisoned in (False, True):
            board = low_hp.LowHpHealVsTeleportTest._kit_board(self, cure_serious=True)
            if poisoned:
                board = replace(board, player=replace(board.player, poisoned=True))
            policy = copy.deepcopy(self.policy)
            answers.append((str(policy.choose_key(board)), policy.last_reason))
        scroll = next(i for i in board.inventory if i.is_teleport_scroll)
        self.assertEqual(answers, [("r" + scroll.slot, "emergency:teleport")] * 2)


class NonZombieGatesRecordedTest(unittest.TestCase):
    setUpClass = classmethod(e4b.ShelfEvaluationRecordedTest.setUpClass.__func__)
    tearDownClass = classmethod(e4b.ShelfEvaluationRecordedTest.tearDownClass.__func__)

    def _non_zombie(self):
        """DECLARED CONSTRUCTED (module docstring)."""
        player = self.board.player
        sources = {name: (frozenset(s for s in held if s != "permanent")
                          if name in ZOMBIE_ABILITIES else held)
                   for name, held in player.ability_sources.items()}
        sources["see_invisible"] = frozenset()
        abilities = frozenset(name for name in player.abilities
                              if name not in ZOMBIE_ABILITIES or sources.get(name))
        return replace(self.board, player=replace(player, abilities=abilities,
                                                  ability_sources=sources))

    def test_the_zombie_meets_every_row_it_met(self):
        missing = self.policy._missing_required_abilities(self.board, 49)
        self.assertEqual(missing, frozenset({"resist_chaos"}))   # the recorded visit's gap

    def test_nether_from_thirty_six(self):
        self.assertNotIn("resist_neth", required_depth_gates(35))
        self.assertIn("resist_neth", required_depth_gates(36))
        board = self._non_zombie()
        self.assertNotIn("resist_neth", self.policy._missing_required_abilities(board, 35))
        self.assertIn("resist_neth", self.policy._missing_required_abilities(board, 36))

    def test_the_ring_of_see_invisible_is_bought_for_the_row(self):
        board = self._non_zombie()
        self.assertIn("see_invisible", ability_gear._landing_missing(self.policy, board))
        flags = ability_gear._open_flags(self.policy, board)
        self.assertIn(TR_SEE_INVIS, flags)
        ring = replace(self.ring, name="透明物体感知の指輪", sval=22,
                       known_flags=frozenset({TR_SEE_INVIS}))
        with mock.patch.object(ability_sources, "owned_unworn_sources", lambda *_args: []):
            self.assertEqual(
                ability_gear._rows(self.policy, board, SimpleNamespace(items=[ring]), flags),
                [ring])

    def test_a_potion_of_see_invisible_meets_no_row(self):
        board = self._non_zombie()
        player = board.player
        drunk = replace(board, player=replace(
            player, abilities=player.abilities | {"see_invisible"},
            ability_sources={**player.ability_sources, "see_invisible": frozenset({"temporary"})}))
        self.assertIn("see_invisible", drunk.player.abilities)
        self.assertIn("see_invisible", self.policy._missing_required_abilities(drunk, 49))
        worn = replace(drunk, player=replace(drunk.player, ability_sources={
            **drunk.player.ability_sources, "see_invisible": frozenset({"equipment"})}))
        self.assertNotIn("see_invisible", self.policy._missing_required_abilities(worn, 49))


if __name__ == "__main__":
    unittest.main()
