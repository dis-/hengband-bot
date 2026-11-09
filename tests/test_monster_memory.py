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

    def test_remembered_keeps_the_order_shown(self):
        policy = Policy()
        monster_memory.observe(policy, board(100, [monster(4, 6, 9), monster(3, 5, 9)]), KIND,
                               shown, never_gone)
        monster_memory.observe(policy, board(101, [monster(4, 6, 8)]), KIND, shown, never_gone)
        self.assertEqual([m.index for m in monster_memory.remembered(policy, board(102), KIND)],
                         [4, 3])

    def test_pickle_round_trip_keeps_the_attribute(self):
        policy = Policy()
        monster_memory.observe(policy, board(100, [monster(3, 5, 9)]), KIND, shown, never_gone)
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(getattr(restored, KIND.attribute), getattr(policy, KIND.attribute))
        self.assertEqual(len(monster_memory.remembered(restored, board(101), KIND)), 1)

    def test_owner_attributes_are_the_old_names(self):
        # Pickled policies (town-arrival checkpoints, recorded fixtures) hold these names.
        self.assertEqual(monster_memory.SLEEPER_REACH.attribute, "_sleeper_reach_memory")


class LootBlockShapeTest(unittest.TestCase):
    """sleeper_loot_block remembers a group with one turn; a policy pickled before
    monster_memory holds (floor_key, {key: MonsterState}, turn) under the same attribute."""

    def test_legacy_group_reads_as_entries(self):
        policy = Policy()
        orc = monster(3, 5, 9, asleep=True)
        setattr(policy, "_sleeper_loot_block", (FLOOR, {(3, 7): orc}, 100))
        restored = pickle.loads(pickle.dumps(policy))
        kind = monster_memory.LOOT_BLOCK
        self.assertEqual(kind.attribute, "_sleeper_loot_block")
        self.assertEqual(monster_memory.entries(restored, board(101), kind), {(3, 7): (orc, 100)})
        self.assertEqual(monster_memory.entries(restored, board(101, floor=OTHER_FLOOR), kind), {})

    def test_holds_reads_the_legacy_shape(self):
        from hengbot import sleeper_loot_block
        policy = Policy()
        orc = monster(3, 5, 9, asleep=True)
        setattr(policy, sleeper_loot_block.MEMORY, (FLOOR, {(3, 7): orc}, 100))
        self.assertTrue(sleeper_loot_block.holds(policy, board(101)))
        self.assertFalse(sleeper_loot_block.holds(policy, board(101, [orc])))
        self.assertFalse(sleeper_loot_block.holds(policy, board(101, floor=OTHER_FLOOR)))

    def test_store_replaces_the_group(self):
        policy = Policy()
        kind = monster_memory.LOOT_BLOCK
        monster_memory.store(policy, board(100), kind, [monster(3, 5, 9), monster(4, 6, 9)])
        monster_memory.store(policy, board(120), kind, [monster(5, 7, 9)])
        self.assertEqual(list(monster_memory.entries(policy, board(121), kind)), [(5, 7)])


class DisenchantKindTest(unittest.TestCase):
    def test_attribute_and_window_while_shown(self):
        kind = monster_memory.DISENCHANT
        self.assertEqual(kind.attribute, "_disenchant_avoid_seen")
        self.assertFalse(kind.window_while_shown)
        self.assertTrue(monster_memory.SLEEPER_REACH.window_while_shown)


class IdentityTest(unittest.TestCase):
    def test_retreat_veto_life_reexports_the_readers(self):
        from hengbot import retreat_veto_life
        for name in ("UNSEEN_GAME_TURNS", "shown_by_index", "seen_or_ended", "gone",
                     "SHAPE_CHANGE_LINES"):
            self.assertIs(getattr(retreat_veto_life, name), getattr(monster_memory, name), name)
        # Pickled policies name the Threat class in retreat_veto_life.
        self.assertEqual(retreat_veto_life.Threat.__module__, "hengbot.retreat_veto_life")

    def test_seen_or_ended_and_gone(self):
        from hengbot.retreat_veto_life import Threat
        orc = monster(3, 5, 9)
        threat = Threat("orc", 100)
        shown = monster_memory.shown_by_index(board(150, [orc]))
        self.assertFalse(monster_memory.seen_or_ended(board(150, [orc]), (3, 7), threat, shown, 100))
        self.assertEqual(threat.last_seen, 150)
        other = monster(3, 5, 9, race=8)
        shown = monster_memory.shown_by_index(board(160, [other]))
        self.assertTrue(monster_memory.seen_or_ended(board(160, [other]), (3, 7), threat, shown, 150))
        late = board(150 + monster_memory.UNSEEN_GAME_TURNS)
        self.assertIsNone(monster_memory.seen_or_ended(late, (3, 7), threat, {}, 150))
        self.assertTrue(monster_memory.gone(late, (3, 7), threat, {}, 150))
        early = board(149 + monster_memory.UNSEEN_GAME_TURNS)
        self.assertFalse(monster_memory.gone(early, (3, 7), threat, {}, 150))


class FloorMarksTest(unittest.TestCase):
    def test_mark_is_per_floor(self):
        policy = Policy()
        attribute = monster_memory.PARALYSER_LEFT
        gazer = monster(3, 5, 9, race=218)
        self.assertFalse(monster_memory.marked(policy, board(100), attribute, gazer))
        monster_memory.mark(policy, board(100), attribute, [gazer])
        self.assertTrue(monster_memory.marked(policy, board(101), attribute, gazer))
        self.assertFalse(monster_memory.marked(policy, board(101, floor=OTHER_FLOOR), attribute, gazer))
        monster_memory.mark(policy, board(102, floor=OTHER_FLOOR), attribute, [monster(4, 1, 1)])
        self.assertEqual(getattr(policy, attribute), (OTHER_FLOOR, frozenset({(4, 7)})))

    def test_status_latch_is_read_as_a_mark(self):
        policy = Policy()
        gazer = monster(3, 5, 9, race=218)
        setattr(policy, "_status_threat_latch", (FLOOR, frozenset({(3, 218)})))
        self.assertTrue(monster_memory.marked(
            policy, board(100), monster_memory.STATUS_THREAT_LATCH, gazer))
        self.assertEqual(monster_memory.floor_marks(
            policy, board(100, floor=OTHER_FLOOR), monster_memory.STATUS_THREAT_LATCH), frozenset())


if __name__ == "__main__":
    unittest.main()
