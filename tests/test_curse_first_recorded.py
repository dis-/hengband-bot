"""n1-a life-472 (2026-11-03 11:49): the Home *Remove Curse* was never fetched.

The worn ロング・ソード {呪われている} waited for *Identify*, which this visit
could not supply.  The Home *Remove Curse* binder waited for every carried or
worn identification candidate, the cursed weapon itself included, so the
scroll the supply ledger counted stayed at Home and the town end stopped
under town:blocked:survival:identify_staff_ready (remove_curse_ready unmet
as well).  Owner 2026-11-03 「先に解呪する」: remove the curse first,
identification waits; Home is entered again within its pass bound.

The take does not fit the pack reserve (19 of 23 slots), so the binder
begins the existing pack-room pass (owner 2026-10-31 「自宅にいるなら先に
不要物を仕舞う」) and binds the take once it fits.

Recorded: the capture's arrival checkpoint and journal
(tests/extract_curse_first_fixture.py).  Rows 0-24 replay unchanged through
the public chooser; at row 25, where the live run left the Magic shop and
went on to the stop, the pass sells the next surplus stack.  DECLARED WALL:
the in-store inscription is not posted through the executor (its prompt
chain is not part of the capture), and the rows after it are not recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import town_pack_headroom
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from hengbot.town_pack_budget import home_take_fits
from replay_town_arrival import decisions, journal, restore
from town_work_corpus import replay_window


FIXTURE = Path(__file__).with_name("fixtures") / "curse-first-20261103"


class CurseFirstRecordedTest(unittest.TestCase):
    def test_home_remove_curse_is_fetched_before_identification(self):
        with TemporaryDirectory() as raw:
            visit = Path(raw) / "town-arrival"
            visit.mkdir()
            (visit / POLICY_FILE).write_bytes(
                lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
            (visit / JOURNAL_FILE).write_bytes(gzip.compress(
                lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
            rows = journal(visit)
            self.assertEqual((rows[25]["key"], rows[25]["reason"]),
                             ("\x1b", "shop:in-store-done"))
            self.assertEqual(rows[-1]["reason"], "town:blocked:survival:identify_staff_ready")
            scratch = Path(raw) / "scratch"
            scratch.mkdir()
            policy = restore(visit, scratch)
            steps = list(decisions(policy, visit, scratch))
            result = replay_window("n1-a-472-1149", policy, iter(steps[:25]))
            self.assertIsNone(result.first_divergence)
            board = steps[25][1]()
            key = policy.choose_key(board)

        cursed = next(item for item in board.equipment if item.is_cursed)
        self.assertEqual(cursed.slot, "main_hand")
        self.assertEqual(policy._required_remove_curse_kind(board), "remove-curse")
        scroll = policy._home_remove_curse_scroll(board)
        self.assertIsNotNone(scroll)
        self.assertFalse(home_take_fits(board, scroll, 1))
        # The pack-room pass the curse take began now holds the visit.
        self.assertTrue(town_pack_headroom.organizing(policy, board))
        self.assertEqual((key, policy.last_reason), ("{b@0\r", "shop:in-store-inscribe"))
        sold = next(item for item in board.inventory if item.slot == "b")
        self.assertTrue(town_pack_headroom.preservable(policy, board, sold))


if __name__ == "__main__":
    unittest.main()
