"""The ring the Ring of Levitation replaced goes back on after the Zul trip.

Owner 2026-11-08, question 「ズルへの旅で浮遊の指輪をはめる時、外した指輪は旅の後どうしますか？」:
「旅の後に付け直す」 -- 外した指輪は旅の間持ち歩き、ズルで治療を終えて町に戻ったら付け直す
（浮遊の指輪は外す）.  ``_wear_key`` put the levitation ring over the sub ring with
nothing remembered and the replaced ring had no retention reservation (n1-c: the Ring of
Resist Chaos could be sold or stored).

Now the replaced ring is remembered when the levitation ring goes on, kept in the pack
for the trip, and put back in its slot once the trip is over and the character is in a
town other than Zul; the levitation ring then follows the ordinary unused-gear rules.

Recorded board: n1-b life-345 08:13:40, the Outpost after the recall (turn 1744015,
tests/fixtures/n1b-343-345-1108/zul.tar.xz): the Ring of Levitation worn in the sub ring
slot, the Ring of Lightning [+10] {r電} in the pack (slot j).
DECLARED CONSTRUCTED: the memory of the replaced ring (that the Ring of Lightning came
off the sub ring for the levitation ring), the finished trip (closed for this stay), and
the board moved after the restart's turn; the Ring of Damage board for the wear.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import time
import unittest

from hengbot import zul_trip
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from tests.test_classA_observed_input import recorded
from tests.support.recorded import FaithfulHookGame, command_screen
from tests import test_zul_ring_replace_1108 as replace_pins
# The module, not the class: a TestCase bound here would run its tests again.
from tests import test_n1b_345_zul_1108_recorded as zul_pins

OUTPOST_TURN = 1744015
LIGHTNING = "電撃の指輪 [+10] {r電}"


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

    def test_the_wear_remembers_the_replaced_ring(self):
        policy, raw, _board, ring = self.outpost()
        before = parse_snapshot(self.swapped(raw), policy._monrace_knowledge)
        levitation = next(item for item in before.inventory if zul_trip.is_levitation_item(item))
        key = zul_trip._wear_key(policy, before, levitation)
        self.assertEqual(key, f"w{levitation.slot})")
        self.assertEqual(zul_trip.replaced_ring(policy), (policy._item_signature(ring), "sub_ring"))
        # Kept in the pack for the trip (no sale, deposit or destruction).
        self.assertTrue(zul_trip.retains_replaced_ring(policy, ring))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        carried = next(item for item in board.inventory if item.name == LIGHTNING)
        self.assertEqual(policy._retention_reservation_baseline_detail(board, carried),
                         (1, "zul-trip:replaced-ring"))

    def test_after_the_trip_the_replaced_ring_goes_back_on(self):
        policy, raw, board, ring = self.outpost()
        policy._zul_replaced_ring = (policy._item_signature(ring), "sub_ring")
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
        # Once it is worn, the memory ends and the levitation ring is ordinary gear.
        worn = self.swapped(raw)
        worn["turn"] += 10
        after = parse_snapshot(worn, policy._monrace_knowledge)
        policy.confirm_key_posted(key)
        self.decide(policy, after)
        self.assertIsNone(zul_trip.replaced_ring(policy))
        self.assertNotEqual(policy.last_reason, zul_trip.REWEAR_REASON)

    def test_no_rewear_while_the_trip_is_under_way(self):
        policy, _raw, board, ring = self.outpost()
        policy._zul_replaced_ring = (policy._item_signature(ring), "sub_ring")
        policy._zul_trip = zul_trip.ZulTrip(active=True, start_town=0, curable=(1,))
        self.assertIsNone(zul_trip.rewear_key(policy, board))


if __name__ == "__main__":
    unittest.main()
