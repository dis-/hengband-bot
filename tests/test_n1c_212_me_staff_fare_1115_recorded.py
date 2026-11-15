"""The Magic-Eater's stage-2 staff purchase keeps the fare home, as the store composer does.

n1-c life-212 (Lv8 zombie Magic-Eater, build 138f619e1) stopped three times in 25 s on
quest:blocked:me-staff (2026-11-15 14:12:06, 14:12:18, 14:12:29) and was replaced.  The staff
sequence had travelled to Morivant for the Tower (row 5, 1,641 -> 1,141 gold) with 周辺感知 and
邪悪存在感知 carried; Morivant's Magic shop sold ドア/階段感知の杖 (794 gold), still needed, so the
buy round reopened (``_phase`` buy) and the sequence walked to the shop.  Away from the Outpost
the store composer keeps the inn fare home (item_reservation.store_item_key,
``_outpost_return_fare`` 500): 1,141 - 500 < 794 composed no key, the outside page stepped off
the entrance (shop:buy-device-food '9') and the next board walked back in (shop:approach,
shop:observe-and-leave), until the sequence's no-progress check stopped it.

Fix (me_staff_sequence ``_spendable_gold``): the page purchase and the buy phase weigh the gold
less the fare; an away town that cannot pay is given up, and given up at Morivant the round that
closes is the Tower's at once (recharge or absorb) instead of the fare home and back.

Recorded: the capture's town-arrival checkpoint and journal rows 0-9
(tests/extract_n1c_212_me_staff_fare_1115_fixture.py), replayed through the public
``choose_key``; the row-8 key is posted through the production executor port.  DECLARED
CONSTRUCTED: the gold raised to pay the staff and the fare, for the control.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.model import STORE_MAGIC
from hengbot.policy_constants import TOWN_TELEPORT_COST
from support.town_arrival_fixture import load
from tests.support import recorded as harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-212-me-staff-fare-1115"
MORIVANT = 2
SV_STAFF_DETECT_DOOR = 13
BOARD = 8  # the first Morivant board after its Magic page (the live shop:buy-device-food '9')


class N1c212MeStaffFare1115RecordedTest(harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def replay(self, edit=None):
        """(policy, the row-8 board, its key) after rows 0-7 decided as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        for recorded, supply in rows[:BOARD]:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            policy.confirm_key_posted(key)
        board = rows[BOARD][1]()
        if edit is not None:
            board = edit(board)
        self.assertEqual(rows[BOARD][0]["reason"], "shop:buy-device-food")
        return policy, board, policy.choose_key(board)

    def post_macro(self, policy, raw, key):
        """RecordedHarness.post with the game's key queue: the headless terminal holds
        BOT_CONTROL_MAX_KEYS + 1 = 1024 keys (headless-term.cpp:41, bot-control-server.h:19),
        the fake game's default 32 would refuse the 40-key travel macro."""
        game = harness.FaithfulHookGame()
        game.capacity = 1024
        game.state = raw
        game.screen = harness.command_screen(raw["turn"])
        following = self.later(raw)
        game.screens = [harness.command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = harness._ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         harness.SendResult.SENT, port.last_result.reason)
        return game.accepted

    def test_the_live_board_offers_a_staff_the_fare_leaves_unpaid(self):
        policy, board, _key = self.replay()
        self.assertEqual(policy._effective_town_id(board), MORIVANT)
        self.assertEqual(policy._outpost_return_fare(board), TOWN_TELEPORT_COST)
        offer = me_staff_sequence.offers(policy, board)[SV_STAFF_DETECT_DOOR]
        self.assertEqual((offer[0], offer[1].price, board.player.gold), (STORE_MAGIC, 794, 1141))
        self.assertLess(me_staff_sequence._spendable_gold(policy, board), offer[1].price)
        self.assertIsNone(me_staff_sequence._page_purchase(
            policy, replace(board, store=policy._town_supplier_stock[STORE_MAGIC])))

    def test_morivant_is_given_up_and_the_tower_is_walked_to(self):
        policy, board, key = self.replay()
        self.assertEqual(policy.last_reason, "me-staff:approach-tower")
        self.assertIn(MORIVANT, me_staff_sequence.state(policy).searched_towns)
        self.assertEqual(me_staff_sequence._phase(policy, board), "recharge")
        self.assertTrue(key.startswith("\x1b`n"), key)
        # Through the production executor: the travel macro is posted whole.
        entry = self.journal[BOARD]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        self.assertEqual("".join(self.post_macro(policy, raw, key)), key)

    def test_with_the_fare_paid_the_staff_is_still_bought(self):
        def richer(board):
            # DECLARED CONSTRUCTED: enough gold for the staff and the fare home.
            return replace(board, player=replace(board.player, gold=794 + TOWN_TELEPORT_COST + 300))
        policy, board, _key = self.replay(richer)
        self.assertNotEqual(policy.last_reason, "me-staff:approach-tower")
        # Morivant was looked at on an earlier round (turn 295149); this board does not give it up.
        self.assertEqual(me_staff_sequence.state(policy).searched_towns[MORIVANT], 295149)
        self.assertEqual(me_staff_sequence._phase(policy, board), "buy")
        self.assertEqual(policy.last_reason, "shop:one-shot-buy")  # the outside page composes it


if __name__ == "__main__":
    unittest.main()
