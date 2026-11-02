"""Recorded identification boards continue through the equipped-identification producer."""
import json
from pathlib import Path
import unittest

import tests  # noqa: F401
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURES = Path(__file__).parent / "fixtures"


class RecordedShadowTest(unittest.TestCase):
    def test_live13_and_live15_identification_continues(self):
        state = json.loads((FIXTURES / "live-screens/live13-before-identify-state.json").read_text(
            encoding="utf8"))
        board = parse_snapshot(state, {})
        for capture in ("live13-star-identify-equipment-prompt.json",
                        "live15-read-scroll-prompt.json"):
            with self.subTest(capture=capture):
                screen = json.loads((FIXTURES / "live-screens" / capture).read_text(encoding="utf8"))
                self.assertTrue(screen)
                policy = HengbotPolicy()
                key = policy._town_equipped_identification_key(board)
                self.assertEqual((key, policy.last_reason), ("rfa", "identify:full-equipped"))


if __name__ == "__main__":
    unittest.main()
