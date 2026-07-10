import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _deduplicate_consecutive, _read_last_line, _split_complete_lines


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
