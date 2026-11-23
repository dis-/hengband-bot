"""n1-a life-535: the Home cap tidy left the Alchemist's page before its Teleportation buy.

n1-a life-535 (Warrior Lv48, 41,580 gold) was stopped in town by
``town:blocked:survival:teleport_ready`` (2026-11-23 13:12:41, turn 7391125) with 13 of the 15
Teleportation scrolls.  Not a stock-out nor the gold: the Alchemist's shelf held 27 at 56 gold.
Its first entry (13:12:35) bought the Word of Recall and deferred the Teleportation to the stale
Home catalogue (shop:home-first-yields-to-current-visit); the Home scan found none there, and the
re-entry (13:12:37, decision 9604) was left on its first page by the Home cap tidy's first take
(owner 2026-11-19 「200件（空き40）」, home:cap-tidy-withdraw, the Home at 202 stacks).  The
Alchemist then counted as tried, no rescue revisits a tried supplier whose page sells the ware,
and the town end named the stop.

The relief yields to the page's departure-blocking purchase (policy_home
``_home_full_relief_yields_to_page_purchase``): the re-entry buys the two scrolls first.

Recorded: the 13:12:22 town-arrival checkpoint of the incident capture
(tests/fixtures/n1a-535-teleport-ready-1123): its first 23 rows replay as recorded, and the
24th (the Alchemist's re-entry page) is decided again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-teleport-ready-1123"
REPLAYED = 23
TELEPORT = (70, 9)


class TeleportReadyCapTidyTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
            cls.town = replay_window("n1a-535-teleport-ready", cls.policy, iter(steps[:REPLAYED]))
        cls.row, supply = steps[REPLAYED]
        cls.board = supply()
        cls.yields = cls.policy._home_full_relief_yields_to_page_purchase(cls.board)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.key = cls.policy.choose_key(cls.board)
        cls.reason = cls.policy.last_reason

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_recorded_boards(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, REPLAYED)
        # Recorded: the re-entry page was left by the cap tidy's first take.
        self.assertEqual((self.row["key"], self.row["reason"]),
                         ("\x1b", "home:cap-tidy-withdraw"))
        board = self.board
        self.assertEqual(board.store.store_type, 4)  # the Alchemist
        self.assertEqual(board.player.gold, 41580)
        shelf = [(item.letter, item.count, item.price) for item in board.store.items
                 if (item.tval, item.sval) == TELEPORT]
        self.assertEqual(shelf, [("c", 27, 56)])
        carried = sum(item.count for item in board.inventory
                      if (item.tval, item.sval) == TELEPORT)
        self.assertEqual(carried, 13)

    def test_the_page_buys_the_teleportation_before_the_tidy(self):
        from hengbot import home_cap

        # The Home stood over its cap: the tidy is due on this visit.
        self.assertEqual(home_cap.stock_count(self.policy, self.board), 202)
        self.assertTrue(self.yields)
        self.assertEqual((self.key, self.reason), ("pc2\r\r", "shop:in-store-buy"))


if __name__ == "__main__":
    unittest.main()
