"""n1-c life-217 2026-11-19 16:16:19, town:blocked:stage-deadline:buy (bot main 53c53f00d8).

The Magic-Eater (Lv44) came home with 239 stacks at Home and the cap tidy (home_cap, owner
2026-11-19 「200件（空き40）」「一気に片づける」) began.  Two faults stopped it after 18 wares:

1. The first batch took six weapons and amulets, then the seventh take filled the pack (19 of
   23 slots, 164.8 of 165.0 lb).  That take was sold alone, the six stayed carried, and every
   later trip moved one light ring (rows 21-125): the batch never drained.  Now the take that
   fills the pack joins the batch and ends it, and the whole batch is sold (home_cap.drain).
2. The stage deadlines (town_visit_plan, owner 2026-11-13 「段の期限は測った最大の2倍」,
   2026-11-14 「歩きは数えない」) restart a stage's count when a board shows new work right
   after one of its decisions.  Each sale's leave-and-re-enter (shop:observe-and-leave, the
   buy stage) came before the sale's own decision, so the buy count only grew: 18 by row 281,
   and row 282 became the buy stage's stop while every sale had raised the gold.  While the
   cap tidy runs, each observed unit of its work restarts its stages' counts
   (``CAP_TIDY_STAGES``); a tidy that shows no new work still spends them.

Recorded: the stop's town-arrival checkpoint and all 283 journal rows
(tests/extract_n1c_217_home_cap_deadline_1119_fixture.py).  Rows 12-17 (the first batch's takes)
are decided through the public choose_key and compared with the record.  The deadline
accounting is run over the recorded rows themselves (their boards, keys and reasons), as the
live bot counted them.

DECLARED CONSTRUCTED: in the accounting, the cap tidy the live bot held from row 8 (the record's
home:cap-tidy-* reasons) is given to the policy, and row 282 is asked as the buy decision it
replaced (shop:observe-and-leave).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_cap, town_visit_plan
from hengbot.home_full_relief import HomeFullRelief
from hengbot.town_visit import town_visit
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-home-cap-deadline-1119"
FIRST_TAKE, FILLING_TAKE, STOP_ROW = 12, 17, 282
BUY_DECISION = ("\x1b", "shop:observe-and-leave")


def accounting(fixture_rows, policy, *, stall_from=None):
    """The stage deadline over the recorded rows; (stop row, stop, buy count at the stop row).

    ``stall_from``: from that row on every board repeats the one before it (no new work).
    """
    previous = None
    for row, (recorded, supply) in enumerate(fixture_rows):
        board = supply()
        if stall_from is not None and row >= stall_from:
            board = previous
        previous = board
        if recorded["reason"].startswith("home:cap-tidy") and policy._home_full_relief is None:
            policy._home_full_relief = HomeFullRelief(remaining=39, town=0, cap=True)
        town_visit_plan.note_observed_progress(policy, board)
        key, reason = ((BUY_DECISION if row == STOP_ROW else (recorded["key"], recorded["reason"])))
        policy.last_reason = reason
        stop = town_visit_plan.stage_deadline_stop(policy, board, key)
        if stop is not None or row == STOP_ROW:
            return row, stop, town_visit(policy).stage_decisions.get("buy", 0)
        town_visit_plan.note_decision(policy, board, key)
    return None, None, None


class N1c217HomeCapDeadline1119RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, self.journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_recorded_visit_stopped_at_the_buy_deadline(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], "town:blocked:stage-deadline:buy")
        self.assertEqual(town_visit_plan.STAGE_DEADLINES["buy"], 18)

    def test_the_tidy_that_keeps_selling_spends_no_deadline(self):
        row, stop, buy = accounting(self.steps, self.policy)
        self.assertEqual((row, stop), (STOP_ROW, None))
        self.assertLess(buy, town_visit_plan.STAGE_DEADLINES["buy"])

    def test_a_tidy_that_shows_no_new_work_still_stops(self):
        row, stop, _ = accounting(self.steps, self.policy, stall_from=150)
        self.assertIsNotNone(stop)
        self.assertLess(row, STOP_ROW)

    def test_the_take_that_fills_the_pack_sells_the_whole_batch(self):
        policy = self.policy
        for row, (recorded, supply) in enumerate(self.steps[:FILLING_TAKE + 2]):
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            if FIRST_TAKE <= row <= FILLING_TAKE:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]), row)
            if row == FILLING_TAKE + 1:
                break
            post(policy, board, recorded["key"], before)
        relief = policy._home_full_relief
        # Row 18's board: the seventh ware taken, the pack at its reserve.
        self.assertEqual((len(board.inventory), policy._inventory_weight(board),
                          policy._inventory_weight_limit(board)), (19, 1648, 1650))
        self.assertFalse(home_cap.batch_grows(policy, board, relief))
        # All seven are the batch, sold first: the first carried ware's pack sale.
        self.assertTrue(relief.draining)
        self.assertEqual(len(relief.carried), 6)
        self.assertTrue(relief.pack_only and relief.withdrawn and relief.mode == "sale")
        self.assertEqual(relief.remaining, 239 - 200 - 7)
        self.assertEqual(policy.last_reason, "shop:travel")
        # Its sale frees a slot (DECLARED CONSTRUCTED: the ware off the pack, as sold); the
        # next carried ware is sold next, not another shelf ware taken.
        post(policy, board, key, copy.copy(policy._store_visit))
        sold = relief.sale[0]
        board = replace(board, inventory=tuple(
            item for item in board.inventory if policy._item_signature(item) != sold))
        self.assertTrue(home_cap.batch_grows(policy, board, relief))
        for _ in range(3):
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            post(policy, board, key, before)
            if relief.sale is None or relief.sale[0] != sold:
                break
        self.assertTrue(relief.draining)
        self.assertEqual(len(relief.carried), 5)
        self.assertTrue(relief.pack_only and relief.withdrawn)


if __name__ == "__main__":
    unittest.main()
