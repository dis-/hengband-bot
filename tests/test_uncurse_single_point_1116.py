"""The worn curse is removed before a rest or a wait at one place (owner 2026-11-15, review Q4).

Owner 「1か所でまとめ構えも含める」: ``curse_cure.before_rest_or_wait`` at the ``choose_key`` exit asks the
removal whenever the decision's key rests or waits in the dungeon (a stance's hold included); the
quest plans no longer ask it themselves, and the safe-now rung keeps only rule 2 (a summoning or
drain-HP curse on a normal floor: removed when a means is had, else Recall).

Recorded: n1-c life-211's Quest 25 hold boards (tests/test_n1c_211_rest_curse_1115_recorded, its
fixture and helpers; the normal floor is that module's DECLARED CONSTRUCTED 30F floor).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import curse_cure
from hengbot.quest_plan_base import HOLD_REASON
from tests import test_n1c_211_rest_curse_1115_recorded as rest_curse

SRC = Path(__file__).resolve().parents[1] / "src" / "hengbot"


def _decide(raw):
    directory = TemporaryDirectory()
    policy = rest_curse.new_policy(Path(directory.name), raw, rest_curse.lists())
    key = rest_curse.decide(policy, raw)
    directory.cleanup()
    return policy.last_reason, key


class SinglePointTest(unittest.TestCase):
    def test_the_stance_hold_is_cured_at_the_exit(self):
        """The recorded Q25 hold board: the plan's hold '5' is replaced at the exit."""
        raw = rest_curse.board(rest_curse.HOLD)
        self.assertEqual(_decide(raw), (curse_cure.POWERFUL_REASON, "UAg"))

    def test_without_the_exit_point_nothing_else_cures_the_hold(self):
        raw = rest_curse.board(rest_curse.HOLD)
        with mock.patch.object(curse_cure, "before_rest_or_wait", lambda policy, snapshot, key: None):
            self.assertEqual(_decide(raw), (HOLD_REASON, "5"))

    def test_a_walk_on_a_normal_floor_is_not_replaced(self):
        """No rule-2 curse announced, a walk chosen: the removal waits for a rest or a wait
        (before, the safe-now rung removed it on any safe board)."""
        raw = rest_curse.normal_floor(rest_curse.board(rest_curse.HOLD))
        self.assertEqual(_decide(raw), ("seek-loot", "6"))

    def test_the_rest_and_wait_keys(self):
        for key in ("5", "s", "R&\r", "R100\r", "R{\r"):
            self.assertTrue(curse_cure.rests_or_waits(key), key)
        for key in ("6", "", None, "UAg", "rl", "mAw"):
            self.assertFalse(curse_cure.rests_or_waits(key), key)

    def test_the_removal_is_asked_in_curse_cure_only(self):
        """No module but curse_cure asks the removal itself (the one place, and rule 2's rung)."""
        callers = set()
        for path in SRC.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id == "curse_cure"
                        and node.attr in {"removal_key", "before_rest"}):
                    callers.add(path.stem)
        self.assertEqual(callers, set())
        self.assertFalse(hasattr(curse_cure, "before_rest"))


if __name__ == "__main__":
    unittest.main()
