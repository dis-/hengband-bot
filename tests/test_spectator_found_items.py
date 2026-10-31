"""Detected items on never-mapped floor reach the spectator tile layer.

Recorded live case (hengband.net n1-b life-281, 2026-10-31): the board at turn
1460074 and the frame 3225888 projected from it. The game's grid_map lists the
detected spikes at (5,78), (7,80), (8,111), (13,120) in found_items and
found_item_ids, but has no terrain run for those cells (the map never showed
their floor), so the layer had no entry and the Original32 page drew text.
The game's map still draws such an item (over the unknown terrain NONE, ID 0),
so copying it shows only what the player's map shows.
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

FIXTURE = Path(__file__).with_name("fixtures") / "spectator-found-items-n1b-20261031.json.gz"
DETECTED = {(5, 78): [0, None, None], (7, 80): [0, None, None],
            (8, 111): [0, None, None], (13, 120): [1, None, None]}


def recorded():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def entry_at(tiles, y, x):
    width = tiles.get("index_width", 1)
    code = tiles["rows"][y - tiles["map"][0]][(x - tiles["map"][1]) * width:][:width]
    if "." in code:
        return None, None
    index = 0
    for digit in code:
        index = index * 64 + INDEX_ALPHABET.index(digit)
    return tiles["palette"][index], (tiles.get("palette_ext") or [None] * (index + 1))[index]


class DetectedItemsOnUnmappedFloorTest(unittest.TestCase):
    def test_recorded_detected_spikes_get_unknown_terrain_entries(self):
        data = recorded()
        state = data["state"]
        before = copy.deepcopy(state)
        tiles = spectator_tiles(state, data["screen"])
        self.assertEqual(state, before)
        runs = {(y, x + i) for y, x, n, _ in state["grid_map"]["runs"] for i in range(n)}
        for (y, x), ext in DETECTED.items():
            with self.subTest(cell=(y, x)):
                self.assertNotIn((y, x), runs)  # never-mapped floor
                self.assertEqual(entry_at(tiles, y, x), ([0, 0, None, 10, False], ext))
        # The screen shows each one as the spike glyph '~'.
        for y, x in DETECTED:
            line = data["screen"]["lines"][y - tiles["map"][0] + 1]
            glyphs = dict(_screen_cells(line))  # the side panel has wide glyphs
            self.assertEqual(glyphs[x - tiles["map"][1] + 13], "~")

    def test_everything_else_matches_the_recorded_frame(self):
        data = recorded()
        tiles = spectator_tiles(data["state"], data["screen"])
        before = data["frame_tiles"]
        self.assertEqual(tiles["map"], before["map"])
        for r, row in enumerate(before["rows"]):
            for c in range(len(row)):
                y, x = tiles["map"][0] + r, tiles["map"][1] + c
                if (y, x) in DETECTED:
                    self.assertEqual(entry_at(before, y, x), (None, None))
                else:
                    self.assertEqual(entry_at(tiles, y, x), entry_at(before, y, x), (y, x))

    def test_writer_frame_carries_the_detected_items(self):
        data = recorded()
        state = data["state"]
        snapshot = parse_snapshot(dict(state, visible_monsters=[], detected_monsters=[]), {})
        with TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json", clock=lambda: 1000)
            self.assertTrue(writer.observe(snapshot, "6", "pin", 1, data["screen"],
                                           state_line=json.dumps(state), append_frame=True))
            frame = json.loads(writer.frames_path.read_text(encoding="utf-8"))
            self.assertEqual(entry_at(frame["tiles"], 13, 120), ([0, 0, None, 10, False], [1, None, None]))

    def test_gold_only_and_hallucinated_unmapped_cells_stay_empty(self):
        data = recorded()
        state = copy.deepcopy(data["state"])
        grid_map = state["grid_map"]
        # Gold is never listed in found_items: a detected gold-only cell has no row.
        grid_map["found_items"] = [row for row in grid_map["found_items"] if row[:2] != [5, 78]]
        grid_map["found_item_ids"] = [row for row in grid_map["found_item_ids"] if row[:2] != [5, 78]]
        tiles = spectator_tiles(state, data["screen"])
        self.assertEqual(entry_at(tiles, 5, 78), (None, None))
        self.assertEqual(entry_at(tiles, 7, 80)[0], [0, 0, None, 10, False])
        state["player"].setdefault("status", {})["hallucinated"] = True
        tiles = spectator_tiles(state, data["screen"])
        for y, x in DETECTED:
            self.assertEqual(entry_at(tiles, y, x), (None, None))


if __name__ == "__main__":
    unittest.main()
