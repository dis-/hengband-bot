"""Explicitly constructed protocol-3 boards pin the viewer tile wire format.

Writer pins use a recorded spectator board with only panel/map/player fields
replaced by the constructed board; existing decision replay pins are unchanged.
"""
import tests  # noqa: F401

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter
from hengbot.spectator_tiles import spectator_player, spectator_tiles


def constructed_state():
    return {
        "protocol_version": 3,
        "panel": {"row_min": 10, "col_min": 20},
        "player": {"y": 11, "x": 21, "race_id": 25, "class_id": 16},
        "grid_map": {
            "palette": [[1, 0, 0, 1], [2, 1, 0, 1], [3, 2, 0, 1], [9, 0, 0, 0]],
            "runs": [[10, 18, 3, 0], [10, 21, 1, 1], [10, 22, 1, 2],
                     [10, 23, 1, 0], [10, 24, 1, 0], [10, 25, 1, 3],
                     [11, 20, 3, 0], [12, 20, 3, 0]],
            "cells": [{"y": 10, "x": 23, "m": 7},
                      {"y": 10, "x": 24, "t": [75, 70]},
                      {"y": 10, "x": 26, "m": 7, "t": [80]},
                      {"y": 11, "x": 20, "m": 8}],
            # A remembered floor item outside the visible sidecar is not drawn.
            "found_items": [[11, 22, 1, 80]],
        },
        "visible_monsters": [{"index": 7, "race_id": 42}],
        "detected_monsters": [{"index": 8, "race_id": 43}],
    }


SCREEN = {"height": 4, "width": 20, "lines": [" " * 20, " " * 20, " " * 14 + "@" + " " * 5, " " * 20]}
EXPECTED = {
    "origin": [1, 13],
    "map": [10, 20, 0, 0],
    "palette": [[1, 0, None, None, False], [2, 1, None, None, False],
                [3, 2, None, None, False], [1, 0, 42, None, False],
                [1, 0, None, 75, False], [1, 0, 43, None, False],
                [1, 0, None, None, True]],
    "rows": ["ABCDE..", "FGA...."],
}


