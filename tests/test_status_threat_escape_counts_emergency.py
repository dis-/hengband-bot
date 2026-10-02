"""Pin: status-threat relocations count as emergency escapes (user 2026-10-02 13:4x).

User decision (AskUserQuestion answer, verbatim label): 「逃走も緊急脱出に数える
(Recommended)」 -- 状態異常の敵から逃げるためにテレポートの巻物を読んだ時や階段を
使った時も、既存の緊急脱出の回数に数える。1回の潜行で2回になったら、致命的かどうか
に関わらず帰還する。  Context: 「逃げること自体は正しい。複数回逃げた場合の帰還条件が
怪しい」.

Live 2026-10-02 (Castle 20F, one dive): 13:06:52 ``status-threat:scroll`` 're'
and 13:11:39/40 ``status-threat:scroll`` 'rd' (decision 5542 in
jsonlog/autorecover-20261002-131232-loop-detected.bot-decisions.jsonl.gz).
ownership-metrics.jsonl ``town_decisions`` stayed 199 from 13:06:12 to 13:12:13,
so both reads were in the same dive.  Neither counted toward
``_dive_emergencies`` (only ``emergency:*`` reasons did), and no return was latched.
The 13:06 boards are no longer on disk (the decision log rotated and the state
log is truncated per relaunch), so this pin is CONSTRUCTED on the recorded
adjacent-paralyzer board ``tests/fixtures/incident-paralyzer-adjacent-escape.jsonl``
turn 3305879 (Angband, dungeon 1, 19F; the recorded key there is 're'
status-threat:scroll, pinned by test_policy_combat): the
landing boards below are DECLARED CONSTRUCTED (player moved to a remembered floor
grid out of sight of every monster, one teleport scroll fewer).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import hashlib
import unittest
from dataclasses import replace

from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import READ_KEY, UP_STAIRS_KEY

import test_policy_combat

# Module attribute, not a name import: unittest must not re-collect the class.
_Recorded = test_policy_combat.RecordedAdjacentParalyzerEscapeTest

ESCAPE_TURN = 3305879
# R9: digest of the fixture bytes with CRLF normalized to LF.
FIXTURE_SHA256 = "783f9d9c9eb8a3a184a7c6d072d260e4d6cb0d8f658f54bf3d8153856b541a7e"


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class StatusThreatEscapeCountsEmergencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Recorded.setUpClass()
        cls.knowledge = _Recorded.KNOWLEDGE
        cls.board = _Recorded.snapshots[ESCAPE_TURN]

    def setUp(self):
        self.assertEqual(_sha(_Recorded.FIXTURE), FIXTURE_SHA256)

    # -- constructed boards ------------------------------------------------
    def _landing(self, board, *, turn_offset: int):
        """CONSTRUCTED: the teleport landed out of sight of every monster."""
        player = board.player.position
        far = max(
            (
                position
                for position, grid in board.grids.items()
                if grid.passable
                and not grid.has_monster
                and position.distance_to(player) >= 20
            ),
            key=lambda position: (position.distance_to(player), position.y, position.x),
        )
        inventory = [
            replace(item, count=item.count - 1) if item.is_teleport_scroll else item
            for item in board.inventory
        ]
        return replace(
            board,
            player=replace(board.player, position=far),
            visible_monsters=[],
            detected_monsters=[],
            inventory=inventory,
            turn=board.turn + turn_offset,
        )

    def _escape(self, policy, board):
        key = policy.choose_key(board)
        self.assertEqual(
            (key, policy.last_reason), (READ_KEY + "e", "status-threat:scroll")
        )

    # -- pins --------------------------------------------------------------
    def test_one_status_threat_teleport_counts_but_does_not_return(self):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        self._escape(policy, self.board)
        policy.choose_key(self._landing(self.board, turn_offset=10))
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertFalse(policy._returning_to_town)

    def test_unrelocated_read_is_not_counted(self):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        self._escape(policy, self.board)
        # The same board again: the read had no observed effect.
        policy.choose_key(replace(self.board, turn=self.board.turn + 1))
        self.assertEqual(policy._dive_emergencies, 0)

    def test_second_status_threat_teleport_of_a_dive_returns_to_town(self):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        self._escape(policy, self.board)
        policy.choose_key(self._landing(self.board, turn_offset=10))
        # CONSTRUCTED: the paralyzer finds us again on the same floor.
        self._escape(policy, replace(self.board, turn=self.board.turn + 20))
        landing = self._landing(self.board, turn_offset=30)
        key = policy.choose_key(landing)
        self.assertEqual(policy._dive_emergencies, 2)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")
        recall = next(item for item in landing.inventory if item.is_recall_scroll)
        self.assertEqual(key, READ_KEY + recall.slot)

    def test_status_threat_stairs_then_teleport_returns_to_town(self):
        # CONSTRUCTED: an up staircase under the player on the recorded board,
        # and the paralyzer one step further away (distance 2: still a status
        # threat, but not the adjacent case that reads a scroll first).
        here = self.board.player.position
        paralyzer = next(m for m in self.board.visible_monsters if m.race_id == 280)
        approach = Position(paralyzer.position.y, paralyzer.position.x + 1)
        self.assertTrue(self.board.grids[approach].passable)
        on_stairs = replace(
            self.board,
            grids={
                **self.board.grids,
                here: replace(self.board.grids[here], has_up_stairs=True),
            },
            visible_monsters=[
                replace(m, position=approach, distance=2) if m is paralyzer else m
                for m in self.board.visible_monsters
            ],
        )
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        key = policy.choose_key(on_stairs)
        self.assertEqual(
            (key, policy.last_reason), (UP_STAIRS_KEY, "status-threat:stairs")
        )
        # CONSTRUCTED: one floor up, the paralyzer is next to us again.
        upper = replace(
            self.board,
            floor_key=(self.board.floor_key[0], self.board.floor_key[1] - 1, 0),
            turn=self.board.turn + 10,
        )
        self._escape(policy, upper)
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertFalse(policy._returning_to_town)
        policy.choose_key(self._landing(upper, turn_offset=10))
        self.assertEqual(policy._dive_emergencies, 2)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")

    def test_new_dive_resets_the_count(self):
        policy = HengbotPolicy(monrace_knowledge=self.knowledge)
        self._escape(policy, self.board)
        policy.choose_key(self._landing(self.board, turn_offset=10))
        self.assertEqual(policy._dive_emergencies, 1)
        # A new dive begins (previous floor in town): the count restarts.
        policy._floor_key = (0, 0, 0)
        self._escape(policy, replace(self.board, turn=self.board.turn + 20))
        self.assertEqual(policy._dive_emergencies, 0)
        policy.choose_key(self._landing(self.board, turn_offset=30))
        self.assertEqual(policy._dive_emergencies, 1)
        self.assertFalse(policy._returning_to_town)


if __name__ == "__main__":
    unittest.main()
