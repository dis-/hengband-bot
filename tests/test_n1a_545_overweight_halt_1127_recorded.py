"""An over-the-limit pack with nothing legal left departs instead of stopping (n1-a life-545, MAINTAINABILITY.md 2).

Recorded (tests/extract_n1a_545_overweight_halt_1127_fixture.py, ``n1a-545-overweight-halt-1127``):
the town-arrival checkpoint of 2026-11-27 10:28:11 (Amberite Rogue CL33, STR index 24, gold 337).
Home's three passes of the visit were spent (identification takes and the equipment transaction's
deposits), row 97 bought ten Treasure Detection scrolls for the mining kit, and row 98 stopped
under town:blocked:overweight-home-full-no-legal-relief: 1646 tenths of a pound on a 1600 limit
(adj_str_wgt[24] 32 x 50, player-status.cpp:2556-2563), Home 146 of 240.  The relief had picked
the 10 unreserved iron shots (82 carried, 72 kept by the ammunition plan; 50 tenths >= the 46
over) for the Weapon Smith, but the need router's overweight-home-unreachable (the Home route's
own terminal) refused the walk.  The fix sells them; failing that, the load departs: 46 over is
no speed at all (player-speed.cpp:43-51, one speed per 320 over).  Every row before the one
decided is replayed through the public ``choose_key`` and posts the recorded key; the row-9
character dump is restored at row 10 as the live game wrote it, so the replay matches every
recorded row (full state).

DECLARED CONSTRUCTED: ``test_without_a_walk_to_a_buyer_the_load_departs`` refuses the walk to the
buyer, and ``test_a_slowing_load_sheds_the_cheapest_reserved_weight`` adds worn weight.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-overweight-halt-1127"
STOP_ROW = 98
STOP = ("7", "town:blocked:overweight-home-full-no-legal-relief")
DUMP_ROW = 10
SHOTS = "s"
WEAPON_SMITH = 2


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class OverweightHalt545RecordedTest(unittest.TestCase):
    def replay(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.assertEqual((journal[STOP_ROW]["key"], journal[STOP_ROW]["reason"]), STOP)
        for recorded, supply in steps[:STOP_ROW]:
            if recorded["row"] == DUMP_ROW:
                Path(policy._character_dump_path).write_bytes(
                    lzma.decompress((FIXTURE / "character-dump-row9.txt.xz").read_bytes()))
            key, reason = decide(policy, supply())
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
            post(policy, recorded["key"])
        board = steps[STOP_ROW][1]()
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1646, 1600))
        self.assertEqual(policy._town_blocked_reason, "overweight-home-unreachable")
        return policy, board

    def test_the_unreserved_shots_go_to_the_weapon_smith(self):
        policy, board = self.replay()
        key, reason = decide(policy, board)
        self.assertNotEqual((key, reason), STOP)
        self.assertEqual(reason, "shop:travel")
        self.assertTrue(key.startswith("\x1b`"), key)
        pending = policy._overweight_surplus_disposal["pending"]
        self.assertEqual((pending["count"], pending["mode"]), (10, "sale"))
        self.assertEqual(pending["signature"][1:], (16, 1))
        self.assertEqual(policy._shopping_approach_store_type, WEAPON_SMITH)

    def test_without_a_walk_to_a_buyer_the_load_departs(self):
        from hengbot import overweight_departure
        policy, board = self.replay()
        original = HengbotPolicy._shopping_approach_step

        def refuse_sale(self, snapshot, store_type=None, **kwargs):
            if kwargs.get("requester") == "shop-sell":
                return None
            return original(self, snapshot, store_type, **kwargs)

        with mock.patch.object(HengbotPolicy, "_shopping_approach_step", refuse_sale):
            key, reason = decide(policy, board)
        self.assertNotIn("blocked", reason)
        waiver = getattr(policy, overweight_departure.NAME)
        self.assertEqual((waiver["weight"], waiver["limit"], waiver["allowed"], waiver["cause"]),
                         (1646, 1600, 1919, "sale-store-unreachable"))
        self.assertFalse(policy._inventory_overweight(board))
        self.assertIsNone(policy._overweight_surplus_disposal)
        self.assertTrue(policy._town_departure_conjuncts(board, commit=False)["inventory_weight_ready"])

    def test_a_slowing_load_sheds_the_cheapest_reserved_weight(self):
        from hengbot import overweight_departure
        policy, board = self.replay()
        # CONSTRUCTED: 1000 tenths more worn weight: 2646 costs three speed (a step is 320 over
        # 1600).  The ammunition plan then keeps no shot (all 82, 410, are surplus), which leaves
        # 2236, and the reserved rows shed toward the tolerated 1919.
        heavy = replace(board, equipment=tuple(
            replace(item, weight=item.weight + 1000) if item.slot == "body" else item
            for item in board.equipment))
        self.assertFalse(overweight_departure.tolerated(policy, heavy))
        surplus = list(policy._weight_relief_selection(heavy).surplus)
        self.assertEqual([(entry[2].slot, entry[3]) for entry in surplus], [(SHOTS, 82)])
        shed = overweight_departure.shed_candidates(policy, heavy, surplus)
        removed = sum(entry[2].weight * entry[3] for entry in [*surplus, *shed])
        self.assertTrue(shed)
        # Short of the 727 needed: the departure supplies (food, cure, teleport, recall) and the
        # cast books stay, and what is left departs (give_way force, "nothing-to-shed").
        self.assertEqual(removed, 703)
        self.assertEqual({item.slot for item in heavy.inventory}
                         - {entry[2].slot for entry in [*surplus, *shed]},
                         {"a", "b", "c", "d", "g", "j", "k"})
        # The two cast books stay; the cheapest weight goes first (Light, then Treasure Detection).
        self.assertFalse({"a", "b"} & {entry[2].slot for entry in shed})
        self.assertEqual([entry[2].slot for entry in shed][:2], ["m", "n"])
        rates = [entry[0] / entry[3] / entry[2].weight for entry in shed]
        self.assertEqual(rates, sorted(rates))
        key, reason = decide(policy, heavy)
        self.assertNotIn("blocked", reason)


if __name__ == "__main__":
    unittest.main()
