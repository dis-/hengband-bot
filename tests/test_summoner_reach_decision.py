"""Pins: the summoner emergency reads only for a summoner that can summon next turn.

USER DECISION 2026-10-03 06:1x.  Question: the condition of the summoner-reason
emergency teleport (``summoner_open`` in ``_emergency_item``); the death
2026-10-03 05:33 began with one for a ゴールデン・スニッチ-like summoner at
distance 15, no walking path, predicted damage 0.  Offered (recommended):
「届かず無害なら読まない」 -- do not read, do not count a dive emergency.
Answer (verbatim): 「届かず、というのが「次のターン召喚を受ける可能性がない」
という意味であれば1」

So "cannot reach" is: the summoner cannot cast a summon at the player before
the player's next action.  Game rules (src/hengbot/policy_combat.py
``_summoner_may_summon_next_turn`` cites them): a counter-attack target set by
the player's damaging shot reaches from anywhere; otherwise within cdis 18 and
with the player's grid or a PROJECTION grid next to it projectable, from any
grid it can walk to with the actions before its last one in one player turn;
sleep is no bar (it can wake within the turn).

Recorded pin: the death capture's first board 06036357 (the teleport that
landed in the nest): the summoner at distance 15 has no walking path but its
line of fire to the player is open, so it can summon -- the read stays.

DECLARED CONSTRUCTED boards (policy_fixtures): an open lit room 11 x 11 around
the player at (10, 10), a summoner (speed +0, no blows, race unknown) and a
Teleportation scroll; the variants are a known wall column at x = 17
(y 0-20) between them, a one-grid gap in it, the summoner 25 grids away, and
a shot posted at it beforehand.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest

from hengbot.model import SV_SCROLL_TELEPORT, Position, Snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS
from policy_fixtures import grid, hostile, item, player
import test_lethal_unseen_caster_recorded as lethal
from test_lethal_unseen_caster_recorded import A_START
from test_policy import SCROLL

FLOOR = (1, 30, 0)


def _board(*, summoner_at=Position(10, 20), wall=True, gap=None, asleep=False):
    grids = {
        Position(y, x): grid(y, x)
        for y in range(5, 16)
        for x in range(5, 16)
    }
    if wall:
        for y in range(0, 21):
            if gap is not None and y == gap:
                grids[Position(y, 17)] = grid(y, 17)
                continue
            grids[Position(y, 17)] = grid(y, 17, passable=False)
    grids[summoner_at] = grid(summoner_at.y, summoner_at.x, monster=True)
    summoner = hostile(
        1, summoner_at.y, summoner_at.x, hp=80, max_hp=80,
        distance=Position(10, 10).distance_to(summoner_at), can_summon=True,
        asleep=asleep,
    )
    return Snapshot(
        player(10, 10, hp=500, max_hp=500), grids, [summoner],
        floor_key=FLOOR,
        inventory=[item("t", SCROLL, SV_SCROLL_TELEPORT)],
    )


class SummonerReachConstructedTest(unittest.TestCase):
    def _decide(self, board, policy=None):
        policy = policy or HengbotPolicy()
        key = policy.choose_key(board)
        return policy, str(key), policy.last_reason

    def assertNoSummonerEmergency(self, policy, key, reason):
        self.assertNotEqual(key, "rt")
        self.assertNotIn(reason, EMERGENCY_ESCAPE_REASONS)
        self.assertFalse(policy._emergency_escape_pending)
        self.assertNotEqual(policy._last_return_trigger, "emergency-summoner")

    def test_walled_off_summoner_is_no_reason_to_read(self):
        board = _board()
        policy = HengbotPolicy()
        self.assertFalse(
            policy._summoner_may_summon_next_turn(board, board.visible_monsters[0])
        )
        policy, key, reason = self._decide(board, policy)
        self.assertNoSummonerEmergency(policy, key, reason)

    def test_summoner_beyond_spell_range_is_no_reason_to_read(self):
        # cdis 25 now, 24 after the one step its second action allows: > 18.
        board = _board(summoner_at=Position(10, 35), wall=False)
        policy, key, reason = self._decide(board)
        self.assertNoSummonerEmergency(policy, key, reason)

    def test_a_gap_in_the_wall_keeps_the_read(self):
        # Conformance: projectable through the gap (no different before the
        # decision).
        board = _board(gap=10)
        policy, key, reason = self._decide(board)
        self.assertEqual((key, reason), ("rt", "emergency:teleport"))
        self.assertEqual(policy._last_return_trigger, "emergency-summoner")

    def test_a_sleeping_summoner_in_the_open_keeps_the_read(self):
        # Sleep is no bar (monster-status.cpp:116-170: within the sensing
        # radius or in view a sleeper loses sleep every monster turn and can
        # wake before the player's next action).  Conformance: the summoner
        # emergency read sleeping summoners before the decision as well.
        board = _board(gap=10, asleep=True)
        self.assertTrue(board.visible_monsters[0].asleep)
        policy, key, reason = self._decide(board)
        self.assertEqual((key, reason), ("rt", "emergency:teleport"))
        self.assertEqual(policy._last_return_trigger, "emergency-summoner")

    def test_a_summoner_shot_at_keeps_the_read_behind_the_wall(self):
        # The shot posted on the open board (no wall) may have set its
        # counter-attack target: behind the wall it may still summon there.
        policy = HengbotPolicy()
        open_board = _board(wall=False)
        policy._note_summoner_counter_targets(open_board, "f1")
        board = _board()
        policy, key, reason = self._decide(board, policy)
        self.assertEqual((key, reason), ("rt", "emergency:teleport"))


class SummonerReachRecordedTest(lethal._Replay):
    def test_death_trigger_summoner_in_the_open_keeps_the_read(self):
        board, key, reason = self._decide(A_START)
        self.assertEqual((key, reason), self._live(A_START))
        summoners = [m for m in board.visible_monsters if m.can_summon]
        self.assertEqual([(m.race_id, m.distance) for m in summoners], [(1329, 15)])
        self.assertTrue(
            self.policy._summoner_may_summon_next_turn(board, summoners[0])
        )
        self.assertEqual(self.policy._last_return_trigger, "emergency-summoner")


if __name__ == "__main__":
    unittest.main()
