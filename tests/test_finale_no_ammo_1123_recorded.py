"""The Magic-Eater fires no round in the finale and deposits them all at the Home (2026-11-23).

Owner 2026-11-23 (verbatim): 「魔道具術師は決戦で矢は撃たない。全て自宅に預ける。」 (angband_finale
``no_ammunition``; finale_prep's ammunition step).  The launcher stays worn for its abilities
(owner 2026-11-18 「弓枠は追加能力や耐性のみで評価する」).

Recorded:

* the 99F boards of n1-b life-416 (fixture finale-floor-2108-n1b-416-1123, tests/support/
  finale_416.py): the pack holds 77 クロスボウの矢 and 22 追尾クロスボウの矢 (+6,+8), the worn
  crossbow fires them; at turn 4297349 a hostile (race 151) stands 3 cells away in a line.  A
  fresh process (no expedition mark): 99F alone bars the shot.
* the town-arrival checkpoint of n1-b life-416 (fixture n1b-416-finale-town-1123,
  tests/test_finale_town_1123_recorded.py), rows 0-18 decided and posted as recorded; the pack
  holds the same two stacks of bolts.

DECLARED CONSTRUCTED: the preparation phase's step is set (the recorded visit never entered the
phase: its Restore Mana was short); for the done-check, the recorded board without its ammunition
(the deposit's result); for the pickup, a pile of bolts on the recorded 99F player's cell.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, attack_expectation, finale_prep, me_deep_launcher
from hengbot.model import STORE_HOME, TVAL_BOLT, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from support.town_arrival_fixture import load
from tests.support import finale_416
from tests.support.recorded import EDIT, _policy
from tests.test_finale_town_1123_recorded import FALLBACK_ROW, TOWN, post

SHOT_TURN = 4297349


class FinaleFloorNoShotRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.raw = next(raw for raw in finale_416.boards("finale-floor-2108-n1b-416-1123.jsonl.gz")
                       if raw["turn"] == SHOT_TURN)

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy = _policy(Path(scratch.name), self.monrace)
        self.board = self.policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(self.raw), self.monrace))
        self.policy.prime(self.board)

    def test_the_recorded_bolts_are_not_fired_on_99f(self):
        board, policy = self.board, self.policy
        self.assertEqual(board.dungeon_level, 99)
        self.assertEqual(sorted(item.count for item in board.inventory if item.is_ammo), [22, 77])
        self.assertIsNotNone(policy._equipped_launcher(board))  # the crossbow stays worn
        self.assertFalse(finale_prep.lifted(policy))
        # Before: ("fire", the bolts, "ranged:fire"), the shot weighed against the devices.
        self.assertIsNone(policy._ranged_projectile(board))
        self.assertTrue(angband_finale.no_ammunition(policy, board))
        self.assertIsNone(policy._matching_ammo(board))
        self.assertIsNone(attack_expectation.launcher_usable(policy, board))
        target = next(monster for monster in board.visible_monsters if monster.hostile)
        bolts = next(item for item in board.inventory if item.is_ammo)
        self.assertEqual(attack_expectation.launcher_shot(policy, board, target, bolts), 0.0)

    def test_a_pile_of_bolts_is_not_picked_up_on_99f(self):
        board, policy = self.board, self.policy
        here = board.grid_at(board.player.position)
        # DECLARED CONSTRUCTED (module docstring).
        pile = replace(here, object_tvals=(TVAL_BOLT,), object_count=1)
        self.assertTrue(policy._floor_pile_is_junk(board, pile))

    def test_a_warrior_on_the_same_board_still_fires(self):
        """The rule is the Magic-Eater's."""
        board = replace(self.board, player=replace(self.board.player, class_id=0))
        self.assertFalse(angband_finale.no_ammunition(self.policy, board))
        chosen = self.policy._ranged_projectile(board)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen[0], "fire")


class FinaleTownAmmoDepositRecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(TOWN, Path(scratch.name))
        for recorded, supply in steps[:FALLBACK_ROW]:
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(supply())
            post(policy, recorded["key"])
        self.policy, self.board = policy, steps[FALLBACK_ROW][1]()
        self.ammo = [item for item in self.board.inventory if item.is_ammo]
        self.assertEqual(sorted(item.count for item in self.ammo), [22, 77])

    def at_step(self, step):
        held = finale_prep.phase(self.policy)
        held.step, held.since, held.in_town = step, self.policy._decision_sequence, True

    def test_the_95f_exploration_keeps_its_rounds(self):
        policy, board = self.policy, self.board
        self.assertFalse(angband_finale.no_ammunition(policy, board))
        self.assertGreater(policy._ammo_procurement_target(board), 0)
        for item in self.ammo:
            self.assertEqual(policy._retention_reservation(board, item), item.count)

    def test_the_ammunition_step_deposits_every_round(self):
        policy, board = self.policy, self.board
        self.at_step(finale_prep.AMMO)  # DECLARED CONSTRUCTED
        self.assertTrue(me_deep_launcher.ammo_unneeded(policy, board))
        self.assertEqual(policy._ammo_procurement_target(board), 0)
        for item in self.ammo:
            self.assertEqual(policy._retention_reservation(board, item), 0)
            self.assertTrue(policy._home_deposit_candidate(item, board))
        self.assertTrue(policy._find_home_deposit(board).is_ammo)
        self.assertTrue(finale_prep.ammo_routed(policy, board))
        needs = policy._town_need_candidates(board)
        self.assertIn((STORE_HOME, "deposit"),
                      [(need.store_type, need.category) for need in needs])

    def test_the_step_waits_for_the_deposit_then_takes_the_supplies(self):
        policy, board = self.policy, self.board
        self.at_step(finale_prep.AMMO)  # DECLARED CONSTRUCTED
        rows = angband_finale.readiness(policy, board)
        finale_prep.observe(policy, board, rows)
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.AMMO)
        emptied = replace(board, inventory=[item for item in board.inventory if not item.is_ammo])
        finale_prep.observe(policy, emptied, rows)
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.SUPPLIES)

    def test_a_refused_deposit_stops_the_phase(self):
        policy, board = self.policy, self.board
        self.at_step(finale_prep.AMMO)  # DECLARED CONSTRUCTED
        policy._home_rejected_deposits.add(policy._item_signature(self.ammo[0]))
        self.assertFalse(finale_prep.ammo_routed(policy, board))
        finale_prep.observe(policy, board, angband_finale.readiness(policy, board))
        held = finale_prep.phase(policy)
        self.assertEqual((held.step, held.stopped),
                         (finale_prep.STOPPED, "ammo:deposit-refused"))


if __name__ == "__main__":
    unittest.main()
