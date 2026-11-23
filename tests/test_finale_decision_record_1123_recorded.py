"""The decision record carries the 99F/100F finale's state (n1-b life-416, 2026-11-23).

The investigation C:/hengband-backups/pdca/n1b-leave-99-1123 had to reconstruct the finale's phase
(finale_prep's step, ``lifted``, ``stopped``) and the battle's last-seen cell from the decisions'
reasons alone: no row of bot-decisions.jsonl named them.  The record now carries
angband_finale_battle ``report`` as ``angband_finale``.

Fixture finale-floor-2108-n1b-416-1123 (tests/support/finale_416.py, DECLARED RECONSTRUCTED device
lists and expedition mark): the 21:08 run's boards up to the teleport away from Oberon (turn
4297369, shown at (11,120)); the record of that board is written as the driver writes it.
"""
import tests  # noqa: F401 -- isolate live runtime files

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import cli
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT

START, TELEPORT = 4297309, 4297369


class FinaleDecisionRecordRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        held = {}

        def prepare(policy, board):
            held["policy"], held["board"] = policy, board
        raws = [raw for raw in finale_416.boards("finale-floor-2108-n1b-416-1123.jsonl.gz")
                if START <= raw["turn"] <= TELEPORT]
        rows = finale_416.drive(raws, monrace, prepare=prepare)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bot-decisions.jsonl"
            cli._write_decision(path, held["board"], rows[-1][2], rows[-1][3], held["policy"])
            cls.record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    def test_the_finale_phase_is_recorded(self):
        finale = self.record["angband_finale"]["finale"]
        self.assertIsNotNone(finale, self.record.get("angband_finale"))
        self.assertTrue(finale["phase"]["lifted"])
        self.assertIn("stopped", finale["phase"])
        self.assertIn("step", finale["phase"])

    def test_the_battle_is_recorded(self):
        battle = self.record["angband_finale"]["battle"]
        self.assertEqual(battle["last_seen"], [11, 120])
        self.assertIn(battle["phase"], ("sweep", "battle", "recover"))


if __name__ == "__main__":
    unittest.main()
