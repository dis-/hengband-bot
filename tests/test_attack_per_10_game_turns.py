"""Attack power is judged per 10 game turns (owner 2026-11-19).

Owner 2026-11-19, verbatim: 「攻撃力の判定を1行動あたりではなく、10ゲームターンあたりのダメージで
評価して」, and on the scope 「攻撃力の判定すべて」.  One reader, attack_expectation.per_10_game_turns:
the per-action figure times the actions 10 game turns hold at the speed (core/speed-table.cpp
extract_energy: 10 energy a game turn at +0, 20 at +10, 30 at +20, 38 at +30; an action costs 100,
player-processor.cpp:149).  The equipment comparison already read damage per game time
(speed_valuation.per_game_time, owner 2026-11-17 「時間あたりの打撃」); it is the same arithmetic.

Recorded: the town arrivals of 2026-11-19 (tests/fixtures/quest32-one-turn-kill-1119): n1-a
life-531 (+4, light green), n1-b life-411 (+25, light green), n1-c life-217 (+16 yellow: a timed
haste on a permanent +6).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import attack_expectation, speed_valuation
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119"


def recorded(name):
    scratch = tempfile.TemporaryDirectory()
    policy, _, steps = load(FIXTURES / name, Path(scratch.name))
    return scratch, policy, steps[0][1]()


class ReaderTest(unittest.TestCase):
    def test_the_energy_table(self):
        # +0, +10, +20, +30, +4, +25 (speed-table.cpp).
        found = [speed_valuation.per_10_game_turns_at(100.0, speed)
                 for speed in (110, 120, 130, 140, 114, 135)]
        self.assertEqual(found, [100.0, 200.0, 300.0, 380.0, 140.0, 350.0])

    def test_the_loadout_comparison_is_the_same_arithmetic(self):
        # speed_valuation.per_game_time reads the loadout's permanent speed through it.
        for speed in (105, 110, 116, 126, 135, 150):
            metrics = SimpleNamespace(player_speed=speed, speed_bonus=0)
            self.assertEqual(speed_valuation.per_game_time(231.8, metrics),
                             speed_valuation.per_10_game_turns_at(231.8, speed))

    def test_the_speeds_of_the_recorded_boards(self):
        for name, current, permanent, hasted, always in (
                ("n1a-531", 114, 114, 124, 124),
                ("n1b-411", 135, 135, 145, 145),   # +10 or more doses too (owner 2026-11-19 「+10 以上でも飲んで読む」)
                ("n1c-217", 126, 116, 126, 126)):  # the yellow +16 is a timed haste
            scratch, policy, board = recorded(name)
            with scratch:
                self.assertEqual(
                    (board.player.speed, attack_expectation.permanent_speed(board),
                     attack_expectation.hasted_speed(board), attack_expectation.always_hasted_speed(board)),
                    (current, permanent, hasted, always), name)
                # The board's speed by default, the named speed otherwise.
                self.assertEqual(attack_expectation.per_10_game_turns(policy, board, 100.0),
                                 speed_valuation.per_10_game_turns_at(100.0, current))
                self.assertEqual(attack_expectation.per_10_game_turns(policy, board, 100.0, speed=permanent),
                                 speed_valuation.per_10_game_turns_at(100.0, permanent))


if __name__ == "__main__":
    unittest.main()
