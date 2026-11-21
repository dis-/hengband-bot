"""The 100F battle stopped on the absorbed rod's prompt (n1-c life-217, 2026-11-21 14:24:01).

Recorded (capture n1c-217-20261121-142404-stuck-prompt-angband-finale-absorbed-healing): on
Angband 100F the battle's heal (angband_finale_battle ``_heal``) cast the absorbed Rod of
Healing (``mCj``) on consecutive boards, ten casts of a rod absorbed ten times, then once more:
the game refused it (cmd-item/cmd-magiceat.cpp:396-399 「その魔法はまだ充填している最中だ。」, the
prompt kept open) and the bot stopped, ``stuck-prompt ... owner=angband-finale:absorbed-healing
... reason=unowned``.  The screen at the stop: ``j) 体力回復 充填:10/10``.

The rod's 「充填: X/Y」 is X of Y charging (cmd-magiceat.cpp:284-289, the count of charging uses
over the count absorbed; a cast is refused while X == Y), and me_capability ``charges`` reads it
as Y - X.  What the battle read was the list shown during the previous cast, before that cast
charged one more (9/10, one ready); that a remembered row is stale after a cast is why every
absorbed-power owner's prompt is answered by me_device_attacks_input, which closes a power the
shown list has charging with ESC (no game time).  The battle's heal set a bare reason, which no
table owns (me_device_attacks_input ``_table``), so nothing answered the refused prompt.

The board: the capture's last state board (tests/fixtures/n1c-rod-charging-1121, 100F, HP
501/688); the policy: n1-c life-217's 12:29:10 checkpoint (tests/fixtures/n1c-99f-quick-return-1121).

DECLARED CONSTRUCTED: the remembered lists: the staff's Healing spent (0 of its uses), the rod
list showing the Rod of Healing 9 of 10 charging (as shown during its tenth cast), then 10 of 10.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale_battle as battle
from hengbot import me_capability
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.me_device_attacks_input import compile_device
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
HEALING_NAMES = me_capability.names("rod", 9) + me_capability.names("staff", 18)


class FinaleRodChargingRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURES / "n1c-99f-quick-return-1121",
                                             Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        rows = json.loads(lzma.decompress(
            (FIXTURES / "n1c-rod-charging-1121" / "boards.json.xz").read_bytes()))
        self.board = parse_snapshot(rows[0]["board"], self.policy._monrace_knowledge)
        self.assertEqual(self.board.dungeon_level, 100)
        lists = self.policy._me_device_lists
        turn, staffs = lists["staff"]
        lists["staff"] = (turn, tuple(dict(row, current=0) if row.get("name") in HEALING_NAMES
                                      else row for row in staffs))  # DECLARED: spent
        self.set_rod_charging(9)

    def tearDown(self):
        self.scratch.cleanup()

    def set_rod_charging(self, charging):
        """DECLARED: the remembered rod list with the Rod of Healing ``charging`` of 10."""
        lists = self.policy._me_device_lists
        turn, rods = lists["rod"]
        rows = [dict(row, charging=charging, max=10) if row.get("name") in HEALING_NAMES
                else dict(row) for row in rods]
        self.assertTrue(any(row.get("name") in HEALING_NAMES for row in rows))
        lists["rod"] = (turn, tuple(rows))

    def test_the_rod_cast_is_an_owned_prompt(self):
        self.assertEqual(me_capability.charges(self.policy, self.board, "rod", 9), 1)
        key = battle._heal(self.policy, self.board)
        self.assertEqual(key, "mCj")  # the recorded key
        reason = self.policy.last_reason
        self.assertEqual(reason, battle.ABSORBED_HEAL_REASON)
        self.assertTrue(reason.endswith(CAST_SUFFIX))
        # me_device_attacks_input answers its prompts (and ESCs a power the list shows charging).
        self.assertIsNotNone(compile_device(key, reason))

    def test_a_rod_shown_all_charging_is_not_cast(self):
        self.set_rod_charging(10)  # the stop's screen: 充填:10/10
        self.assertEqual(me_capability.charges(self.policy, self.board, "rod", 9), 0)
        battle._heal(self.policy, self.board)
        self.assertNotEqual(self.policy.last_reason, battle.ABSORBED_HEAL_REASON)


if __name__ == "__main__":
    unittest.main()
