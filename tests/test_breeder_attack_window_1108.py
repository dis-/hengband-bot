"""breeder-attack-window-1108: the 20-action breeder window counts only attack actions.

Owner 2026-11-08: 「20回の判定は、実際に攻撃した手だけで数える。」  n1-c life-164 latched Q25 on a
window of which 38 of 40 actions were holds beside the corpse masses (breeder_stalemate).

DECLARED CONSTRUCTED: the breeder-window-1103 board (tests/test_breeder_window_1103_recorded) with
ten worms, its turn advanced 10 per action; the window is opened by that test's constructed attack;
each later board follows a decision whose reason is set here (a hold, then a shot).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import breeder_stalemate
from hengbot.model import parse_snapshot
from hengbot.quest_find_exit import HOLD_REASON
from tests import test_breeder_window_1103_recorded as window


class OnlyAttacksCountTest(window.WindowCase):
    """「20回の判定は、実際に攻撃した手だけで数える。」"""

    def test_holds_do_not_advance_the_window(self):
        policy = window.new_policy()
        window.open_by_attack(policy, window.worms(10, 0))
        self.assertEqual(policy._breeder_engagement_actions, 0)
        snapshot = parse_snapshot(copy.deepcopy(window.worms(10, 0)), policy._monrace_knowledge)
        for action in range(1, 2 * window.WINDOW):
            policy.last_reason = HOLD_REASON
            snapshot = parse_snapshot(copy.deepcopy(window.worms(10, action)), policy._monrace_knowledge)
            self.assertFalse(breeder_stalemate.flee_due(policy, snapshot, list(snapshot.visible_monsters)))
        self.assertEqual(policy._breeder_engagement_actions, 1)   # the attack before the first hold
        for action in range(2 * window.WINDOW, 3 * window.WINDOW):
            policy.last_reason = "ranged:fire"
            snapshot = parse_snapshot(copy.deepcopy(window.worms(10, action)), policy._monrace_knowledge)
            due = breeder_stalemate.flee_due(policy, snapshot, list(snapshot.visible_monsters))
        self.assertTrue(due)


if __name__ == "__main__":
    unittest.main()
