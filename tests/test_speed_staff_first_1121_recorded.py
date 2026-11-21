"""A Magic-Eater's first Staff of Speed is bought first on whatever page shelves it.

Owner 2026-11-21 (verbatim): 「スピードの杖の一本目は最優先にする」 (bm_destruction_fund's
speed-staff row of PRIORITY_WARES).

Recorded: n1-b life-413's town visit of 2026-11-21 23:06:50 (Lv31 Magic-Eater, no Speed
absorbed, none carried or in the Home; tests/fixtures/n1b-413-magic-shop-1121, 15 journal rows).
Row 13 is the Black Market's page (52 rows, 6,625 gold); live it bought ``px``.  Rows 0-2
replay as recorded; from row 3 the Short Bow of Robin Hood the per-turn launcher comparison
takes from the Home (a165b1caf8) opens an equipment transaction the recorded build did not, so
the recorded keys are delivered row by row as the game received them and the page's purchase
is read from the shop's selector (``_next_purchase``).

DECLARED CONSTRUCTED: row 13's board with a Staff of Speed shelved in place of the page's 光の杖
row (letter B: sval 22, 10 charges, 30,000 gold) and 200,000 gold;
the same with the Speed power absorbed (the absorption record), and with a Staff of Speed in the
pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import bm_destruction_fund, me_capability
from hengbot.model import STORE_BLACK, SV_STAFF_SPEED, TVAL_STAFF
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-magic-shop-1121"
PAGE_ROW = 13
MATCHED = 3
PRICE = 30000
GOLD = 200000


class SpeedStaffFirstRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        policy, _journal, steps = load(FIXTURE, Path(self.scratch.name))
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        self.decided = []
        for recorded, supply in steps[:PAGE_ROW]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            self.decided.append((recorded, key, policy.last_reason))
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, recorded["key"]):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": recorded["key"]})
        self.recorded, supply = steps[PAGE_ROW]
        self.page = supply()
        self.policy = policy

    def shelved(self, **player):
        """DECLARED CONSTRUCTED (module docstring): the page with a Staff of Speed."""
        store = self.page.store
        light = next(item for item in store.items if item.tval == TVAL_STAFF)
        speed = replace(light, sval=SV_STAFF_SPEED, name="スピードの杖 (10回分)",
                        charges=10, pval=10, price=PRICE)
        items = tuple(speed if item is light else item for item in store.items)
        return replace(self.page, store=replace(store, items=items),
                       player=replace(self.page.player, gold=GOLD, **player))

    def purchase(self, board):
        """The page's purchase: the board observed by the chooser, then the shop's selector."""
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(board)
            return self.policy._next_purchase(board)

    def speed_letter(self, board):
        return next(item.letter for item in board.store.items if item.sval == SV_STAFF_SPEED
                    and item.tval == TVAL_STAFF)

    def test_replay_and_the_recorded_page(self):
        for recorded, key, reason in self.decided[:MATCHED]:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
        self.assertEqual(self.page.store.store_type, STORE_BLACK)
        self.assertEqual(self.recorded["key"], "px\r")
        self.assertTrue(bm_destruction_fund.first_speed_staff_wanted(self.policy, self.page))

    def test_the_first_staff_of_speed_is_bought_before_every_other_ware(self):
        board = self.shelved()
        ware = self.purchase(board)
        self.assertIsNotNone(ware)
        self.assertEqual((ware.letter, ware.tval, ware.sval),
                         (self.speed_letter(board), TVAL_STAFF, SV_STAFF_SPEED))
        self.assertEqual(self.policy._bm_destruction_shelf["ware"], "speed-staff")

    def test_an_absorbed_speed_power_leaves_the_ordinary_order(self):
        me_capability.recorded(self.policy)[me_capability.record_key("staff", SV_STAFF_SPEED)] = 3
        board = self.shelved()
        self.assertFalse(bm_destruction_fund.first_speed_staff_wanted(self.policy, board))
        self.purchase(board)
        shelf = getattr(self.policy, "_bm_destruction_shelf", None)
        self.assertNotEqual((shelf or {}).get("ware"), "speed-staff")

    def test_a_carried_staff_of_speed_leaves_the_ordinary_order(self):
        board = self.shelved()
        speed = next(item for item in board.store.items if item.sval == SV_STAFF_SPEED
                     and item.tval == TVAL_STAFF)
        template = board.inventory[0]
        carried = replace(template, tval=TVAL_STAFF, sval=SV_STAFF_SPEED, name=speed.name,
                          count=1, charges=10, pval=10, aware=True, known=True,
                          slot=chr(ord("a") + len(board.inventory)))
        board = replace(board, inventory=(*board.inventory, carried))
        self.assertFalse(bm_destruction_fund.first_speed_staff_wanted(self.policy, board))


if __name__ == "__main__":
    unittest.main()
