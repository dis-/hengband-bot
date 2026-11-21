"""Hunger on the finale's floor: eat at once, recall when nothing is left to eat (n1-b life-411).

Owner 2026-11-21 (verbatim, LOCKED) 「空腹で死ぬ前に帰還するように修正」.  Recorded (capture
n1b-411-20261121-100f-hunger): n1-b (race 25, a MANA eater: cmd-item/cmd-eat.cpp
exe_eat_charge_of_magic_device, 5000 food per wand or staff charge) carried its staple, a wand
with about a hundred charges.  On Angband 100F it turned hungry at turn 11463702 (board 2669,
「お腹が空いてきた」), and the battle, which answers above the survival ladder, kept resting and
fighting; the starvation gate's eat (survival:mana-absorb, ``Ek``) came only at turn 11464571,
after 「お腹が空いて倒れそうだ」 (weak), from the second, unidentified wand.  The staple had been
drained to 0 by a monster's UN_POWER blow (monster-attack/monster-eating.cpp process_un_power;
owner: 「モンスターの近接能力で魔法棒のチャージが0になっていた」, and 「取り込んだ魔力では空腹を満たせない」).
Now the battle eats when hungry (``_eat_key``), and with nothing that counts as food (a device only
while its charges are shown) its recall is permitted (``starving_out``).

The policy: n1-b's town-arrival checkpoint of 15:31:51 (the preparation visit before this
expedition, tests/fixtures/n1b-hunger-100f-1121, with board 2669).

DECLARED CONSTRUCTED: the expedition's mark and the battle in its recovery (as recorded: it rested
on board 2669); no return latched; no list re-read at the decision's head; for the eating case,
the staple's charges not drained (5).
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

from hengbot import angband_finale_battle as battle, finale_prep
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-hunger-100f-1121"


class N1b411Hunger100fRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(self.policy)
        held.lifted, held.step, held.in_town = True, finale_prep.DONE, False  # DECLARED
        self.policy._returning_to_town, self.policy._last_return_trigger = False, None  # DECLARED
        self.policy._me_power_resume_reads = False  # DECLARED
        rows = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
        self.board = parse_snapshot(rows[0]["board"], self.policy._monrace_knowledge)
        self.assertEqual((self.board.dungeon_level, self.board.player.food_state), (100, "hungry"))
        held_battle = battle.battle(self.policy, self.board)
        held_battle.phase = battle.RECOVER  # DECLARED: resting after a teleport, as recorded

    def tearDown(self):
        self.scratch.cleanup()

    def decide(self, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = self.policy.choose_key(board)
        return key, self.policy.last_reason

    def test_hungry_with_the_staple_drained_recalls(self):
        """Recorded board 2669: the staple wand drained to 0 by a monster's UN_POWER blow (owner:
        「モンスターの近接能力で魔法棒のチャージが0になっていた」), the other wand unidentified (its
        charges not shown), so nothing counts as food: the recall (recorded: angband-finale:rest)."""
        self.assertIsNone(self.policy._find_edible(self.board))
        _key, reason = self.decide(self.board)
        self.assertEqual(reason, battle.RECALL_REASON)
        self.assertTrue(battle.starving_out(self.policy, self.board))

    def test_hungry_with_a_charged_staple_eats_at_once(self):
        staple = next(item for item in self.board.inventory if item.is_wand_staff and item.known)
        board = replace(self.board, inventory=tuple(
            replace(item, charges=5) if item is staple else item
            for item in self.board.inventory))  # DECLARED: the staple's charges not drained
        key, reason = self.decide(board)
        self.assertEqual(reason, "angband-finale:eat")  # battle.EAT_REASON
        self.assertTrue(key.startswith("E"), key)

if __name__ == "__main__":
    unittest.main()
