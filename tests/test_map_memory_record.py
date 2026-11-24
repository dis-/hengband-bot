"""The floor's map memory carried across a bot restart (map_memory_record, n1-c life-221 2026-11-24), recorded.

n1-c life-221 (Angband 100F, 2026-11-24 09:54): a deploy restarted the bot; the new process had no
map memory (the remembered grids ``_with_grid_memory`` merges under the board), the ground west of
the vault went unshown, and the battle found no stand on the Serpent's rays (``rays=0``) while the
floor's map discs read the player covered.  Owner: 「長期戦になる99F 100Fにおいて無駄な行動は許されない」.

Fixture finale-hold-pocket-n1c-221-1124 (tests/test_finale_hold_loop_1124_recorded: the 100F floor
from the arrival through the restart, replayed open-loop by tests/support/finale_416 with the same
DECLARED constructed state).  The record file is the one the replay's own ``choose_key`` exits
wrote; at the restart's board the map memory is the one a fresh process holds (DECLARED: the policy
keeps its other state -- only the map memory is the restart's subject here), and the first board
after it restores the record.  Compared with the recorded restart (the memory lost, no stand on any
of the Serpent's rays): the rays have stands on the restored ground, and the map is not cast again.

The unit cases build a fresh policy (tests.support.recorded ``_policy``) beside the record of
another: the same floor restores it; another floor, an earlier game turn, or a record left off a
dungeon floor (town) restores nothing.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, angband_finale_battle, map_memory_record, sealed_pocket
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT, _policy

FIXTURE = "finale-hold-pocket-n1c-221-1124.jsonl.gz"
RESTART = 2768   # the boards before the 09:54 restart (tests/test_finale_hold_loop_1124_recorded)
WINDOW = 20


class RestartRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        path = Path(scratch.name) / map_memory_record.FILE_NAME
        seen = []
        held = {}

        def prepare(policy, board):
            angband_finale.memory(policy).restore_mana_used = 0
            sealed_pocket._memory(policy, board).uses.clear()
            policy._map_memory_record_path = path
            if len(seen) == RESTART:
                held["before"] = set(policy._remembered_grids)
                held["recorded"] = set(map_memory_record.load(path)["grids"])
                # DECLARED: the 09:54 restart -- the map memory as a fresh process holds it.
                policy._remembered_grid_region = None
                policy._remembered_grids = {}
                policy._remembered_grid_signatures = {}
                policy._remembered_grid_sources = {}
                policy._map_memory_record = None
                policy._map_memory_record_read = False
                target = angband_finale_battle.target_monster(board)
                aim = (target.position.y, target.position.x)
                # What a fresh process without the record sees: the board alone.
                held["stands_lost"] = angband_finale_battle._candidates(policy, board, aim)
            elif len(seen) == RESTART + 1:
                held["restored"] = set(policy._remembered_grids)
                target = angband_finale_battle.target_monster(board)
                aim = (target.position.y, target.position.x)
                merged = policy._with_grid_memory(board)
                held["stands_restored"] = angband_finale_battle._candidates(policy, merged, aim)
            seen.append(board.turn)
            if len(seen) > RESTART:
                held.setdefault("reports", []).append(angband_finale_battle.report(policy))

        rows = finale_416.drive(finale_416.boards(FIXTURE), monrace, prepare=prepare)
        cls.restarted = rows[RESTART:RESTART + WINDOW]
        cls.held = held

    def test_the_restart_restores_the_map_memory(self):
        # The record is the memory of a decision at most SAVE_CADENCE before the restart; the
        # battle held in place, so it is the whole memory.
        self.assertEqual(self.held["recorded"], self.held["before"])
        self.assertGreater(len(self.held["before"]), 1000)
        self.assertLessEqual(self.held["before"], self.held["restored"])

    def test_the_map_is_not_cast_again_and_the_stand_is_chosen(self):
        # The recorded restart (memory lost): no stand on any ray (no_stand "rays=0"), the map
        # once more on the cell (tests/test_finale_hold_loop_1124_recorded).  Restored: the ground
        # west of the vault is known again, the rays have stands, and no map is cast.  (The replay
        # is open-loop: before the restart its own refused walks already held it at the bound, so
        # the keys after it are the same holds as before it, not a walk.)
        self.assertEqual(self.held["stands_lost"], [])
        self.assertTrue(self.held["stands_restored"], self.held["stands_restored"])
        self.assertEqual([row for row in self.restarted if "map-area" in (row[3] or "")], [],
                         self.restarted)
        no_stand = [report["battle"].get("no_stand") for report in self.held["reports"][:WINDOW]
                    if report.get("battle")]
        self.assertFalse(any(text and "rays=0" in text for text in no_stand), no_stand)


class RecordUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        raws = finale_416.boards(FIXTURE)
        cls.boards = [parse_snapshot(copy.deepcopy(raw), cls.monrace) for raw in raws[:200]]

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.path = self.root / map_memory_record.FILE_NAME

    def process(self, name):
        directory = self.root / name
        directory.mkdir()
        policy = _policy(directory, self.monrace)
        policy._map_memory_record_path = self.path
        return policy

    def first_process(self):
        policy = self.process("first")
        for board in self.boards[:-1]:
            policy._with_grid_memory(board)
            map_memory_record.record(policy, board)
        policy._map_memory_record = None   # write the last board's memory now (no cadence wait)
        map_memory_record.record(policy, self.boards[-2])
        return policy

    def test_the_same_floor_restores_the_memory(self):
        first = self.first_process()
        merged = self.process("second")._with_grid_memory(self.boards[-1])
        self.assertLessEqual(set(first._remembered_grids), set(merged.grids))
        unshown = set(first._remembered_grids) - set(self.boards[-1].grids)
        self.assertTrue(unshown)

    def test_another_floor_discards_it(self):
        self.first_process()
        other = dataclasses.replace(self.boards[-1], floor_key=(4, 99, 0))
        second = self.process("second")
        merged = second._with_grid_memory(other)
        self.assertEqual(set(merged.grids), set(other.grids))
        # The record is read once per process: the floor of the record later is not restored.
        second._with_grid_memory(self.boards[-1])
        self.assertEqual(set(second._remembered_grids), set(self.boards[-1].grids))

    def test_an_earlier_turn_discards_it(self):
        self.first_process()
        earlier = dataclasses.replace(self.boards[-1], turn=self.boards[0].turn - 1)
        merged = self.process("second")._with_grid_memory(earlier)
        self.assertEqual(set(merged.grids), set(earlier.grids))

    def test_a_record_left_in_town_holds_nothing(self):
        first = self.first_process()
        town = dataclasses.replace(self.boards[-1], floor_key=(0, 0, 0), town_flag=True)
        first._with_grid_memory(town)
        map_memory_record.record(first, town)
        self.assertIsNone(map_memory_record.load(self.path))
        merged = self.process("second")._with_grid_memory(self.boards[-1])
        self.assertEqual(set(merged.grids), set(self.boards[-1].grids))

    def test_unchanged_memory_is_not_rewritten_and_changes_wait_for_the_cadence(self):
        policy = self.process("first")
        board = self.boards[0]
        policy._with_grid_memory(board)
        map_memory_record.record(policy, board)
        written = self.path.stat().st_mtime_ns
        self.path.unlink()
        map_memory_record.record(policy, board)
        self.assertFalse(self.path.exists())
        policy._remembered_grid_revision += 1
        for _ in range(map_memory_record.SAVE_CADENCE - 1):
            map_memory_record.record(policy, board)
        self.assertFalse(self.path.exists())
        map_memory_record.record(policy, board)
        self.assertTrue(self.path.exists() and written)


if __name__ == "__main__":
    unittest.main()
