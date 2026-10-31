"""Magic-Eater use_menu kind menu published as command_char (game 8efed08ef7).

cmd-magiceat.cpp select_magic_eater's cursor menu (「どの種類の魔法を使います
か？」 / 「どの種類の魔法を見ますか？」) read raw inkey() and published a null
context; since game develop 8efed08ef7 it is ``input_key_with_context
(InputKind::COMMAND_CHAR, prompt)``.  Each owner that answers the menu
(magic_eater_input, me_device_attacks_input, me_powers_refresh_input) gets
its key from the public ``choose_key`` and is sent through the production
executor; the game's replies publish the menu as command_char.

DECLARED CONSTRUCTED: the menu replies (rows 2-4 as cmd-magiceat.cpp prints
them at column 14, the cursor on the staff row); the boards are those of the
named existing tests.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.magic_eater import MISSILE_REASON
from tests import test_magic_eater_o3 as o3
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_stage2_powers as stage2
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_powers_refresh import BrowseGame

USE_MENU = "どの種類の魔法を使いますか？"
BROWSE_MENU = "どの種類の魔法を見ますか？"
KINDS = ("staff", "wand", "rod")
NAMES = ("杖", "魔法棒", "ロッド")


def kind_menu(text, cursor):
    """The menu as the new game publishes it (command_char, prompt = row 0)."""
    screen = prompt(text, "command_char")
    for index, name in enumerate(NAMES):
        mark = "》" if index == cursor else "  "
        screen["lines"][2 + index] = " " * 14 + f" {mark} {name}"
    return screen


class MenuBrowseGame(BrowseGame):
    """BrowseGame with use_menu on: the kind question is the cursor menu."""

    cursor = 0

    def key(self, char):
        if self.mode == "kind" and char in "28":
            self.cursor = (self.cursor + (1 if char == "2" else -1)) % len(KINDS)
            return
        if self.mode == "kind" and char == "\r":
            char = "ABC"[self.cursor]
        super().key(char)

    def render(self):
        if self.mode == "kind":
            return kind_menu(BROWSE_MENU, self.cursor)
        return super().render()


def borrow(cls, *names):
    """The named harness members of a test class, without its test methods."""
    return {name: cls.__dict__[name] for name in names}


class MissileKindMenuTest(unittest.TestCase):
    locals().update(borrow(o3.MagicEaterO3Test, "setUpClass", "policy", "board",
                           "choose", "run_follow"))

    def test_missile_menu_published_as_command_char(self):
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            kind_menu(USE_MENU, 0), kind_menu(USE_MENU, 1), o3.powers(menu=True, japanese=True),
            prompt("方向 ('*'でターゲット選択, ESCで中断)? ", "direction", can_choose_target=True)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "2", "\r", "\r", "6"])


class UtilityPowerKindMenuTest(stage2.mining.harness.ProductionHarness):
    locals().update(borrow(stage2.MagicEaterStage2PowersTest, "setUpClass", "raw",
                           "recorded_policy", "choose", "post", "board", "policy",
                           "assertPower"))

    def test_detect_evil_menu_published_as_command_char(self):
        raw = self.board()
        policy = self.policy(raw)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, "p", "me-power:new-floor:detect-evil")
        rows = [(stage2.me_powers.encode_letter(sval), stage2.NAMES[sval], 5, 14, 20)
                for sval in stage2.staff_rows()]
        game, port = self.post(policy, raw, key, [kind_menu(USE_MENU, 0),
                                                  power_screen("staff", rows)])
        self.assertEqual(game.accepted, ["m", "\r", "p"])


class ReadPowersKindMenuTest(nokey.PostedKey):
    def test_read_powers_menu_published_as_command_char(self):
        raw = nokey.staff_board(0)
        policy = nokey.staff_policy(raw, record=False)
        key = nokey.decide(policy, raw, nokey.CASE["staff"]["skill"])
        self.assertEqual((key, policy.last_reason), ("bA", "me-staff:read-powers"))
        game = MenuBrowseGame(copy.deepcopy(nokey.RestartForgetsAbsorptionsTest.ABSORBED))
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        listed = executor.ready_board["_magic_eater_power_list"]
        self.assertEqual([row["name"] for row in listed["rows"]], ["鑑定", "財宝感知"])


if __name__ == "__main__":
    unittest.main()
