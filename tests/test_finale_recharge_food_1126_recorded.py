"""The 100F battle of a Zombie reads a Scroll of Recharging on a drained food wand when hungry
with all three drained, and eats it, instead of recalling (n1-c life-222, Angband 100F,
2026-11-26 10:04).

Owner 2026-11-26 (verbatim): 「魔力充填の巻物を10巻持っていき、空腹かつ3本とも空の場合のみ充填して
食料とする」.

The recorded run (fixture finale-bank-food-n1c-222-1126, tests/test_finale_bank_food_1126_recorded):
the three food wands (謎の魔法棒 {@E1} {@E2} {@E3}) were drained to 0 charges by UN_POWER blows;
hungry at turn 12325001 with nothing to eat, the battle recalled (``starving_out``).  The run
carried no Scroll of Recharging.

DECLARED CONSTRUCTED: ``SCROLLS`` Scrolls of Recharging (tval 70, sval 22) inserted into every
board's pack in the game's pack order (after the Word of Recall, sval 11; the later slots
re-lettered), for the runs "with scrolls"; the board after the read showing the targeted wand
recharged (unidentified, no charges: spell-kind/magic-item-recharger.cpp resets KNOWN) for the
eat test.  The replay is open-loop (tests/support/finale_416).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import string
import unittest

from hengbot import angband_finale, angband_finale_battle as fb, finale_recharge_food as frf
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

FIXTURE = "finale-bank-food-n1c-222-1126.jsonl.gz"
WINDOW = 12324500
FIRST_HUNGER = 12320551
STARVED = 12325001
AFTER_READ = 12325003  # the next recorded board
SCROLLS = 10
TVAL_SCROLL, SV_RECHARGING = 70, 22
TVAL_WAND, SV_WAND_WONDER = 65, 24


def _with_scrolls(raw: dict) -> dict:
    """The board with SCROLLS Scrolls of Recharging in its pack order (DECLARED CONSTRUCTED)."""
    raw = copy.deepcopy(raw)
    pack = raw["inventory"]
    template = next(item for item in pack if item["tval"] == TVAL_SCROLL)
    scroll = {**copy.deepcopy(template), "sval": SV_RECHARGING, "count": SCROLLS,
              "name": f"{SCROLLS}巻の魔力充填の巻物", "inscription": ""}
    # The pack's order: tval descending, sval ascending within a tval.
    at = next((index for index, item in enumerate(pack)
               if item["tval"] < TVAL_SCROLL
               or (item["tval"] == TVAL_SCROLL and item["sval"] > SV_RECHARGING)), len(pack))
    pack.insert(at, scroll)
    for letter, item in zip(string.ascii_lowercase, pack):
        item["slot"] = letter
    return raw


def _food_slots(board: dict, charged: bool) -> set:
    return {item["slot"] for item in board["inventory"]
            if item["tval"] == TVAL_WAND and item["sval"] == SV_WAND_WONDER
            and (item.get("charges", 0) > 0) == charged}


def _scroll_slot(board: dict) -> str:
    return next(item["slot"] for item in board["inventory"]
                if (item["tval"], item["sval"]) == (TVAL_SCROLL, SV_RECHARGING))


class FinaleRechargeFoodRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.monrace = monrace
        boards = finale_416.boards(FIXTURE)
        split = next(index for index, board in enumerate(boards) if board["turn"] >= WINDOW)
        cls.checks = {}

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            if board.turn == STARVED and frf.scrolls(board):
                scroll = next(item for item in board.inventory if angband_finale.is_recharging(item))
                cls.checks = {
                    "carry": angband_finale.carry_target(policy, board, scroll),
                    "retention": policy._retention_reservation_detail(board, scroll),
                    "junk": policy._junk_class(board, scroll),
                    "shortage": angband_finale.shortage(policy, board, angband_finale.RECHARGING),
                }
            if board.turn == AFTER_READ and frf.scrolls(board):
                cls.checks["starving_after_refusal"] = fb.starving_out(policy, board)

        cls.window = [_with_scrolls(board) for board in boards[split:]]
        cls.rows = finale_416.drive(cls.window, monrace, prepare=prepare, eat_ahead=True)
        cls.bare_window = boards[split:]
        cls.bare_rows = finale_416.drive(cls.bare_window, monrace, prepare=prepare,
                                         eat_ahead=True)
        cls.opening = [_with_scrolls(board) for board in boards[:split]]
        cls.opening_rows = finale_416.drive(cls.opening, monrace, prepare=prepare,
                                            eat_ahead=True)

    def _row(self, rows, turn):
        return next(row for row in rows if row[0] == turn)

    def test_hungry_with_all_three_drained_reads_recharging_on_a_food_wand(self):
        # Recorded: the recall (starving-out); revert: the same recall.
        board = next(board for board in self.window if board["turn"] == STARVED)
        row = self._row(self.rows, STARVED)
        self.assertEqual(row[3], frf.RECHARGE_REASON, row)
        self.assertEqual(row[2][0], "r", row)
        self.assertEqual(row[2][1], _scroll_slot(board), row)
        self.assertIn(row[2][2:], _food_slots(board, charged=False), row)

    def test_no_scroll_still_recalls(self):
        row = self._row(self.bare_rows, STARVED)
        self.assertEqual(row[3], fb.RECALL_REASON, row)
        self.assertFalse(any(row[3] == frf.RECHARGE_REASON for row in self.bare_rows))

    def test_a_refused_read_is_not_sent_again_on_the_floor(self):
        # Open-loop: the board after the read still shows ten scrolls on a later game turn (the
        # game would have spent one), which is a refusal: no second read, and hungry with nothing
        # to eat is starving out again (the recorded boards are already recalling).
        reads = [row for row in self.rows if row[3] == frf.RECHARGE_REASON]
        self.assertEqual(len(reads), 1, reads)
        self.assertTrue(self.checks["starving_after_refusal"], self.checks)

    def test_a_hungry_board_with_a_charged_wand_eats_and_reads_no_scroll(self):
        row = self._row(self.opening_rows, FIRST_HUNGER)
        board = next(board for board in self.opening if board["turn"] == FIRST_HUNGER)
        self.assertEqual(row[3], fb.EAT_REASON, row)
        self.assertEqual(row[2][0], "E", row)
        self.assertIn(row[2][1], _food_slots(board, charged=True), row)
        self.assertFalse(any(row[3] == frf.RECHARGE_REASON
                             for row in (*self.opening_rows, *self.rows) if row[0] < STARVED))

    def test_the_recharged_wand_is_eaten(self):
        # DECLARED CONSTRUCTED: the board after a successful read (the targeted wand unidentified,
        # its charges hidden), the policy that read it.
        from tests.support.recorded import _policy
        from pathlib import Path
        from tempfile import TemporaryDirectory
        raw = copy.deepcopy(next(board for board in self.window if board["turn"] == STARVED))
        target = self._row(self.rows, STARVED)[2][2:]
        wand = next(item for item in raw["inventory"] if item["slot"] == target)
        wand.update(known=False, fully_known=False, name="謎の魔法棒 {%s}" % wand["inscription"])
        for field in ("charges", "pval", "charging"):
            wand.pop(field, None)
        for item in raw["inventory"]:
            if (item["tval"], item["sval"]) == (TVAL_SCROLL, SV_RECHARGING):
                item["count"] = SCROLLS - 1
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            self.assertEqual([item.slot for item in frf.recharged(board)], [target])
            self.assertFalse(fb.starving_out(policy, board))
            self.assertTrue(frf.relief(policy, board))
            policy.prime(board)
            key = frf.key(policy, board)
        self.assertEqual(policy.last_reason, frf.RECHARGED_EAT_REASON)
        self.assertEqual(key, "E" + target)

    def test_the_scrolls_are_kept_for_the_finale(self):
        # A Zombie Magic-Eater past 95F: the ten are the finale's carry, retained (never sold or
        # destroyed: the consumable table discards the kind otherwise).
        self.assertEqual(self.checks["carry"], angband_finale.RECHARGING_CARRY, self.checks)
        self.assertEqual(self.checks["retention"],
                         (SCROLLS, angband_finale.RETENTION_BRANCH), self.checks)
        self.assertIsNone(self.checks["junk"], self.checks)
        self.assertEqual(self.checks["shortage"], 0, self.checks)


if __name__ == "__main__":
    unittest.main()
