"""A carried Scroll of Reset Recall sets Angband back to 95F (owner 2026-11-21).

Owner (verbatim, LOCKED) 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」, its option
「拾ったり闇市に並んだフロア・リセットの巻物があれば使って95Fに戻す」.  The game: reset_recall
(spell-kind/spells-world.cpp) asks choose_dungeon, then 「何階にセットしますか？」 (input_numerics, the
saved depth as the default; the first digit clears it, core/asking-player.cpp askfor).

Recorded: n1-b's town visit of 2026-11-21 17:15:50 (tests/fixtures/n1b-411-deep-angband-recall-1121),
its first board (Angband's recall depth 100).

DECLARED CONSTRUCTED: a Scroll of Reset Recall in the pack (a copy of the board's Word of Recall row);
the Black Market's row of one.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, consumable_policy, finale_prep, reset_recall
from hengbot.model import DUNGEON_ANGBAND
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-deep-angband-recall-1121"


class ResetRecallRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        self.board = steps[0][1]()
        self.assertEqual(self.board.dungeon_recall_depths[DUNGEON_ANGBAND], 100)
        recall = next(item for item in self.board.inventory if item.is_recall_scroll)
        self.scroll = replace(recall, sval=reset_recall.SV_SCROLL_RESET_RECALL, count=1,
                              name="フロア・リセットの巻物", slot="w", inscription="")  # DECLARED
        self.with_scroll = replace(self.board, inventory=(*self.board.inventory, self.scroll),
                                   store=None)

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_scroll_is_read_to_set_angband_to_95(self):
        key = reset_recall.key(self.policy, self.with_scroll)
        selection = self.policy._recall_selection_key(self.with_scroll, DUNGEON_ANGBAND)
        self.assertEqual(key, f"rw{selection}95\r")
        self.assertEqual(self.policy.last_reason, reset_recall.REASON)

    def test_the_scroll_is_kept_and_bought_while_refused(self):
        self.assertTrue(consumable_policy.carry_required(self.policy, self.with_scroll, self.scroll))
        self.assertTrue(angband_finale.black_market_wanted(self.policy, self.board, self.scroll))
        self.assertFalse(angband_finale.black_market_wanted(self.policy, self.with_scroll, self.scroll))

    def test_nothing_on_the_expedition_or_at_95(self):
        at_95 = replace(self.with_scroll, dungeon_recall_depths={
            **self.board.dungeon_recall_depths, DUNGEON_ANGBAND: 95})  # DECLARED
        self.assertIsNone(reset_recall.key(self.policy, at_95))
        finale_prep.phase(self.policy).lifted = True  # DECLARED: the expedition's mark
        self.assertIsNone(reset_recall.key(self.policy, self.with_scroll))


if __name__ == "__main__":
    unittest.main()
