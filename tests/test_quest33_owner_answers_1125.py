"""QUEST_33: the owner's answers of 2026-11-25 to the contradiction audit, one pin each.

The audit (C:/hengband-backups/pdca/maintainability-review-contradictions-1125/REPORT.md) asked
(b)-1..(b)-6; the Q33 side was ordered with (b)-1, (b)-2, (b)-3 and (b)-6, and two more answers of
the same day, (c)-1 and (c)-2, after n1-b life-418's death (memory q33-contradiction-answers-20261125).

DECLARED CONSTRUCTED: the floor boards are tests/test_quest33_post_disengage's (n1-b's recorded town
arrival moved onto the Q33 floor, a Magic-Eater with the absorbed Teleportation), the navigator put in
the state each pin names, and, where a pin says so, a reader patched to give the verdict it reads.
The Magic-Eater with spent attack powers is tests/test_me_stranded_rest_first_1125's replay of n1-c
life-220's recorded boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from unittest import mock

from hengbot import me_absorbed_substitutes, me_capability, quest_room_sweep, quest_wait_placement
from hengbot import quest_summon_answer as answer
from hengbot.model import Position
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import DAGON, QUEST, monster
from hengbot.q34_recharge import REST_KEY
from tests import test_me_stranded_rest_first_1125 as stranded
from tests import test_n1c_220_q33_sensed_1122_recorded as sensed
from tests.test_quest33_post_disengage import JART, _FloorBoards


class _SpentReplay(sensed.N1c220SensedChooseKeyTest):
    """n1-c life-220's Q33 replay with the attack powers spent (tests/test_me_stranded_rest_first_1125)."""

    def spent_board(self, lists):
        self.lists = lists
        (snapshot, _reason, _key), = self.answers(at=sensed.ACTED_ON_CELL, boards=1, full_hp=True)
        navigator = _navigator(self.policy, snapshot, QUEST)
        profile = self.policy.approved_quest_strategy(QUEST)
        plan = profile.engagement_plan["room_sweep"]
        board = quest_room_sweep._Board(self.policy, snapshot, profile, navigator, plan)
        ship = next(m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                    if m.race_id == sensed.PHANTOM_SHIP)
        return snapshot, navigator, plan, board, ship

    def with_spent(self):
        return {kind: (turn, tuple(stranded.spent(kind, row) if stranded.is_attack(kind, row) else row
                                   for row in rows))
                for kind, (turn, rows) in self.lists.items()}

    def with_none(self):
        return {kind: (turn, tuple(row for row in rows if not stranded.is_attack(kind, row)))
                for kind, (turn, rows) in self.lists.items()}


for _name in [name for name in vars(sensed.N1c220SensedChooseKeyTest) if name.startswith("test_")]:
    setattr(_SpentReplay, _name, None)


class B2RestFirstTest(_SpentReplay):
    """(b)-2 (as recommended): a Magic-Eater going after a summoner (``_go_after`` -> ``_approach``),
    and the room sweep's walk to what stands still (``_fight``), rest out of the lines first when a
    rest restores an absorbed attack power for it; they walk to melee only with none to restore."""

    def test_the_chase_rests_first(self):
        snapshot, navigator, plan, board, ship = self.spent_board(self.with_spent())
        self.assertTrue(answer.recharges_first(self.policy, snapshot, ship.race_id))
        self.assertEqual(answer.melee_approach(self.policy, snapshot, ship, site=answer.CHASE_SITE),
                         answer.REST_FIRST)
        key = answer._approach(self.policy, snapshot, navigator, plan, board, ship)
        self.assertEqual((key, self.policy.last_reason), (REST_KEY, answer.RECHARGE_REST_REASON))

    def test_the_sweep_rests_first(self):
        snapshot, _navigator_, _plan, _board, ship = self.spent_board(self.with_spent())
        self.assertEqual(answer.melee_approach(self.policy, snapshot, ship, site=answer.SWEEP_SITE),
                         answer.REST_FIRST)

    def test_with_nothing_to_restore_the_chase_closes_in(self):
        snapshot, _navigator_, _plan, _board, ship = self.spent_board(self.with_none())
        self.assertFalse(answer.recharges_first(self.policy, snapshot, ship.race_id))
        self.assertEqual(answer.melee_approach(self.policy, snapshot, ship, site=answer.CHASE_SITE),
                         answer.MELEE)
        self.assertEqual(answer.melee_approach(self.policy, snapshot, ship, site=answer.SWEEP_SITE),
                         answer.MELEE)


class B3VerdictReadAgainTest(_FloorBoards, unittest.TestCase):
    """(b)-3 「「来るか」は固定しておき、待ちの上限が尽きた時と、HP が隠れの境目をまたいで大きく変わった時だけ
    判断し直す」: the kept verdict is read again only on those two."""

    def setUp(self):
        super().setUp()
        self.reads = []

    def verdict(self, snapshot, navigator, comes_now):
        def will_come(*_args, **_kwargs):
            self.reads.append(1)
            return ((0, 0),) if comes_now else ()

        board = self.sweep_board(snapshot, navigator)
        with mock.patch.object(quest_wait_placement, "will_come", will_come):
            return answer.never_comes(self.policy, snapshot, navigator, self.plan, board, 1)

    def test_kept_until_the_hiding_line_is_crossed(self):
        full = self.board_at((13, 39), hp=int(self.board.player.max_hp * 0.7))
        navigator = self.disengaged(full, {1: (JART, (14, 20), False)})
        self.assertFalse(self.verdict(full, navigator, comes_now=True))   # read: it comes
        self.assertFalse(self.verdict(full, navigator, comes_now=False))  # kept
        self.assertEqual(len(self.reads), 1)
        # The same hiding line at a little less HP: kept.
        line = quest_wait_placement.hide_line(full)
        near = self.board_at((13, 39), hp=full.player.hp - 1)
        self.assertEqual(quest_wait_placement.hide_line(near), line)
        self.assertFalse(self.verdict(near, navigator, comes_now=False))
        # A fifth of the HP: the line is crossed, the verdict read again.
        low = self.board_at((13, 39), hp=full.player.max_hp // 5)
        self.assertNotEqual(quest_wait_placement.hide_line(low), line)
        self.assertTrue(self.verdict(low, navigator, comes_now=False))
        self.assertEqual(len(self.reads), 2)

    def test_read_again_once_when_the_wait_runs_out(self):
        snapshot = self.board_at((13, 39))
        navigator = self.disengaged(snapshot, {1: (JART, (14, 20), False)})
        self.assertFalse(self.verdict(snapshot, navigator, comes_now=True))
        answer._rejudge_after_wait(navigator, [1])
        later = self.board_at((13, 39))
        self.assertTrue(self.verdict(later, navigator, comes_now=False))   # read again
        answer._rejudge_after_wait(navigator, [1])
        again = self.board_at((13, 39))
        self.assertTrue(self.verdict(again, navigator, comes_now=True))    # once: kept now
        self.assertEqual(len(self.reads), 2)


if __name__ == "__main__":
    unittest.main()
