"""Telepathy/detection monsters and monsters on unmapped floor reach the tile layer.

Recorded live case (hengband.net n1-b life-281, 2026-10-31, main cfc32e192):
three spectate frames and the boards whose projection reproduces each frame
exactly. The game puts a cell's "m" only in direct view on mapped floor, while
telepathy monsters are listed in detected_monsters with their (y, x); the layer
took races only from "m", so the page drew these monsters as text. The screen
shows every one of them, so drawing them shows only what the player sees.
"""
import tests  # noqa: F401

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter
from hengbot.spectator_tiles import INDEX_ALPHABET, _screen_cells, spectator_tiles

FIXTURE = Path(__file__).with_name("fixtures") / "spectator-esp-monsters-n1b-20261031.json.gz"
# (frame, y, x): the expected entry and the screen glyph the frame shows there.
NAMED = {
    (3251523, 7, 33): ([0, 0, 350, None, False], "o"),   # telepathy, floor never mapped
    (3251607, 8, 21): ([96, 2, 149, None, False], "o"),  # telepathy, mapped floor out of view
    (3251538, 5, 22): ([0, 0, 350, None, False], "o"),   # direct sight, floor never mapped
}


def cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return {case["frame"]: case for case in json.load(stream)["cases"]}


def entry_at(tiles, y, x):
    width = tiles.get("index_width", 1)
    row, col = y - tiles["map"][0], x - tiles["map"][1]
    if not 0 <= row < len(tiles["rows"]) or col < 0:
        return "outside"
    code = tiles["rows"][row][col * width:(col + 1) * width]
    if len(code) < width:
        return "outside"
    if "." in code:
        return None
    index = 0
    for digit in code:
        index = index * 64 + INDEX_ALPHABET.index(digit)
    return tiles["palette"][index]


def listed(state):
    return [monster for field in ("visible_monsters", "detected_monsters") for monster in state[field]]


class EspMonstersTest(unittest.TestCase):
    def test_recorded_named_cells(self):
        recorded = cases()
        for (frame, y, x), (entry, glyph) in NAMED.items():
            with self.subTest(frame=frame, cell=(y, x)):
                case = recorded[frame]
                before = copy.deepcopy(case["state"])
                tiles = spectator_tiles(case["state"], case["screen"])
                self.assertEqual(case["state"], before)
                self.assertEqual(entry_at(tiles, y, x), entry)
                line = case["screen"]["lines"][1 + y - tiles["map"][0]]
                self.assertEqual(dict(_screen_cells(line))[13 + x - tiles["map"][1]], glyph)
                # The recorded frame had no race there.
                old = entry_at(case["frame_tiles"], y, x)
                self.assertTrue(old is None or old[2] is None)

    def test_every_listed_monster_in_the_window_has_its_race(self):
        for frame, case in cases().items():
            tiles = spectator_tiles(case["state"], case["screen"])
            for monster in listed(case["state"]):
                entry = entry_at(tiles, monster["y"], monster["x"])
                if entry != "outside":
                    with self.subTest(frame=frame, monster=monster["index"]):
                        self.assertEqual(entry[2], monster["race_id"])

    def test_cells_without_a_listed_monster_match_the_recorded_frame(self):
        for frame, case in cases().items():
            tiles = spectator_tiles(case["state"], case["screen"])
            occupied = {(monster["y"], monster["x"]) for monster in listed(case["state"])}
            self.assertEqual(tiles["map"], case["frame_tiles"]["map"])
            for row in range(len(tiles["rows"])):
                for col in range(len(tiles["rows"][row]) // tiles.get("index_width", 1)):
                    y, x = tiles["map"][0] + row, tiles["map"][1] + col
                    if (y, x) not in occupied:
                        self.assertEqual(entry_at(tiles, y, x), entry_at(case["frame_tiles"], y, x), (frame, y, x))

    def test_hallucination_hides_every_race(self):
        case = cases()[3251607]
        state = copy.deepcopy(case["state"])
        state["player"].setdefault("status", {})["hallucinated"] = True
        tiles = spectator_tiles(state, case["screen"])
        self.assertTrue(all(entry[2] is None for entry in tiles["palette"]))
        self.assertIsNone(entry_at(tiles, 7, 33))

    def test_writer_frame_carries_the_telepathy_monster(self):
        case = cases()[3251607]
        state = case["state"]
        snapshot = parse_snapshot(dict(state, visible_monsters=[], detected_monsters=[]), {})
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", clock=lambda: 1000)
            self.assertTrue(writer.observe(snapshot, "6", "pin", 1, case["screen"],
                                           state_line=json.dumps(state), append_frame=True))
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8"))
            self.assertEqual(entry_at(frame["tiles"], 8, 21), [96, 2, 149, None, False])


if __name__ == "__main__":
    unittest.main()
