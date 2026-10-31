"""Pins for the Original32 (tiles=3/4) fields of the spectator tile layer.

A recorded protocol-4 board (dungeon-1031.json.gz, death-return board 0: a
level-48 floor with gargoyles, bolts on the floor and a pile of gold) is
projected through the real writer; constructed variants pin the item identity
rules. Only received fields are copied: found_item_ids prints sval/flavor_id/
artifact_id exactly as the item's name reveals them.
"""
import tests  # noqa: F401

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import cli
from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter
from hengbot.spectator_tiles import INDEX_ALPHABET, spectator_tile_player, spectator_tiles

FIXTURE = Path(__file__).with_name("fixtures") / "dungeon-1031.json.gz"


def recorded_board():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)["death-return"]["boards"][0]


def screen_for(state, width=120, height=50):
    """A blank screen whose one '@' puts the panel at floor (12, 8) for this board."""
    lines = [" " * width for _ in range(height)]
    row, col = 1 + 35, 13 + 20
    lines[row] = " " * col + "@" + " " * (width - col - 1)
    return {"width": width, "height": height, "lines": lines}


def cell_entry(tiles, y, x):
    """(palette entry, palette_ext entry) drawn at floor (y, x)."""
    row = tiles["rows"][y - tiles["map"][0]]
    index = INDEX_ALPHABET.index(row[x - tiles["map"][1]])
    return tiles["palette"][index], (tiles.get("palette_ext") or [None] * (index + 1))[index]


class RecordedBoardTest(unittest.TestCase):
    def test_recorded_board_carries_items_monsters_and_floor_seed(self):
        state = recorded_board()
        before = copy.deepcopy(state)
        tiles = spectator_tiles(state, screen_for(state))
        self.assertEqual(state, before)
        player = state["player"]
        # '@' at screen (36, 33): the panel's top-left floor cell, dungeon level 48, no quest.
        self.assertEqual(tiles["map"], [player["y"] - 35, player["x"] - 20, 48, 0])
        self.assertEqual(tiles["map"][:2], [12, 8])
        self.assertEqual(len(tiles["palette_ext"]), len(tiles["palette"]))
        self.assertTrue(all(len(entry) == 5 for entry in tiles["palette"]))
        # Bolts (tval 18) whose name shows the kind: sval 1, no flavor, no artifact.
        for y, x in ((28, 69), (32, 59), (32, 61), (32, 62), (32, 63)):
            entry, ext = cell_entry(tiles, y, x)
            self.assertEqual(entry[3], 18)
            self.assertEqual(ext, [1, None, None])
        # Gold has no found_item_ids record: the page falls back to the '$' picture.
        entry, ext = cell_entry(tiles, 15, 68)
        self.assertEqual((entry[3], ext), (127, None))
        # The apparent race of a visible gargoyle, and the player cell.
        self.assertEqual(cell_entry(tiles, 28, 31)[0][2], 528)
        self.assertTrue(cell_entry(tiles, player["y"], player["x"])[0][4])

    def test_writer_adds_tile_player_beside_unchanged_player_names(self):
        state = recorded_board()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=lambda: 1000)

            class Policy:
                _spectator_sex_title = "女性"
                _target_dungeon_id = None

            # No monster knowledge is needed for these writer fields.
            snapshot = parse_snapshot(dict(state, visible_monsters=[], detected_monsters=[]), {})
            self.assertTrue(writer.observe(snapshot, "6", "pin", 1, screen_for(state),
                                           state_line=json.dumps(state), policy=Policy()))
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written["player"], {"race": "Zombie", "class": "Warrior"})
            self.assertEqual(written["tile_player"], {"class_id": 0, "sex_id": 0})
            self.assertEqual(written["tiles"]["palette_ext"],
                             spectator_tiles(state, screen_for(state))["palette_ext"])


