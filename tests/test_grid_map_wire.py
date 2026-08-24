from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _decision_record
from hengbot.model import parse_snapshot


FIXTURES = Path(__file__).parent / "fixtures"
FLAG_NAMES = ("mark", "cave_known", "lite", "view", "room", "unsafe")
TERRAIN_NAMES = (
    "building", "can_dig", "door", "down_stairs", "entrance", "floor",
    "has_gold", "los", "move", "permanent", "quest_enter", "quest_exit",
    "stairs", "store", "trap", "tunnel", "up_stairs", "wall",
)
SIDECAR_NAMES = {
    "monster_index": "m", "object_count": "o", "store_number": "s",
    "entrance_dungeon_id": "e", "quest_id": "q", "building_type": "b",
    "building_special": "p",
}


def _load_first_row(name: str) -> dict:
    path = FIXTURES / name
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.loads(next(stream))


def _encode_grid_map(snapshot_data: dict) -> dict:
    palette: list[list[int]] = []
    signatures: list[tuple[int, int, int, int]] = []
    runs: list[list[int]] = []
    cells: list[dict] = []
    for grid in snapshot_data["nearby_grids"]:
        flags = grid.get("flags", {})
        terrain = grid.get("terrain", {})
        signature = (
            int(grid["terrain_id"]),
            sum(bool(flags.get(name, False)) << index for index, name in enumerate(FLAG_NAMES)),
            sum(bool(terrain.get(name, False)) << index for index, name in enumerate(TERRAIN_NAMES)),
            int(bool(grid.get("known", flags.get("known", False)))),
        )
        if signature not in signatures:
            signatures.append(signature)
            palette.append(list(signature))
        palette_index = signatures.index(signature)
        y, x = int(grid["y"]), int(grid["x"])
        if runs and runs[-1][0] == y and runs[-1][1] + runs[-1][2] == x and runs[-1][3] == palette_index:
            runs[-1][2] += 1
        else:
            runs.append([y, x, 1, palette_index])
        cell = {"y": y, "x": x}
        for source, encoded in SIDECAR_NAMES.items():
            if source in grid and int(grid[source]) != 0:
                cell[encoded] = grid[source]
        if int(grid.get("object_count", 0)) != 0:
            cell["t"] = grid.get("object_tvals", [])
        for source, encoded in (
            ("store_number", "s"), ("entrance_dungeon_id", "e"),
            ("quest_id", "q"), ("building_type", "b"),
            ("building_special", "p"),
        ):
            if source in grid:
                cell[encoded] = grid[source]
        if len(cell) > 2:
            cells.append(cell)
    floor = snapshot_data["floor"]
    return {
        "w": int(floor["width"]), "h": int(floor["height"]),
        "palette": palette, "runs": runs, "cells": cells, "unsafe_rows": None,
    }


class GridMapWireTest(unittest.TestCase):
    def test_real_town_and_dungeon_rows_are_cell_equivalent(self):
        fixture_names = (
            "incident-town-oil-stall-turn-712398.jsonl.gz",
            "incident-20260821-loop-capture-rows.jsonl.gz",
        )
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                old_data = _load_first_row(fixture_name)
                old_data["visible_monsters"] = []
                old_data["detected_monsters"] = []
                new_data = copy.deepcopy(old_data)
                new_data["grid_map"] = _encode_grid_map(new_data)
                del new_data["nearby_grids"]
                old_snapshot = parse_snapshot(old_data, {})
                new_snapshot = parse_snapshot(new_data, {})
                self.assertEqual(new_snapshot.grids, old_snapshot.grids)
                self.assertEqual(new_snapshot.grids_observed, old_snapshot.grids_observed)

    def test_present_empty_grid_map_is_observed(self):
        data = _load_first_row("incident-20260821-loop-capture-rows.jsonl.gz")
        data.pop("nearby_grids")
        data["grid_map"] = {
            "w": data["floor"]["width"], "h": data["floor"]["height"],
            "palette": [], "runs": [], "cells": [], "unsafe_rows": None,
        }
        snapshot = parse_snapshot(data, {})
        self.assertEqual(snapshot.grids, {})
        self.assertTrue(snapshot.grids_observed)

    def test_schema_error_is_unobserved_and_visible_in_decision_record(self):
        data = _load_first_row("incident-20260821-loop-capture-rows.jsonl.gz")
        data.pop("nearby_grids")
        data["grid_map"] = {
            "schema_error": True, "w": data["floor"]["width"],
            "h": data["floor"]["height"], "palette": [], "runs": [],
            "cells": [], "unsafe_rows": None,
        }
        snapshot = parse_snapshot(data, {})
        self.assertEqual(snapshot.grids, {})
        self.assertFalse(snapshot.grids_observed)
        self.assertTrue(snapshot.grid_map_schema_error)
        self.assertTrue(_decision_record(snapshot, "5", "test")["grid_map_schema_error"])


if __name__ == "__main__":
    unittest.main()
