"""Large-floor decision speed work must not change a parsed board or a decision.

Owner 2026-11-07 (「調べて速くする」): n1-c's viewing screen moved slowly on a
198x66 floor (Orc cave 23F, ~12,000 emitted cells): parse_snapshot,
choose_key and the decision-row facts each made several full-map passes per
decision.  The speed work is pinned two ways on boards recorded live that day
(n1-c life-159 in the dungeon, n1-b life-337 arriving in town):

* every parsed board equals, field for field and in grid order, the board the
  per-record decode path (``_decode_grid_map`` + ``_grid_state_from_record``,
  the former loop) produces, with the former unsafe_rows decode;
* replaying the boards on a fresh policy yields the key/reason trajectory and
  the decision-row facts recorded with main b090fed57, before any of it.
"""
import tests  # noqa: F401  -- live runtime-file isolation

import dataclasses
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import model
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _capture_decision_facts, _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import BOARD_SNAPSHOT_TYPES, GridState, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import (
    load_damaging_terrain_elements, load_damaging_terrain_ids, load_deep_damaging_terrain_ids)
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
GAME = Path("C:/hengband")
EDIT = GAME / "lib" / "edit"
CAPTURES = ("dungeon", "town")
GRID_FIELDS = [field.name for field in dataclasses.fields(GridState)]
_MONRACE = None


def _monrace():
    global _MONRACE
    if _MONRACE is None:
        _MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    return _MONRACE


def _boards(capture):
    path = FIXTURES / f"big-floor-1107-{capture}.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.startswith("{")]


def _reference_grids(data, protocol):
    """The former parse loop: decode every cell to a record, then a state."""
    grids = {}
    for record in model._decode_grid_map(data["grid_map"], protocol):
        grid = model._grid_state_from_record(record)
        grids[grid.position] = grid
    return grids


def _reference_unsafe_rows(data):
    width = int(data["floor"]["width"])
    if data["grid_map"].get("unsafe_rows") is None:
        return None
    return tuple(
        tuple(bool((int(row[x // 4], 16) >> (x % 4)) & 1) for x in range(width))
        for row in data["grid_map"]["unsafe_rows"]
    )


def _policy(directory):
    town_maps = {}
    for town_index in range(1, 6):
        path = find_town_map(town_index, GAME)
        if path is not None:
            town_maps[town_index - 1] = parse_town_map(path)
    policy = ConservativePolicy(
        town_map=town_maps.get(0),
        town_maps=town_maps,
        wilderness_map=load_wilderness_map(find_wilderness_definition(GAME)),
        dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"),
        monrace_knowledge=_monrace(),
        damaging_terrain_ids=load_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc"),
        damaging_terrain_elements=load_damaging_terrain_elements(
            EDIT / "TerrainDefinitions.jsonc"),
        deep_damaging_terrain_ids=load_deep_damaging_terrain_ids(
            EDIT / "TerrainDefinitions.jsonc"),
        quest_knowledge=load_quest_knowledge(EDIT / "quests"),
        quest_strategies=load_quest_strategies(ROOT / "strategy" / "quests"),
        exploration_ledger_path=directory / "exploration-ledger.json",
        baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
    )
    policy._crossarea_fundraising_enforced = True  # live argv
    policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
    return policy


def replay(capture):
    """[key, reason, facts digest] per board, as the live loop decides it."""
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory))
        rows = []
        for data in _boards(capture):
            if data.get("type") not in BOARD_SNAPSHOT_TYPES:
                # A knowledge/store reply line, consumed as the driver does.
                _consume_response_sequence(
                    [json.dumps(data, ensure_ascii=False) + "\n"], policy,
                    lambda _key, **_kw: True, _monrace(),
                    knowledge_ledger_path=Path(directory) / "knowledge.jsonl")
                continue
            snapshot = parse_snapshot(data, _monrace())
            if not rows:
                policy.prime(snapshot)
            key = policy.validate_read_key(snapshot, policy.choose_key(snapshot))
            facts = _capture_decision_facts(snapshot, policy)
            digest = hashlib.sha256(json.dumps(
                facts, sort_keys=True, default=repr, ensure_ascii=False,
            ).encode()).hexdigest()[:16]
            rows.append([key, policy.last_reason, digest])
            if policy.last_reason == "periodic:skill-exp-knowledge":
                # The ~f reply the live driver would consume next.
                policy.consume_skill_knowledge({
                    "knowledge": {"skills": [{"id": 1, "exp": 4000},
                                             {"id": 3, "exp": 2000}]},
                    "player": {"level": snapshot.player.level},
                })
        return rows


class GridMapFastPathTest(unittest.TestCase):
    def assert_same_board(self, data):
        protocol = model.snapshot_protocol_version(data)
        parsed = parse_snapshot(data, _monrace())
        expected = _reference_grids(data, protocol)
        # Report the first differing cell: a whole-list diff of ~12,000
        # GridStates would take minutes.
        self.assertEqual(len(parsed.grids), len(expected))
        for got, wanted in zip(parsed.grids.items(), expected.items()):
            if got != wanted:
                self.fail(f"first differing cell: {got!r} != {wanted!r}")
        for grid in parsed.grids.values():
            if list(vars(grid)) != GRID_FIELDS:
                self.fail(f"field order differs at {grid.position}: {list(vars(grid))}")
        return parsed

    def test_recorded_large_boards_parse_as_the_record_path(self):
        for capture in CAPTURES:
            for index, data in enumerate(_boards(capture)):
                if (data.get("type") not in BOARD_SNAPSHOT_TYPES
                        or not isinstance(data.get("grid_map"), dict)):
                    continue  # a reply line or a store page
                with self.subTest(capture=capture, board=index):
                    parsed = self.assert_same_board(data)
                    self.assertGreater(len(parsed.grids), 1000)
                    self.assertEqual(parsed.unsafe_rows, _reference_unsafe_rows(data))

    def test_sidecars_duplicates_and_empty_runs_parse_as_the_record_path(self):
        board = _boards("dungeon")[0]
        for protocol in (2, 3):
            data = json.loads(json.dumps(board))
            data["protocol_version"] = protocol
            grid_map = data["grid_map"]
            if protocol == 2:
                # Protocol 2 decodes slot 1 as CAVE bits.
                for entry in grid_map["palette"]:
                    entry[1] = 0b101010101
            y, x0, _length, palette_index = grid_map["runs"][0]
            grid_map["runs"][1:1] = [
                [y, x0, 0, palette_index],  # empty run
                [y, x0, 2, len(grid_map["palette"]) - 1],  # re-emitted cells
            ]
            grid_map["cells"].append({"y": y, "x": x0 + 1, "o": 2, "t": [7, 9],
                                      "s": 3, "q": 5, "b": 4, "p": 1})
            with self.subTest(protocol=protocol):
                self.assert_same_board(data)


class BigFloorReplayPinTest(unittest.TestCase):
    def test_decisions_and_facts_match_the_recorded_baseline(self):
        baseline = json.loads(
            (FIXTURES / "big-floor-1107-baseline.json").read_text(encoding="utf-8"))
        for capture in CAPTURES:
            with self.subTest(capture=capture):
                self.assertEqual(replay(capture), baseline[capture])


if __name__ == "__main__":
    unittest.main()