class ItemIdentityTest(unittest.TestCase):
    def board(self, visible, found, ids, **player):
        state = {
            "protocol_version": 4,
            "player": dict({"y": 5, "x": 5}, **player),
            "floor": {"level": 3, "quest_id": 7},
            "grid_map": {"palette": [[1, 0, 0, 1]], "runs": [[5, 5, 3, 0]],
                         "cells": [{"y": 5, "x": 6, "o": len(visible), "t": visible}],
                         "found_items": [[5, 6, len(found), *found]],
                         "found_item_ids": [[5, 6, *ids]]},
        }
        screen = {"width": 20, "height": 4, "lines": [" " * 20, " " * 13 + "@" + " " * 6, " " * 20, " " * 20]}
        return spectator_tiles(state, screen)

    def test_flavor_and_artifact_ids_pass_through(self):
        tiles = self.board([75], [75], [{"flavor_id": 214}])
        self.assertEqual(tiles["map"], [5, 5, 3, 7])
        # Entries: the player cell, the item cell, the empty floor cell.
        self.assertEqual(tiles["palette_ext"], [None, [None, 214, None], None])
        tiles = self.board([23], [23], [{"sval": 16, "ego_id": 3, "artifact_id": 25}])
        self.assertEqual(tiles["palette_ext"], [None, [16, None, 25], None])

    def test_same_tval_different_kind_get_separate_palette_entries(self):
        state = {
            "protocol_version": 4, "player": {"y": 5, "x": 5}, "floor": {},
            "grid_map": {"palette": [[1, 0, 0, 1]], "runs": [[5, 5, 3, 0]],
                         "cells": [{"y": 5, "x": 6, "o": 1, "t": [75]}, {"y": 5, "x": 7, "o": 1, "t": [75]}],
                         "found_items": [[5, 6, 1, 75], [5, 7, 1, 75]],
                         "found_item_ids": [[5, 6, {"sval": 1}], [5, 7, {"sval": 2}]]},
        }
        screen = {"width": 20, "height": 4, "lines": [" " * 20, " " * 13 + "@" + " " * 6, " " * 20, " " * 20]}
        tiles = spectator_tiles(state, screen)
        self.assertEqual(tiles["rows"][0][:3], "ABC")
        self.assertEqual(tiles["palette"][1], tiles["palette"][2])
        self.assertEqual(tiles["palette_ext"], [None, [1, None, None], [2, None, None]])

    def test_gold_on_top_disagreeing_lists_and_unnamed_items_have_no_identity(self):
        for visible, found, ids in (([127, 75], [75], [{"sval": 1}]),   # gold drawn on top
                                    ([75], [80], [{"sval": 1}]),         # lists disagree
                                    ([75], [75], [None]),                # hallucination record
                                    ([75], [75], [{"sval": "1"}]),       # not an ID
                                    ([75], [75], [{}])):                 # nothing printed
            with self.subTest(visible=visible, found=found, ids=ids):
                self.assertNotIn("palette_ext", self.board(visible, found, ids))

    def test_hallucination_hides_the_item_identity(self):
        tiles = self.board([75], [75], [{"sval": 1}], status={"hallucinated": True})
        self.assertNotIn("palette_ext", tiles)
        self.assertTrue(all(entry[3] is None for entry in tiles["palette"]))


class TilePlayerTest(unittest.TestCase):
    def test_sex_titles_and_class_bounds(self):
        self.assertEqual(spectator_tile_player(16, "男性"), {"class_id": 16, "sex_id": 1})
        self.assertEqual(spectator_tile_player(0, "Female"), {"class_id": 0, "sex_id": 0})
        self.assertEqual(spectator_tile_player(28, "Male"), {"class_id": 28, "sex_id": 1})
        self.assertEqual(spectator_tile_player(29, None), {})
        self.assertEqual(spectator_tile_player(None, "不明"), {})

    def test_character_response_sets_the_sex_title(self):
        from tests import test_spectator as replay
        from tests.test_home_light_alternation import _fresh_policy
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _fresh_policy(root)
            self.assertIsNone(getattr(policy, "_spectator_sex_title", None))
            raw = json.loads(replay._recorded_lines(1)[0])
            response = dict(copy.deepcopy(raw), type="character", character={"sex": "男性"})
            self.assertEqual(cli._dispatch_response_lines([json.dumps(response)], policy, lambda key: None), 1)
            self.assertEqual(policy._spectator_sex_title, "男性")
            writer = SpectatorWriter(root / "spectate.json")
            self.assertTrue(writer.observe(parse_snapshot(raw, {}), "5", "pin", 1, None,
                                           state_line=json.dumps(raw), policy=policy))
            written = json.loads((root / "spectate.json").read_text(encoding="utf-8"))
            self.assertEqual(written["tile_player"]["sex_id"], 1)


if __name__ == "__main__":
    unittest.main()
