"""Recorded replay of the n1-c life-123 death of 2026-11-04 05:16 (城30階).

Source: tests/fixtures/death-n1c-123-1104.json.gz
(tests/extract_n1c_123_hallucinated_death_fixture.py).  Hallucination hides every
monster's race, so the three-turn prediction was 0 on every board.  At HP 49/487
with a hostile beside it and 12 Teleport scrolls, Recall counting down, the Lv34
Magic-Eater fired four times instead of reading; a summoned horde killed it.

Owner 2026-11-04 (「命に関わる扱いにする」): hallucinated, below the low-HP threshold,
with a hostile in view, the board is lethal for the existing ladder.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1c-123-1104.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BELOW = 3934818    # HP 49/487; the threshold is 243.5
ABOVE = 3934344    # HP 296/487, a hallucinated hostile beside it
TELEPORT_KEY = "rb"


def answer(until):
    policy = d57.new_policy(CASE)
    for raw in CASE["boards"]:
        key = d57.loops.decide(policy, raw)
        if raw["turn"] == until:
            return raw, key, policy.last_reason
        policy.confirm_key_posted(key)
    raise AssertionError(until)


class HallucinatedLowHpRecordedTest(d57.PostedDeathKey):
    prompts = {**d57.PROMPTS, "r": "どの巻物を読みますか? "}

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[BELOW], ("quest-strategy:ranged-fire:magic-eater", "mBp9"))
        self.assertEqual(recorded[ABOVE], ("melee", "8"))
        board = next(raw for raw in CASE["boards"] if raw["turn"] == BELOW)
        self.assertTrue(board["player"]["status"]["hallucinated"])
        self.assertTrue(board["player"]["recalling"])

    def test_below_the_threshold_reads_the_teleport(self):
        raw, key, reason = answer(BELOW)
        self.assertEqual((key, reason), (TELEPORT_KEY, "emergency:teleport"))
        self.post(d57.new_policy(CASE), raw, key)

    def test_above_the_threshold_keeps_todays_answer(self):
        _raw, key, reason = answer(ABOVE)
        self.assertEqual((key, reason), ("8", "melee"))


if __name__ == "__main__":
    unittest.main()
