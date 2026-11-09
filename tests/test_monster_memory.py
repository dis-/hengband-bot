"""The unified out-of-sight monster memory (monster_memory, maintainability review 1109 段2)."""

from __future__ import annotations

import pickle
import unittest
from types import SimpleNamespace

from hengbot import monster_memory
from hengbot.model import MonsterState, Position

FLOOR = ("dungeon", 1, 0, 10)
OTHER_FLOOR = ("dungeon", 1, 0, 11)
KIND = monster_memory.Kind("_test_memory")
SHOWN_KEEPS = monster_memory.Kind("_test_shown_keeps", window_while_shown=False)


def monster(index, y, x, race=7, asleep=False):
    return MonsterState(index=index, position=Position(y, x), hp=10, max_hp=10, distance=0,
                        friendly=False, pet=False, asleep=asleep, name=f"m{index}", race_id=race)


def board(turn, visible=(), floor=FLOOR, at=Position(5, 5), in_town=False, level=10):
    return SimpleNamespace(turn=turn, floor_key=floor, in_town=in_town, dungeon_level=level,
                           visible_monsters=list(visible), detected_monsters=[], messages=[],
                           player=SimpleNamespace(position=at))


class Policy:
    pass


def never_gone(policy, snapshot, monster):
    return False


def shown(policy, snapshot):
    return snapshot.visible_monsters


class ObserveRememberedTest(unittest.TestCase):
    def test_out_of_sight_at_last_cell_with_distance(self):
        policy = Policy()
        orc = monster(3, 5, 9)
        monster_memory.observe(policy, board(100, [orc]), KIND, shown, never_gone)
        self.assertEqual(monster_memory.remembered(policy, board(110, [orc]), KIND), [])
        (out,) = monster_memory.remembered(policy, board(110, at=Position(5, 1)), KIND)
        self.assertEqual((out.index, out.position, out.distance), (3, Position(5, 9), 8))

    def test_window_and_gone_and_floor(self):
        policy = Policy()
        orc = monster(3, 5, 9)
        monster_memory.observe(policy, board(100, [orc]), KIND, shown, never_gone)
        window = monster_memory.UNSEEN_GAME_TURNS
        monster_memory.observe(policy, board(100 + window), KIND, shown, never_gone)
        self.assertEqual(len(monster_memory.remembered(policy, board(100 + window), KIND)), 1)
        monster_memory.observe(policy, board(101 + window), KIND, shown, never_gone)
        self.assertEqual(monster_memory.remembered(policy, board(101 + window), KIND), [])

        monster_memory.observe(policy, board(100, [orc]), KIND, shown, never_gone)
        monster_memory.observe(policy, board(101), KIND, shown, lambda *_: True)
        self.assertEqual(monster_memory.entries(policy, board(101), KIND), {})

        monster_memory.observe(policy, board(100, [orc]), KIND, shown, never_gone)
        self.assertEqual(monster_memory.entries(policy, board(101, floor=OTHER_FLOOR), KIND), {})
        monster_memory.observe(policy, board(101, in_town=True, level=0), KIND, shown, never_gone)
        self.assertIsNone(getattr(policy, KIND.attribute))

    def test_window_while_shown_is_a_parameter(self):
        window = monster_memory.UNSEEN_GAME_TURNS
        orc = monster(3, 5, 9)
        for kind, kept in ((KIND, False), (SHOWN_KEEPS, True)):
            policy = Policy()
            monster_memory.observe(policy, board(100, [orc]), kind, shown, never_gone)
            # Shown again but not remembered again (the owner's predicate declines it).
            monster_memory.observe(policy, board(101 + window, [orc]), kind,
                                   lambda *_: [], never_gone)
            self.assertEqual(bool(monster_memory.entries(policy, board(0), kind)), kept, kind)

    def test_remembered_keep_filter(self):
        policy = Policy()
        monster_memory.observe(policy, board(100, [monster(3, 5, 9), monster(4, 6, 9)]), KIND,
                               shown, never_gone)
        kept = monster_memory.remembered(policy, board(101), KIND,
                                         keep=lambda policy, snapshot, m: m.index == 4)
        self.assertEqual([m.index for m in kept], [4])

    def test_pickle_round_trip_keeps_the_attribute(self):
        policy = Policy()
        monster_memory.observe(policy, board(100, [monster(3, 5, 9)]), KIND, shown, never_gone)
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(getattr(restored, KIND.attribute), getattr(policy, KIND.attribute))
        self.assertEqual(len(monster_memory.remembered(restored, board(101), KIND)), 1)

    def test_owner_attributes_are_the_old_names(self):
        # Pickled policies (town-arrival checkpoints, recorded fixtures) hold these names.
        self.assertEqual(monster_memory.SLEEPER_REACH.attribute, "_sleeper_reach_memory")


if __name__ == "__main__":
    unittest.main()
