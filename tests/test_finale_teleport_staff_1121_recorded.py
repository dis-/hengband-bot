"""No Teleportation scroll left on the finale's floor: the absorbed staff, then recall and resupply.

Owner 2026-11-21 (verbatim, LOCKED): 「100Fへ降りる前に巻物を補給する」, with 「テレポートの巻物が尽きた
時は帰還して補給する」, and 「99F100Fでテレポートの巻物が尽きた時は取り込んだテレポートの杖を使用する
ことを許可する」.  n1-c life-217's 100F board of 14:41:02 (tests/fixtures/n1c-finale-restart-1121,
capture n1c-217-20261121-death-100f) carries no Teleportation scroll (all 40 spent on 99F/100F),
10 Word of Recall, quest 9 (the Serpent) TAKEN.

The policy: n1-c life-217's 12:29:10 checkpoint (tests/fixtures/n1c-99f-quick-return-1121), whose
staff list shows the absorbed Staff of Teleportation 99/99.

DECLARED CONSTRUCTED: the expedition's mark; no return latched; no list re-read at the decision's
head; the staff list's Teleportation at 0 for the out-of-teleports case.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, angband_finale_battle as battle, finale_prep, me_capability
from hengbot.me_absorbed_substitutes import TELEPORTATION
from hengbot.me_device_attacks_input import compile_device
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")


class FinaleTeleportStaffRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURES / "n1c-99f-quick-return-1121",
                                             Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(self.policy)
        held.lifted, held.step = True, finale_prep.DONE  # DECLARED
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        self.policy._me_power_resume_reads = False  # DECLARED
        rows = json.loads(lzma.decompress(
            (FIXTURES / "n1c-finale-restart-1121" / "boards.json.xz").read_bytes()))
        self.board = parse_snapshot(rows[0]["board"], self.policy._monrace_knowledge)
        self.assertEqual(angband_finale.carried(self.board, angband_finale.TELEPORT), 0)

    def tearDown(self):
        self.scratch.cleanup()

    def staff_teleport(self, current):
        turn, rows = self.policy._me_device_lists["staff"]
        names = me_capability.names(*TELEPORTATION)
        self.policy._me_device_lists["staff"] = (turn, tuple(
            dict(row, current=current) if row.get("name") in names else row for row in rows))

    def test_the_absorbed_staff_serves_when_no_scroll_is_left(self):
        self.assertTrue(battle.applies(self.policy, self.board))
        key = battle._teleport(self.policy, self.board)
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith("mA"), key)
        self.assertEqual(self.policy.last_reason, battle.TELEPORT_STAFF_REASON)
        self.assertIsNotNone(compile_device(key, self.policy.last_reason))  # an owned prompt
        self.assertFalse(battle.teleports_out(self.policy, self.board))
        self.assertFalse(battle.recall_permitted(self.policy, self.board))

    def test_no_scroll_and_no_staff_charge_recalls(self):
        self.staff_teleport(0)  # DECLARED
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(self.board)
        self.assertEqual(self.policy.last_reason, battle.RECALL_REASON)
        self.assertIsNone(battle._teleport(self.policy, self.board))
        self.assertTrue(battle.teleports_out(self.policy, self.board))
        self.assertTrue(battle.recall_permitted(self.policy, self.board))


if __name__ == "__main__":
    unittest.main()
