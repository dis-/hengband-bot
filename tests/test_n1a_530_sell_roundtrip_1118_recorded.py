"""n1-a life-530 2026-11-18 03:53:26, town:blocked:stage-deadline:sell (bot fa6471d0f).

Resumed after the full-Home relief learnt to sell its clearly useless shelf stock as a round
trip (tests/test_n1a_530_overweight_relief_1118_recorded.py), the Lv47 warrior took stacks of
plain (+0,+0) crossbow bolts out of its full Home and sold them at the Weaponsmith, each
under the same name ``クロスボウの矢 (1d5) (+0,+0) (65/shot 94/turn) {@1}``: 99 sold on row
44, 99 on row 71.  On row 84 the third 99 were refused before any key was sent
(``shop:unsellable-home-full-surplus-sale-refused``): ``_store_sell_key`` counts an attempt
as a repeat of the previous one when the same name is offered with no fewer carried, and
after three it marks the ware unsellable and the store refused.  The relief observed each
sale (its ware left the pack) but never ended that count, unlike the overweight-surplus
sale, which clears it on its observed effect.  Held unsellable, the bolts went from store to
store (``shop:unsellable-leave`` at the General Store, rows 90-104) until the sell stage's
deadline.  The game's Weaponsmith and General Store both buy bolts (service-checker.cpp
check_store_weapon, check_store_general); the store was not refusing anything.

The relief's observed sale now ends the store attempts.

Recorded: the incident capture's town-arrival checkpoint and its first 85 journal rows
(tests/extract_n1a_530_sell_roundtrip_1118_fixture.py); rows 44, 71 and 84 are the recorded
Weaponsmith boards with the taken 99 {@1} bolts, rows 46 and 73 the outside boards after the
first two sales.

DECLARED CONSTRUCTED: the replay of this capture parts from the record at row 18 (the
equipment transaction reads the loadout report the capture did not copy), so the relief's
state on each sale board is set as the live bot held it (the taken 99 {@1} bolts its sale
ware, bound for the Weaponsmith), and the boards are decided through the relief's own
producers (``_store_sell_key`` at the store, ``_home_full_relief_key`` outside) instead of
choose_key.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-sell-roundtrip-1118"
ROUND_TRIPS = ((44, 46), (71, 73), (84, None))
STORE_WEAPONSMITH = 2
TVAL_BOLT = 18
SALE_KEY = "d199\ry"
REFUSED = "shop:unsellable-home-full-surplus-sale-refused"


def taken_bolts(board):
    return next(item for item in board.inventory
                if item.tval == TVAL_BOLT and item.inscription == "@1")


class N1a530SellRoundTrip1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        rows = {row for pair in ROUND_TRIPS for row in pair if row is not None}
        cls.boards = {row: supply() for row, (_, supply) in enumerate(steps) if row in rows}

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def bind_relief(self, board):
        """The relief as the live bot held it: the taken 99 {@1} bolts its sale ware."""
        policy = self.policy
        ware = taken_bolts(board)
        signature = policy._item_signature(ware)
        identity = policy._sale_item_identity(ware)
        carried = sum(item.count for item in board.inventory
                      if policy._sale_item_identity(item) == identity)
        policy._home_full_relief = {
            "deposits": (), "remaining": 2, "town": 0, "identify_cap_skip_fingerprint": {},
            "sale": (signature, STORE_WEAPONSMITH, carried - ware.count), "withdrawn": True,
            "mode": "sale", "useless": signature, "taken": (signature, ware.count),
            "stock_count": 500,
        }
        policy._batch_sell_pending = None
        return ware

    def test_the_recorded_visit_refused_the_third_round_trip(self):
        for row, _ in ROUND_TRIPS:
            board = self.boards[row]
            self.assertEqual(board.store.store_type, STORE_WEAPONSMITH)
            self.assertEqual(taken_bolts(board).count, 99)
        self.assertEqual([(self.journal[row]["key"], self.journal[row]["reason"])
                          for row, _ in ROUND_TRIPS],
                         [(SALE_KEY, "shop:in-store-sell")] * 2 + [("\x1b", REFUSED)])
        signatures = {self.policy._item_signature(taken_bolts(self.boards[row]))
                      for row, _ in ROUND_TRIPS}
        self.assertEqual(len(signatures), 1)

    def test_each_round_trip_is_sold(self):
        policy = self.policy
        decided = []
        for sale_row, after_row in ROUND_TRIPS:
            board = self.boards[sale_row]
            ware = self.bind_relief(board)
            key = policy._store_sell_key(board, ware, "shop:sell-home-full-surplus",
                                         rejected_reason=REFUSED)
            decided.append((key, policy.last_reason))
            if after_row is not None:
                # Outside after the sale: the relief observes its ware gone.
                policy._home_full_relief_key(self.boards[after_row])
                self.assertIsNone(policy._home_full_relief["sale"])
                self.assertIsNone(policy._store_sell_attempt)
        self.assertEqual(decided, [(SALE_KEY, "shop:one-shot-sale-compose")] * 3)
        self.assertNotIn(policy._item_signature(taken_bolts(self.boards[84])),
                         policy._unsellable_items)
        self.assertNotIn(STORE_WEAPONSMITH, policy._store_sale_refused)


if __name__ == "__main__":
    unittest.main()
