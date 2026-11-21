"""The 99F battle's recovery drank Restore Mana on every board (n1-c life-217, 2026-11-21 12:59).

Recorded (capture n1c-217-20261121-125910-loop-detected, the state boards 66-72 in
tests/fixtures/n1c-restore-mana-loop-1121/boards.json.xz): on Angband 99F the battle read
Teleportation (board 68, 12:59:06) and its recovery (angband_finale_battle ``_recover_key``)
drank a Potion of Restore Mana on board 69 and then on every board after it, 34 -> 12, until the
loop detector stopped the bot at 12:59:08.  The Rocket's uses are read from the last displayed
wand list (me_capability ``charges``), which only a cast or a browse shows; Restore Mana
(spell/spells-status.cpp restore_mana: every absorbed staff and wand gains count / 3 uses, 3
below ten, never past its count; every rod recharges) shows none, so the list kept the Rocket
short and ``_refill_worth`` held on every board.  The owner on the potion: 「絶対に売ってはならない」
「99F・100Fをクリアするための非常に重要なアイテム」.

Now the line 「頭がハッキリとした」 marks every displayed list stale (me_device_attacks
``stale_kinds``), the decision's head reads the stale lists again by browsing (no game time,
me_powers_refresh ``resume_read_key``, the wand's first), and the battle drinks only on a fresh
wand list (``rocket_list_fresh``).

The policy: n1-c life-217's town-arrival checkpoint of 12:29:10 (tests/fixtures/
n1c-99f-quick-return-1121, the same character half an hour earlier).

DECLARED CONSTRUCTED:
* the expedition's mark (finale_prep ``lifted``), no return latched, and the CLI's resume reads
  on (cli sets ``_me_power_resume_reads``);
* the checkpoint's wand list with the Rocket at 2 of its 11 (after the battle's rockets: the
  capture holds no wand list);
* the browse's answer after the first quaff: the wand list with the Rocket at 5 (2 + 11 / 3),
  then at 8 (another potion's).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale_battle as battle
from hengbot import finale_prep, me_device_attacks
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
ROCKET_ROW = {"success": 99, "max": 11}


def _rocket(row) -> bool:
    return all(row.get(name) == value for name, value in ROCKET_ROW.items())


class FinaleRestoreManaLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURES / "n1c-99f-quick-return-1121",
                                             Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(self.policy)
        held.lifted, held.step = True, finale_prep.DONE  # DECLARED
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        self.policy._me_power_resume_reads = True  # DECLARED: the CLI's
        turn, rows = self.policy._me_device_lists["wand"]
        self.wand_rows = rows
        self.policy._me_device_lists["wand"] = (turn, self.with_rocket(2))  # DECLARED
        recorded = json.loads(lzma.decompress(
            (FIXTURES / "n1c-restore-mana-loop-1121" / "boards.json.xz").read_bytes()))
        self.boards = {row["line"]: parse_snapshot(row["board"], self.policy._monrace_knowledge)
                       for row in recorded}

    def tearDown(self):
        self.scratch.cleanup()

    def with_rocket(self, current):
        return tuple(dict(row, current=current) if _rocket(row) else dict(row)
                     for row in self.wand_rows)

    def decide(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = self.policy.choose_key(board)
        if key:
            self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason

    def until_first_quaff(self):
        for line in (66, 67, 68):
            self.decide(self.boards[line])
        self.assertEqual(self.policy.last_reason, battle.TELEPORT_REASON)  # recorded at 68
        key, reason = self.decide(self.boards[69])
        self.assertEqual(reason, battle.RESTORE_MANA_REASON)  # recorded at 69
        return key

    def test_no_second_quaff_before_the_wand_list_is_read_again(self):
        self.until_first_quaff()
        for line in (70, 71, 72):  # each recorded board carries 「頭がハッキリとした」
            key, reason = self.decide(self.boards[line])
            self.assertNotEqual(reason, battle.RESTORE_MANA_REASON, line)
            self.assertEqual(key, "bB", line)  # the wand list browsed (no game time)
        self.assertIn("wand", me_device_attacks.stale_kinds(self.policy))
        self.assertFalse(battle.rocket_list_fresh(self.policy))

    def test_the_fresh_list_decides_the_next_potion(self):
        self.until_first_quaff()
        self.decide(self.boards[70])
        # DECLARED: the browses' answers: the wand list with the Rocket at 5 of 11, then the
        # staff and rod lists (the checkpoint's own rows).
        shown = replace(self.boards[70], messages=(), magic_eater_power_list={
            "kind": "wand", "rows": [dict(row) for row in self.with_rocket(5)]})
        self.assertEqual(self.decide(shown), ("bA", "periodic:magic-eater-powers"))
        self.assertTrue(battle.rocket_list_fresh(self.policy))
        for kind, browse in (("staff", "bC"), ("rod", None)):
            listed = replace(shown, magic_eater_power_list={
                "kind": kind, "rows": [dict(row) for row in self.policy._me_device_lists[kind][1]]})
            key, reason = self.decide(listed)
            if browse is not None:
                self.assertEqual(key, browse)
        # Every list fresh: one more potion lands whole on the Rocket's 5.
        self.assertFalse(me_device_attacks.stale_kinds(self.policy))
        self.assertEqual(reason, battle.RESTORE_MANA_REASON)
        # DECLARED: after that potion the browse shows 8 of 11: no potion more.
        shown = replace(listed, magic_eater_power_list={
            "kind": "wand", "rows": [dict(row) for row in self.with_rocket(8)]})
        self.assertNotEqual(self.decide(shown)[1], battle.RESTORE_MANA_REASON)


if __name__ == "__main__":
    unittest.main()
