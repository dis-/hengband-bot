"""A requirement whose rescues are spent never stops the town end (MAINTAINABILITY.md 2,
departure_leaf_classes, coordinator 2026-11-28).

DECLARED CONSTRUCTED: every board here is the recorded n1-a life-545 stop board of
tests/test_n1a_545_weight_ready_1128_recorded.py (row 15) with its weight waived first
(overweight_departure ``give_way``, the recorded fix's answer), then one leaf made to fail by a
patched predicate or an edited player, and every rescue made to answer nothing
(``departure_rescues.ACTIONS`` all None, the procurement progress None).  The town end
(town_terminal ``town_end_key``) is then asked directly.

* a TOP_UP leaf at its adequacy line departs and records the waiver (``town_end_waived``);
* a TOP_UP leaf below its line and a MUST_HAVE leaf start the 1F mining cycle
  (town:end-mining-cycle, ``SAFER_FALLBACK``);
* a MECHANISM leaf keeps its named stop.

DECLARED HELD OFF (2026-11-28): the speed row's depth-gap gear (depth_gap_gear ``gate_floor`` and
``speed_row``, 478b571d14 and 523c009eb2) is held off for the whole module.  The recorded visit
predates it; with it the bot first takes the Ring of Speed gear from Home at row 4 (an equipment
transaction) and the recorded visit never happens.  Without it every recorded row reproduces.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import departure_leaf_classes, departure_rescues, deep_climb, depth_gap_gear
from hengbot import overweight_departure
from hengbot import town_terminal
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-weight-ready-1128"
STOP_ROW = 15
SURVIVAL = "town:blocked:survival:"
MINING = "town:end-mining-cycle"
WAIVED = "town:repetition-depart:recall"

# leaf -> the patch that fails it on the stop board (the policy method, its constant answer).
FAILED_BY_METHOD = {
    "recall_departure_ready": ("_recall_departure_ready", False),
    "teleport_ready": ("_teleport_ready", False),
    "cure_critical_ready": ("_cure_critical_ready", False),
    "light_ready": ("_light_ready", False),
    "remove_curse_ready": ("_required_remove_curse_kind", "remove-curse"),
    "combat_weapon_ready": ("_combat_weapon_ready", False),
    "teleport_items_safe": ("_teleport_blocked_by_equipment", True),
}



def setUpModule():
    # DECLARED HELD OFF: the depth-gap gear the recorded visit predates (module docstring).
    for name in ("gate_floor", "speed_row"):
        patcher = mock.patch.object(depth_gap_gear, name, lambda *_a, **_k: None)
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class TownEndRequirementLeavesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        for row, (recorded, supply) in enumerate(steps[:STOP_ROW + 1]):
            board = supply()
            if row == STOP_ROW:
                cls.board, cls.checkpoint = board, checkpoint_bytes(policy)
                break
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            post(policy, recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def town_end(self, board=None, *, patches=(), leaf=None):
        """(reason, printed, policy) of the town end on ``board`` with every rescue spent."""
        board = board or self.board
        policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(overweight_departure.give_way(policy, self.board, "constructed"))
        spent = {name: (lambda *_: None) for name in departure_rescues.ACTIONS}
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(departure_rescues.ACTIONS, spent))
            stack.enter_context(mock.patch.object(
                HengbotPolicy, "_town_procurement_progress_key", lambda *_: None))
            for patch in patches:
                stack.enter_context(patch)
            if leaf in FAILED_BY_METHOD:
                name, value = FAILED_BY_METHOD[leaf]
                stack.enter_context(mock.patch.object(HengbotPolicy, name, lambda *_a, **_k: value))
            with contextlib.redirect_stdout(out):
                town_terminal.town_end_key(policy, board)
        return policy.last_reason, out.getvalue(), policy

    def player(self, **changes):
        return dataclasses.replace(self.board, player=dataclasses.replace(self.board.player, **changes))

    def below_line(self, leaf):
        return mock.patch.dict(departure_leaf_classes.TOP_UP, {leaf: lambda *_: False})

    def assert_waived(self, leaf, result):
        reason, out, policy = result
        self.assertFalse(reason.startswith(SURVIVAL), reason)
        self.assertEqual(reason, WAIVED, out[-2000:])
        self.assertIn(leaf, policy._departure_block["town_end_waived"])

    def assert_mines(self, leaf, result):
        reason, out, _ = result
        self.assertFalse(reason.startswith(SURVIVAL), reason)
        self.assertEqual(reason, MINING, out[-2000:])
        self.assertIn(f"<town-end-safer> ", out)
        self.assertIn(leaf, out[out.index("<town-end-safer> "):].splitlines()[0])

    def test_the_waived_weight_board_departs(self):
        reason, _, _ = self.town_end()
        self.assertEqual(reason, WAIVED)

    def test_supply_leaves_depart_at_their_line_and_mine_below_it(self):
        for leaf in ("recall_departure_ready", "teleport_ready", "cure_critical_ready",
                     "light_ready", "remove_curse_ready"):
            with self.subTest(leaf=leaf, side="at the line"):
                self.assert_waived(leaf, self.town_end(leaf=leaf))
            if leaf == "remove_curse_ready":
                continue  # always adequate: the curse was worn on the way in
            with self.subTest(leaf=leaf, side="below the line"):
                self.assert_mines(leaf, self.town_end(leaf=leaf, patches=[self.below_line(leaf)]))

    def test_rest_leaves_depart_at_the_dungeons_rest_line_and_mine_below_it(self):
        max_hp = self.board.player.max_hp
        self.assert_waived("hp_full", self.town_end(self.player(hp=max_hp - 1)))
        self.assert_mines("hp_full", self.town_end(self.player(hp=max_hp // 2)))
        self.assert_waived("temporary_status_clear", self.town_end(self.player(afraid=True)))
        self.assert_mines("temporary_status_clear", self.town_end(self.player(confused=True)))
        max_mp = self.board.player.max_mp
        self.assertGreater(max_mp, 0)
        self.assert_waived("mp_full", self.town_end(self.player(mp=max_mp - 1)))
        self.assert_mines("mp_full", self.town_end(self.player(mp=max_mp - 1),
                                                   patches=[self.below_line("mp_full")]))

    def test_zero_free_slots_with_no_legal_disposal_departs(self):
        full = len(self.board.inventory)
        patches = [mock.patch("hengbot.policy_town.PACK_CAPACITY", full),
                   mock.patch("hengbot.policy_constants.PACK_CAPACITY", full),
                   mock.patch.object(HengbotPolicy, "_overflow_disposal_item", lambda *_: None)]
        self.assert_waived("free_pack_slots_ready", self.town_end(patches=patches))

    def test_must_have_floors_mine_instead_of_stopping(self):
        for leaf in ("combat_weapon_ready", "teleport_items_safe"):
            with self.subTest(leaf=leaf):
                self.assert_mines(leaf, self.town_end(leaf=leaf))
        with self.subTest(leaf="depth_abilities"):
            self.assert_mines("depth_abilities", self.town_end(patches=[mock.patch.object(
                deep_climb, "departure_gaps", lambda *_a, **_k: {"constructed"})]))

    def test_the_weight_floor_mines_when_its_answer_is_spent(self):
        policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.assertTrue(policy._inventory_overweight(self.board))
        spent = {name: (lambda *_: None) for name in departure_rescues.ACTIONS}
        out = io.StringIO()
        with mock.patch.dict(departure_rescues.ACTIONS, spent), \
                contextlib.redirect_stdout(out):
            town_terminal.town_end_key(policy, self.board)
        self.assertEqual(policy.last_reason, MINING)

    def test_a_mechanism_leaf_keeps_its_named_stop(self):
        def inflight(policy):
            policy._store_buy_inflight = {"constructed": True}
        policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        with contextlib.redirect_stdout(io.StringIO()):
            overweight_departure.give_way(policy, self.board, "constructed")
        inflight(policy)
        spent = {name: (lambda *_: None) for name in departure_rescues.ACTIONS}
        with mock.patch.dict(departure_rescues.ACTIONS, spent), \
                mock.patch.object(HengbotPolicy, "_town_procurement_progress_key", lambda *_: None), \
                contextlib.redirect_stdout(io.StringIO()):
            town_terminal.town_end_key(policy, self.board)
        self.assertEqual(policy.last_reason, SURVIVAL + "store_transfer_clear")

    def test_every_requirement_leaf_has_its_answer(self):
        self.assertEqual(departure_leaf_classes.MECHANISM, frozenset({
            "equipment_observed", "home_atomic_withdraw_clear",
            "departure_home_atomic_withdraw_clear", "store_transfer_clear",
            "equipment_transfer_clear"}))
        for leaf in (*departure_leaf_classes.TOP_UP, *departure_leaf_classes.MUST_HAVE):
            self.assertTrue(departure_leaf_classes.safer_fallback((leaf,)), leaf)
        for leaf in departure_leaf_classes.MECHANISM:
            self.assertFalse(departure_leaf_classes.safer_fallback((leaf, "hp_full")), leaf)


if __name__ == "__main__":
    unittest.main()