class SpectatorTilesTest(unittest.TestCase):
    def test_clipped_map_lighting_monster_item_player_and_empty(self):
        state = constructed_state()
        before = copy.deepcopy(state)
        self.assertEqual(spectator_tiles(state, SCREEN), EXPECTED)
        self.assertEqual(state, before)
        shifted = dict(state, panel={"row_min": 11, "col_min": 21})
        self.assertEqual(spectator_tiles(shifted, dict(SCREEN, lines=[" " * 20, " " * 13 + "@" + " " * 6, " " * 20, " " * 20])), {
            "origin": [1, 13],
            "map": [11, 21, 0, 0],
            "palette": [[1, 0, None, None, True], [1, 0, None, None, False]],
            "rows": ["AB.....", "BB....."],
        })

    def test_hallucinated_or_unknown_monsters_have_no_race(self):
        for change in ("monster", "player", "missing", "unknown"):
            with self.subTest(change=change):
                state = constructed_state()
                if change == "monster":
                    state["visible_monsters"][0]["hallucinated"] = True
                elif change == "player":
                    state["player"]["status"] = {"hallucinated": True}
                elif change == "missing":
                    state["visible_monsters"] = []
                else:
                    state["visible_monsters"][0]["race_id"] = 0
                tiles = spectator_tiles(state, SCREEN)
                symbol = tiles["rows"][0][3]
                self.assertIsNone(tiles["palette"][ord(symbol) - ord("A")][2])
                if change == "player":
                    self.assertTrue(all(row[2:4] == [None, None] for row in tiles["palette"]))

    def test_missing_panel_is_derived_from_this_screen(self):
        state = constructed_state()
        del state["panel"]
        self.assertEqual(spectator_tiles(state, SCREEN), EXPECTED)
        state["panel"] = None
        self.assertEqual(spectator_tiles(state, SCREEN), EXPECTED)

    def test_zero_or_two_map_anchors_omit_even_with_a_state_panel(self):
        for panel in (True, False):
            for line in (" " * 20, " " * 14 + "@@" + " " * 4):
                with self.subTest(panel=panel, line=line):
                    state = constructed_state()
                    if not panel:
                        del state["panel"]
                    screen = dict(SCREEN, lines=["@" * 20, "@" * 13 + " " * 7,
                                                 line, "@" * 20])
                    counts = {}
                    self.assertIsNone(spectator_tiles(state, screen, panel_counts=counts))
                    self.assertEqual(counts, {"player_glyph_count": 1})

    def test_state_panel_must_agree_with_both_derived_coordinates(self):
        for field in ("row_min", "col_min"):
            state = constructed_state()
            state["panel"][field] += 1
            counts = {}
            self.assertIsNone(spectator_tiles(state, SCREEN, panel_counts=counts))
            self.assertEqual(counts, {"mismatch": 1})

    def test_anchor_search_is_clipped_to_the_map_area(self):
        screen = dict(SCREEN, lines=["@" * 21, "@" * 13 + " " * 7 + "@",
                                     "@" * 13 + " @" + " " * 5 + "@",
                                     "@" * 21, "@" * 21])
        self.assertEqual(spectator_tiles(constructed_state(), screen), EXPECTED)

    def test_each_frame_uses_its_own_anchor_and_position(self):
        state = constructed_state()
        del state["panel"]
        counts = {}
        self.assertEqual(spectator_tiles(state, SCREEN, panel_counts=counts), EXPECTED)
        shifted = dict(SCREEN, lines=[" " * 20, " " * 13 + "@" + " " * 6,
                                      " " * 20, " " * 20])
        self.assertEqual(spectator_tiles(state, shifted)["rows"], ["AB.....", "BB....."])
        state["player"].update(y=10, x=20)
        self.assertEqual(spectator_tiles(state, shifted)["rows"][0], "ABCDE..")
        self.assertEqual(counts, {"derived": 1})

    def test_wide_side_panel_glyphs_count_two_screen_columns(self):
        # Live n1-a 2026-10-29: row 7 read "腕力 : 18/80 #@+..."; the '@' at string index 12 is screen column 14.
        state = constructed_state()
        del state["panel"]
        wide = dict(SCREEN, lines=[" " * 20, "腕力" + " " * 9 + "@" + " " * 6,
                                   " " * 20, " " * 20])
        narrow = dict(SCREEN, lines=[" " * 20, " " * 13 + "@" + " " * 6,
                                     " " * 20, " " * 20])
        counts = {}
        self.assertEqual(spectator_tiles(state, wide, panel_counts=counts),
                         spectator_tiles(state, narrow))
        self.assertEqual(counts, {"derived": 1})
        hidden = dict(SCREEN, lines=[" " * 20, "腕力 : 18/80@" + " " * 7, " " * 20, " " * 20])
        self.assertIsNone(spectator_tiles(state, hidden))

    def test_missing_player_position_does_not_invent_an_origin(self):
        state = constructed_state()
        del state["player"]["y"]
        counts = {}
        self.assertIsNone(spectator_tiles(state, SCREEN, panel_counts=counts))
        self.assertEqual(counts, {"player_position": 1})

    def test_overflow_has_fixed_two_digit_indices_and_empty_sentinel(self):
        state = constructed_state()
        state["player"] = {"y": 10, "x": 20}
        state["grid_map"] = {
            "palette": [[i, 0, 0, 1] for i in range(65)],
            "runs": [[10, 20 + i, 1, i] for i in range(65)],
        }
        tiles = spectator_tiles(state, {"width": 80, "height": 3, "lines": [" " * 80, " " * 13 + "@" + " " * 66, " " * 80]})
        self.assertEqual(tiles["index_width"], 2)
        self.assertEqual(len(tiles["palette"]), 65)
        self.assertEqual(tiles["rows"], [
            "AAABACADAEAFAGAHAIAJAKALAMANAOAPAQARASATAUAVAWAXAYAZAaAbAcAdAeAf"
            "AgAhAiAjAkAlAmAnAoApAqArAsAtAuAvAwAxAyAzA0A1A2A3A4A5A6A7A8A9A+A/BA...."])
        state["grid_map"]["runs"].pop()
        self.assertNotIn("index_width", spectator_tiles(state, {"width": 80, "height": 3, "lines": [" " * 80, " " * 13 + "@" + " " * 66, " " * 80]}))

    def test_pref_names_and_unknown_ids(self):
        self.assertEqual(spectator_player({"race_id": 25, "class_id": 0}),
                         {"race": "Zombie", "class": "Warrior"})
        self.assertEqual(spectator_player({"race_id": 19, "class_id": 16}),
                         {"race": "Dark-Elf", "class": "Magic-Eater"})
        self.assertEqual(spectator_player({"race_id": -1, "class_id": 999}), {})
        self.assertEqual(spectator_player({}), {})

    def test_legacy_palette_slot_is_not_a_lighting_symbol(self):
        state = constructed_state()
        state["protocol_version"] = 2
        state["grid_map"]["palette"][0][1] = 99
        self.assertEqual(spectator_tiles(state, SCREEN)["palette"][0][1], 0)


