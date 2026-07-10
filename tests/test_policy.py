import unittest

from hengbot.model import GridState, MonsterState, PlayerState, Position, Snapshot
from hengbot.policy import ConservativePolicy


def grid(y, x, *, known=True, passable=True, monster=False, downstairs=False):
    pos = Position(y, x)
    return GridState(
        position=pos,
        known=known,
        passable=known and passable,
        wall=known and not passable,
        has_monster=monster,
        has_down_stairs=downstairs,
        has_up_stairs=False,
        unsafe=False,
    )


class ConservativePolicyTest(unittest.TestCase):
    def test_attacks_adjacent_hostile(self):
        player = PlayerState(Position(10, 10), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {Position(10, 10): grid(10, 10), Position(10, 11): grid(10, 11, monster=True)}
        monster = MonsterState(1, Position(10, 11), hp=3, max_hp=3, distance=1, friendly=False, pet=False)
        key = ConservativePolicy().choose_key(Snapshot(player, grids, [monster]))
        self.assertEqual(key, "6")

    def test_moves_toward_downstairs(self):
        player = PlayerState(Position(10, 10), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, downstairs=True),
        }
        key = ConservativePolicy().choose_key(Snapshot(player, grids, []))
        self.assertEqual(key, "6")

    def test_retreats_when_low_hp(self):
        player = PlayerState(Position(10, 10), hp=2, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11),
        }
        monster = MonsterState(1, Position(10, 11), hp=10, max_hp=10, distance=1, friendly=False, pet=False)
        key = ConservativePolicy().choose_key(Snapshot(player, grids, [monster]))
        self.assertEqual(key, "4")

    def test_moves_toward_unknown_frontier(self):
        player = PlayerState(Position(10, 10), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12),
            Position(10, 13): grid(10, 13, known=False),
        }
        key = ConservativePolicy().choose_key(Snapshot(player, grids, []))
        self.assertEqual(key, "6")

    def test_waits_without_a_real_frontier(self):
        player = PlayerState(Position(10, 10), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {
            Position(10, 10): grid(10, 10),
            Position(10, 9): grid(10, 9),
            Position(10, 11): grid(10, 11),
        }
        key = ConservativePolicy().choose_key(Snapshot(player, grids, []))
        self.assertEqual(key, "5")

    def test_prefers_less_visited_frontier(self):
        player = PlayerState(Position(10, 10), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        grids = {
            Position(10, 8): grid(10, 8, known=False),
            Position(10, 9): grid(10, 9),
            Position(10, 10): grid(10, 10),
            Position(10, 11): grid(10, 11),
            Position(10, 12): grid(10, 12, known=False),
        }
        policy = ConservativePolicy()

        self.assertEqual(policy.choose_key(Snapshot(player, grids, [], turn=1)), "4")
        west_player = PlayerState(Position(10, 9), hp=20, max_hp=20, mp=0, max_mp=0, level=1)
        self.assertEqual(policy.choose_key(Snapshot(west_player, grids, [], turn=2)), "6")
        self.assertEqual(policy.choose_key(Snapshot(player, grids, [], turn=3)), "6")


if __name__ == "__main__":
    unittest.main()
