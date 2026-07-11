import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    LOOP_WINDOW,
    _deduplicate_consecutive,
    _is_looping,
    _newest_snapshot,
    _read_last_line,
    _split_complete_lines,
)


def _snap_line(turn, y, x):
    return (
        json.dumps(
            {
                "turn": turn,
                "player": {"y": y, "x": x, "hp": 10, "max_hp": 10},
                "floor": {"dungeon_id": 0, "level": 1},
            }
        )
        + "\n"
    )


class NewestSnapshotTest(unittest.TestCase):
    def test_returns_only_the_latest_of_a_batch(self):
        # A fast monster can emit several prompts before we read; we must act on
        # the newest board, not replay the stale ones (which desyncs our keys).
        batch = [_snap_line(100, 5, 5), _snap_line(110, 5, 6), _snap_line(120, 6, 6)]
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 120)
        self.assertEqual((snap.player.position.y, snap.player.position.x), (6, 6))

    def test_skips_a_malformed_trailing_line(self):
        batch = [_snap_line(100, 5, 5), '{"turn": 110, "player":\n']
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 100)

    def test_returns_none_for_empty_or_all_blank(self):
        self.assertIsNone(_newest_snapshot([]))
        self.assertIsNone(_newest_snapshot(["\n", "   \n"]))


class LoopDetectionTest(unittest.TestCase):
    FLOOR = (2, 1, 0)

    def test_flags_a_two_tile_oscillation(self):
        # The live failure: bouncing between exactly two tiles on one floor.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertTrue(_is_looping(cells))

    def test_ignores_a_healthy_sweep(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 10, 10 + i))  # marching down a corridor
        self.assertFalse(_is_looping(cells))

    def test_does_not_flag_before_the_window_fills(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW - 1):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertFalse(_is_looping(cells))

    def test_floor_change_resets_the_signal(self):
        # Confined tiles but spread across two floors is descent, not a loop.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            floor = (2, 1, 0) if i < LOOP_WINDOW // 2 else (2, 2, 0)
            cells.append((floor, 15, 43))
        self.assertFalse(_is_looping(cells))


class DeduplicateConsecutiveTest(unittest.TestCase):
    def test_drops_only_consecutive_duplicate_snapshots(self):
        lines = ["first\n", "first\n", "second\n", "first\n"]

        self.assertEqual(
            list(_deduplicate_consecutive(lines)),
            ["first\n", "second\n", "first\n"],
        )


class CompleteLineTest(unittest.TestCase):
    def test_buffers_an_incomplete_line(self):
        complete, pending = _split_complete_lines('first\n{"turn":')
        self.assertEqual(complete, ["first\n"])
        self.assertEqual(pending, '{"turn":')

        complete, pending = _split_complete_lines(pending + "1}\n")
        self.assertEqual(complete, ['{"turn":1}\n'])
        self.assertEqual(pending, "")

    def test_once_ignores_an_incomplete_trailing_line(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.jsonl"
            path.write_text('{"turn":1}\n{"turn":', encoding="utf-8")

            self.assertEqual(list(_read_last_line(path)), ['{"turn":1}'])


if __name__ == "__main__":
    unittest.main()