class SpectatorTilesWriterTest(unittest.TestCase):
    def test_snapshot_and_deferred_frame_use_the_same_received_state(self):
        fixture = Path(__file__).with_name("fixtures") / "spectator-board.json"
        state = json.loads(fixture.read_text(encoding="utf-8"))
        state.update({key: value for key, value in constructed_state().items() if key != "player"})
        state["player"].update(constructed_state()["player"])
        # No monster knowledge is needed for these constructed writer fields.
        snapshot = parse_snapshot(dict(state, visible_monsters=[], detected_monsters=[]), {})
        # The recorded board's floor (dungeon level 45, no quest) seeds Original32 variants.
        expected = dict(EXPECTED, map=[10, 20, 45, 0])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=lambda: 1000)
            self.assertTrue(writer.observe(snapshot, "6", "tile-pin", 1, SCREEN,
                                           state_line=json.dumps(state), append_frame=True,
                                           defer_frame=True))
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written["tiles"], expected)
            self.assertEqual(written["player"], {"race": "Zombie", "class": "Magic-Eater"})
            self.assertFalse(writer.frames_path.exists())
            # The state and screen used by the projection cannot be replaced by
            # a later observation while the frame waits for a posted command.
            state["panel"]["row_min"] = 99
            writer.commit_frame()
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8"))
            self.assertEqual(frame, dict(written, frame=1))
            del state["panel"]
            writer.observe(snapshot, "6", "no-panel", 2, SCREEN,
                           state_line=json.dumps(state), append_frame=True)
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(frame["tiles"], expected)
            self.assertEqual(writer.tile_panel_counts, {"state": 1, "derived": 1})
            state["panel"] = {"row_min": 99, "col_min": 20}
            writer.observe(snapshot, "6", "mismatch", 3, SCREEN,
                           state_line=json.dumps(state), append_frame=True)
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertNotIn("tiles", frame)
            self.assertEqual(writer.tile_panel_counts["mismatch"], 1)
            writer.observe(snapshot, "6", "no-screen", 3, None,
                           state_line=json.dumps(state), append_frame=True)
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertNotIn("tiles", frame)
            self.assertNotIn("screen", frame)
            writer.observe(snapshot, "6", "snapshot-only", 4, SCREEN, append_frame=True)
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(frame["player"], {"race": "Zombie", "class": "Magic-Eater"})
            self.assertNotIn("tiles", frame)


if __name__ == "__main__":
    unittest.main()
