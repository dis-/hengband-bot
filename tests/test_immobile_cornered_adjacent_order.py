"""The cornered immobile-summoner owner's answer beside a hostile (N3).

This rung asked the refused-melee answer before its melee gate, every other rung
after it.  The two gates are exact complements (attack_expectation.melee_refused),
so combat_answer.adjacent_attack serves it too; this table pins that the order
never showed: every combination of fear, a NO_MELEE dungeon, adjacency and a
ranged answer gives the same (key, reason) the rung's old order gave.
DECLARED CONSTRUCTED: the sealed corridor of test_immobile_summoner_recorded,
the ranged answer stubbed, and the rung's earlier ranged fire stubbed away.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import itertools
import unittest
from dataclasses import replace
from unittest import mock

from hengbot import me_ranged_first
from hengbot.model import Position
from tests import test_immobile_summoner_recorded as recorded


RANGED = "RANGED"
UNSET = "unset"


def expected(afraid, no_melee, adjacent, ranged):
    if afraid or no_melee:
        return (RANGED, UNSET) if adjacent and ranged else (None, UNSET)
    if not adjacent:
        return "6", "summoner:cornered-approach"
    return (RANGED, UNSET) if ranged else ("6", "melee")


class CorneredAdjacentOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recorded.ImmobileSummonerRecordedTest.setUpClass()
        cls.corridor = recorded.ImmobileSummonerRecordedTest("test_constructed_no_exit_also_attacks")

    def answer(self, afraid, no_melee, adjacent, ranged):
        board = self.corridor._corridor()
        x = 14 if adjacent else 10
        board = replace(
            board, player=replace(board.player, position=Position(10, x), afraid=afraid),
            visible_monsters=[replace(board.visible_monsters[0], distance=15 - x)])
        policy = self.corridor._policy(board)
        policy.last_reason = UNSET
        policy._map_predicate_snapshot = board  # as choose_key sets it
        with (mock.patch.object(me_ranged_first, "attack_key",
                                return_value=RANGED if ranged else None)), \
                mock.patch.object(policy, "_ranged_attack_key", return_value=None), \
                mock.patch.object(policy, "_adjacent_ranged_key", return_value=None), \
                mock.patch.object(policy, "_can_fight_in_dungeon", return_value=not no_melee):
            key = policy._immobile_summoner_key(board, list(board.visible_monsters))
        return key, policy.last_reason

    def test_every_combination(self):
        for case in itertools.product((False, True), repeat=4):
            with self.subTest(afraid=case[0], no_melee=case[1], adjacent=case[2], ranged=case[3]):
                key, reason = self.answer(*case)
                self.assertEqual((key if key is None else str(key), reason), expected(*case))


if __name__ == "__main__":
    unittest.main()
