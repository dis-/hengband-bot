import unittest
from pathlib import Path


class NoLiveStateArtifactTest(unittest.TestCase):
    def test_test_modules_do_not_read_mutating_bot_state(self):
        tests = Path(__file__).parent
        forbidden = (
            "bot-state-" + "fixed.jsonl",
            "Path(" + '"' + "jsonlog/",
            "Path(" + "'" + "jsonlog/",
        )
        readers = []
        for module in sorted(tests.glob("test_*.py")):
            text = module.read_text(encoding="utf-8")
            if any(marker in text for marker in forbidden):
                readers.append(module.name)
        self.assertEqual(
            readers,
            [],
            "tests must use tests/fixtures, never repository jsonlog live state",
        )
