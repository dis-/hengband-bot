"""The ring the Ring of Levitation replaced goes back on after the Zul trip.

Owner 2026-11-08, question 「ズルへの旅で浮遊の指輪をはめる時、外した指輪は旅の後どうしますか？」:
「旅の後に付け直す」 -- 外した指輪は旅の間持ち歩き、ズルで治療を終えて町に戻ったら付け直す
（浮遊の指輪は外す）.  ``_wear_key`` put the levitation ring over the sub ring with
nothing remembered and the replaced ring had no retention reservation (n1-c: the Ring of
Resist Chaos could be sold or stored).

Now the levitation ring borrows its ring slot (slot_lending ``zul-levitation``); the target
loadout's ring for that slot is kept in the pack for the trip and goes back in the slot once the
trip is over and the character is in a town other than Zul; the levitation ring then follows the
ordinary unused-gear rules.  Equipment review E5 (owner 2026-11-22 Q6 「一時的な付け替え（採掘・
クエスト・ズル等）の後はいつも目指す装備の武器に戻す。各系統で元の武器を覚えるのをやめる」): the
slot returns to the target's ring, not to a ring remembered when the levitation ring went on.

Recorded board: n1-b life-345 08:13:40, the Outpost after the recall (turn 1744015,
tests/fixtures/n1b-343-345-1108/zul.tar.xz): the Ring of Levitation worn in the sub ring
slot, the Ring of Lightning [+10] {r電} in the pack (slot j).
DECLARED CONSTRUCTED: the lending of the sub ring slot (the levitation ring went on it), the
target loadout naming the Ring of Lightning in the sub ring (the search's), the finished trip
(closed for this stay), and the board moved after the restart's turn; the Ring of Damage board for
the wear; a target naming another ring for the slot.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import time
from dataclasses import replace
import unittest

from hengbot import equipment_target, slot_lending, zul_trip
from hengbot.equipment_optimizer import (
    EvaluatedLoadout, Loadout, LoadoutMetrics, OptimizationResult, OwnedEquipment,
)
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from tests.test_classA_observed_input import recorded
from tests.support.recorded import FaithfulHookGame, command_screen
from tests import test_zul_ring_replace_1108 as replace_pins
# The module, not the class: a TestCase bound here would run its tests again.
from tests import test_n1b_345_zul_1108_recorded as zul_pins

OUTPOST_TURN = 1744015
LIGHTNING = "電撃の指輪 [+10] {r電}"


def install_target(policy, slots):
    """DECLARED CONSTRUCTED: the loadout an earlier town visit fixed (equipment_target, stage E3)
    naming ``slots`` ((slot, item) pairs); the recorded checkpoint (11-08) predates the visit
    target, and the town's own events clear the stored search target."""
    loadout = Loadout(tuple((slot, OwnedEquipment(f"target-{slot}", item, "pack"))
                            for slot, item in slots), "one_handed")
    result = OptimizationResult(
        best=EvaluatedLoadout(loadout, LoadoutMetrics(1.0, 1.0, 1.0)),
        alternatives=(), pareto_frontier=(), dominated_item_ids=frozenset(),
        combinations_considered=1, combinations_evaluated=1,
        invalid_combinations=0, elapsed_seconds=0.0, timed_out=False,
        incomplete_item_ids=frozenset())
    equipment_target.fix_visit_target(policy, "an-earlier-visit", (), (None, None, None, (False, False)),
                                      result)


