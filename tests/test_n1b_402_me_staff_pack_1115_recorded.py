"""The Magic-Eater's stage-2 staff purchase waits for a pack slot, or gives the town up.

n1-b life-402 (Lv8 zombie Magic-Eater, bot_play3 template, build abcba1e76) stopped three times
in 25 s on quest:blocked:me-staff (2026-11-15 17:31:53, 17:32:06, 17:32:16) and was replaced.
In town 3 it bought the Staff of Detect Traps (row 62, 6,994 -> 6,274 gold); 19 of 23 slots were
then used (six spare weapons among them) and stage 2 went on for the 光の杖 (502 gold) on the same
Magic shelf.  The page purchase is refused below the four-slot floor (policy_shop
``_store_purchase_fits_pack``), and the inventory pass that makes room never interrupts a quest
return (town_pack_headroom.eligible: the Q14 prepare-return owned town 3), so nothing made the
slot; the sequence walked into the Magic shop and out again (shop:approach,
shop:observe-and-leave) until its no-progress check stopped it.  Not the fare of n1-c life-212
(6,274 gold pays both).

Fix: the buy phase asks the pack first (me_staff_sequence ``_pack_takes``): the town's inventory
pass starts and the sequence waits while it makes the slot (me-staff:await-pack-room); without a
pass an away town is given up, and the round that closes there is answered at once (the Tower
trip); the Outpost stops by name (pack-full-no-room).

Recorded: the capture's town-arrival checkpoint and journal rows 0-69
(tests/extract_n1b_402_me_staff_pack_1115_fixture.py), replayed through the public
``choose_key``; the row-64 key is posted through the production executor port.  DECLARED FORCED:
row 33, whose recorded in-store buy the fresh arbiter retires on this replay (main d89dedaffb
alike), is posted as recorded.  DECLARED CONSTRUCTED: for the pass case, no quest return owning
the town (``_fixed_quest_prepare_return_required`` False).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import me_staff_sequence, town_pack_headroom
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load
from tests.support import recorded as harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-402-me-staff-pack-1115"
BOARD = 64  # the first board after the trap staff's purchase (the live shop:travel:await-entry)
FORCED = {33}
TOWN = 3
SV_STAFF_LITE = 8


class N1b402MeStaffPack1115RecordedTest(harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def replay(self):
        """(policy, the rows) after rows 0-63 posted as recorded (decided as recorded but FORCED)."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        for recorded, supply in rows[:BOARD]:
            board = supply()
            key = policy.choose_key(board)
            if recorded["row"] not in FORCED:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
        self.assertEqual(rows[BOARD][0]["reason"], "shop:travel:await-entry")
        return policy, rows

    def post_macro(self, policy, raw, key):
        """RecordedHarness.post with the headless terminal's key queue (1024 keys,
        headless-term.cpp:41): the fake game's default 32 refuses a travel macro."""
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

    def test_the_slot_no_pass_can_make_gives_town_3_up(self):
        policy, rows = self.replay()
        board = rows[BOARD][1]()
        self.assertEqual((policy._effective_town_id(board), board.player.gold, len(board.inventory)),
                         (TOWN, 6274, 19))
        offer = me_staff_sequence.offers(policy, board)[SV_STAFF_LITE]
        self.assertFalse(me_staff_sequence._pack_takes(policy, board, offer[1]))
        self.assertTrue(policy._fixed_quest_prepare_return_required(board))
        self.assertFalse(town_pack_headroom.eligible(policy, board))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")
        self.assertIn(TOWN, me_staff_sequence.state(policy).searched_towns)
        entry = self.journal[BOARD]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        self.assertEqual("".join(self.post_macro(policy, raw, key)), key)

    def test_with_a_pass_the_sequence_waits_for_the_slot(self):
        policy, rows = self.replay()
        # DECLARED CONSTRUCTED: no quest return owns the town, so the inventory pass may run.
        with mock.patch.object(HengbotPolicy, "_fixed_quest_prepare_return_required",
                               lambda self, snapshot: False):
            board = rows[BOARD][1]()
            self.assertTrue(town_pack_headroom.room_can_be_made(policy, board))
            policy.choose_key(board)
            self.assertTrue(town_pack_headroom.organizing(policy, board))
            self.assertNotIn(TOWN, me_staff_sequence.state(policy).searched_towns)
            self.assertNotIn(policy.last_reason, {"shop:approach", "shop:travel:await-entry"})


if __name__ == "__main__":
    unittest.main()
