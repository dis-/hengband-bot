"""The Rogue's Magic Mapping as a 周辺感知 (owner 2026-11-27, through ``choose_key``).

Owner 2026-11-27 (verbatim): 「仙術盗賊について。魔法の地図は探索効率を大幅に向上させるので
うまく使うと良いだろう。周辺感知の互換である。」

Game (C:/hengband/src): realm/realm-sorcery.cpp:156-165 casts map_area(DETECT_RAD_MAP), and
spell/spells-util.h:4 DETECT_RAD_MAP is 30, the radius of the staff and the rod of 周辺感知
(cmd-item/cmd-usestaff.cpp:141, cmd-zaprod.cpp:102) and the Scroll of Magic Mapping
(object-use/read/scroll-read-executor.cpp:245).

DECLARED CONSTRUCTED: the boards (a level-20 Rogue with both Sorcery books on a dungeon floor of
open known ground, its mana; the same board as a Warrior and a Magic-Eater), the second book's
list (the rows realm_spells.derived gives for the spells at or below level 20, fail 9%), the next
boards (the posted cast landed: the completed operation's owner, ten game turns later).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace

from policy_fixtures import grid
from test_realm_spells_1126 import board, book, recorded, second_book_record
from hengbot import realm_spells
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position
from hengbot.policy import HengbotPolicy

DETECT = "maa"          # book 1 (slot a), Detect Monsters (a)
MAP = "mba"             # book 2 (slot b), Magic Mapping (a)


def rogue(mp):
    record = second_book_record(mp=mp, level=20)
    for row in record["spell_list"]["spells"]:
        if row["level"] > 20:
            row["status"] = "unknown"      # not yet learnable at level 20
    # Angband (DungeonDefinitions id 1, no DARKNESS): a map's radius is the full 30.
    policy = HengbotPolicy(dungeon_knowledge={1: DungeonInfo(1, "Angband", 1, 127, 30)})
    realm_spells.observe_list(policy, record)
    realm_spells.observe_list(policy, recorded())
    return policy


def wide(snapshot):
    """The board on a wider known floor (5..15 x 5..60) with known stairs."""
    grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 61)}
    # Known stairs both ways: the map's stairs trigger has nothing to find.
    grids[Position(5, 5)] = grid(5, 5, downstairs=True)
    grids[Position(5, 6)] = grid(5, 6, upstairs=True)
    return replace(snapshot, grids=grids)


def drive(policy, snapshot, decisions, *, moves=()):
    """``decisions`` boards through choose_key, each after the previous key landed (its owner
    completed, ten game turns on); ``moves`` puts the player at a position from that decision."""
    keys, turn, moves = [], snapshot.turn, dict(moves)
    for index in range(decisions):
        here = moves.get(index, snapshot.player.position)
        snapshot = replace(snapshot, turn=turn, player=replace(snapshot.player, position=here),
                           completed_operation_owner=policy.last_reason or None,
                           completed_operation_receipt={})
        keys.append((policy.choose_key(snapshot), policy.last_reason))
        turn += 10
    return keys


class MagicMappingTest(unittest.TestCase):
    def test_arrival_detects_then_maps_then_explores(self):
        keys = drive(rogue(60), wide(board(mp=60, level=20, inventory=[book(), book("b", 1)])), 3)
        self.assertEqual(keys[:2], [(DETECT, "realm-spell:new-floor:detect-monsters"),
                                    (MAP, "realm-spell:new-floor:map-area")])
        self.assertFalse(keys[2][1].startswith("realm-spell"), keys)

    def test_no_map_that_would_eat_the_escape_or_detection_mana(self):
        # The order: Teleport 12 held, then Detect Monsters (2) before the map (9 in this list).
        self.assertEqual(realm_spells.order_reserve(
            rogue(40), board(level=20, inventory=[book(), book("b", 1)]),
            realm_spells.MAGIC_MAPPING), 2)
        # After the detection landed the map needs 12 + 9: 20 is short, 21 casts it.
        for mp, mapped in ((20, False), (21, True)):
            with self.subTest(mp=mp):
                keys = drive(rogue(mp), wide(board(mp=mp, level=20,
                                                   inventory=[book(), book("b", 1)])), 2)
                self.assertEqual(keys[0][0], DETECT)
                self.assertEqual(keys[1][0] == MAP, mapped, keys)

    def test_walking_out_of_the_mapped_radius_maps_again(self):
        policy = rogue(80)
        snapshot = wide(board(mp=80, level=20, inventory=[book(), book("b", 1)]))
        keys = drive(policy, snapshot, 5, moves={3: Position(10, 39), 4: Position(10, 41)})
        self.assertEqual([key for key, _ in keys[:2]], [DETECT, MAP])
        self.assertNotEqual(keys[3][0], MAP)      # 29 from where the map was cast: inside
        self.assertEqual(keys[4], (MAP, "realm-spell:outside-mapped-area:map-area"))

    def test_the_mapping_means_serve_the_spell_where_a_staff_would_serve(self):
        # area_mapping's means (the stairs maps of deep_climb and finale_descent, a sealed pocket's,
        # a vault's outside): the spell first, as the 周辺感知 staff or rod.
        from hengbot import area_mapping
        policy = rogue(40)
        snapshot = wide(board(mp=40, level=20, inventory=[book(), book("b", 1)]))
        policy.prime(snapshot)
        self.assertTrue(area_mapping.means_held(policy, snapshot))
        self.assertEqual(area_mapping.deep_climb_key(policy, snapshot), MAP)
        self.assertEqual(policy.last_reason, "area-mapping:deep-climb")
        warrior = replace(snapshot, player=replace(snapshot.player, class_id=0))
        self.assertFalse(area_mapping.means_held(policy, warrior))
        self.assertIsNone(area_mapping.deep_climb_key(policy, warrior))

    def test_warrior_and_magic_eater_do_not_cast(self):
        for class_id in (0, 16):
            with self.subTest(class_id=class_id):
                policy = rogue(60)
                snapshot = wide(board(mp=60, level=20, class_id=class_id,
                                      inventory=[book(), book("b", 1)]))
                keys = drive(policy, snapshot, 2)
                self.assertFalse(any(reason.startswith("realm-spell") for _, reason in keys), keys)


if __name__ == "__main__":
    unittest.main()