class ZulRingRewearTest(zul_pins.ZulRecordedTest):
    # The parent's pins run in their own module.
    test_the_entry_board_walks_over_the_mountains_to_the_tower = None
    test_the_walk_reaches_the_tower_and_pays_the_cure = None
    test_a_tower_out_of_reach_closes_the_trip_by_name = None
    test_the_stranded_board_takes_the_cure_walk = None
    test_the_stranded_board_without_a_cure_walks_out = None
    test_the_dark_ambush_heads_for_the_edge_instead_of_recall = None
    test_no_recall_is_read_as_a_stuck_escape_on_the_trip = None

    @staticmethod
    def decide(policy, board):
        """choose_key past the reads a new town visit asks first (no game time)."""
        for _ in range(6):
            key = policy.choose_key(board)
            if not policy.last_reason.startswith(("home:request-knowledge", "me-staff:read-powers")):
                return key
            policy.confirm_key_posted(key)
        return key

    def outpost(self):
        policy, _recorded, _steps, _row = self.ready(mutation=False)
        raw = self.at_restart(policy, self.recorded(OUTPOST_TURN))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        ring = next(item for item in board.inventory if item.name == LIGHTNING)
        worn = {piece.slot: piece.name for piece in board.equipment}
        self.assertTrue(worn["sub_ring"].startswith("浮遊の指輪"))
        return policy, raw, board, ring

    @staticmethod
    def swapped(raw):
        """DECLARED CONSTRUCTED: the Lightning ring worn, the levitation ring in the pack."""
        raw = copy.deepcopy(raw)
        lev = next(row for row in raw["equipment"] if row["slot"] == "sub_ring")
        ring_row = next(row for row in raw["inventory"] if row["name"] == LIGHTNING)
        raw["inventory"] = [dict(lev, slot=ring_row["slot"]) if row is ring_row else row
                            for row in raw["inventory"]]
        raw["equipment"] = [dict(ring_row, slot="sub_ring") if row is lev else row
                            for row in raw["equipment"]]
        return raw

    def test_the_wear_lends_the_ring_slot(self):
        policy, raw, _board, ring = self.outpost()
        install_target(policy, (("sub_ring", ring),))
        before = parse_snapshot(self.swapped(raw), policy._monrace_knowledge)
        levitation = next(item for item in before.inventory if zul_trip.is_levitation_item(item))
        key = zul_trip._wear_key(policy, before, levitation)
        self.assertEqual(key, f"w{levitation.slot})")
        self.assertEqual(slot_lending.lent_slots(policy, slot_lending.ZUL_LEVITATION), ("sub_ring",))
        self.assertFalse(hasattr(policy, "_zul_replaced_ring"))
        # The target's ring for the slot is kept in the pack for the trip.
        self.assertTrue(zul_trip.retains_returning_ring(policy, ring))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        carried = next(item for item in board.inventory if item.name == LIGHTNING)
        self.assertEqual(policy._retention_reservation_baseline_detail(board, carried),
                         (1, "zul-trip:replaced-ring"))

    def test_after_the_trip_the_target_ring_goes_back_on(self):
        policy, raw, board, ring = self.outpost()
        slot_lending.lend(policy, "sub_ring", slot_lending.ZUL_LEVITATION)
        install_target(policy, (("sub_ring", ring),))
        key = self.decide(policy, board)
        self.assertEqual(policy.last_reason, zul_trip.REWEAR_REASON, key)
        # Both ring slots filled: wield pack slot j, ')' at 「どちらの指輪と取り替えますか?」.
        self.assertEqual(key, f"w{ring.slot})")
        # Recorded screens: the wield chooser and the replace-ring chooser of
        # n1-c life-160 (tests/fixtures/zul-ring-replace-20261107.json.gz).
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [recorded("live-screen-cap-15-home-wield-w.json"),
                        replace_pins.capture()["replace_ring_screen"],
                        command_screen(raw["turn"] + 10)]
        game.states = [copy.deepcopy(raw) for _screen in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        _send_new_decision_key(port, "zul-ring-rewear", key, None, set(), in_store=False,
                               decision={"sequence": policy._decision_sequence,
                                         "reason": policy.last_reason},
                               snapshot=board, posting_contract=None)
        self.assertEqual(game.accepted, ["w", ring.slot, ")"])
        self.assertEqual(port.last_result.outcome, "completed")
        # Once it is worn, the lending ends and the levitation ring is ordinary gear.
        worn = self.swapped(raw)
        worn["turn"] += 10
        after = parse_snapshot(worn, policy._monrace_knowledge)
        policy.confirm_key_posted(key)
        self.decide(policy, after)
        self.assertEqual(slot_lending.lent_slots(policy, slot_lending.ZUL_LEVITATION), ())
        self.assertNotEqual(policy.last_reason, zul_trip.REWEAR_REASON)

    def test_after_the_trip_the_slot_returns_to_the_target_not_the_replaced_ring(self):
        # Owner 2026-11-22 Q6: the target loadout names another ring for the sub ring (DECLARED
        # CONSTRUCTED: a ring the search preferred, not carried): the replaced Ring of Lightning is
        # not put back -- before E5 the remembered ring was -- and the lending ends with the slot
        # left to the visit's swap.
        policy, _raw, board, ring = self.outpost()
        other = replace(ring, name="力の指輪 <+3>", pval=3)
        slot_lending.lend(policy, "sub_ring", slot_lending.ZUL_LEVITATION)
        install_target(policy, (("sub_ring", other),))
        self.assertFalse(zul_trip.retains_returning_ring(policy, ring))
        self.decide(policy, board)
        self.assertNotEqual(policy.last_reason, zul_trip.REWEAR_REASON)
        self.assertEqual(slot_lending.lent_slots(policy, slot_lending.ZUL_LEVITATION), ())

    def test_no_rewear_while_the_trip_is_under_way(self):
        policy, _raw, board, ring = self.outpost()
        slot_lending.lend(policy, "sub_ring", slot_lending.ZUL_LEVITATION)
        install_target(policy, (("sub_ring", ring),))
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=0, curable=(1,))
        self.assertIsNone(zul_trip.rewear_key(policy, board))


if __name__ == "__main__":
    unittest.main()
