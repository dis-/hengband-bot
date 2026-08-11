import unittest
from pathlib import Path


class NoLiveStateArtifactTest(unittest.TestCase):
    def test_test_modules_do_not_read_mutating_bot_state(self):
        tests = Path(__file__).parent
        forbidden = "bot-state-" + "fixed.jsonl"
        readers = []
        for module in sorted(tests.glob("test_*.py")):
            if forbidden in module.read_text(encoding="utf-8"):
                readers.append(module.name)
        self.assertEqual(
            readers,
            [],
            "tests must use frozen fixtures, never jsonlog's mutating bot state",
        )
