"""ROOT-FIX S1 timing guard: the entry material is gathered once per decision.

The terminal admission reads the equipment preparation on every town board
where the quest rung would walk, not only next to the entrance.  Both quest
rungs (#1 and #2) and repeated asks within one decision share one material
read; the next decision reads again.

Board: row 1 (turn 534285) of ``fixtures/n1a-townalt-20261023.jsonl.gz``
(see test_town_terminal_n1a_recorded).  The preparation is a DECLARED
CONSTRUCTED stand-in (one incomplete catalog item), so the count is the
number of preparation reads, not optimizer searches.
"""

import tests  # noqa: F401

import gzip
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.model import PLAYER_CLASS_WARRIOR, parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "n1a-townalt-20261023.jsonl.gz"


class TerminalMaterialOncePerDecisionTest(unittest.TestCase):
    def test_one_preparation_read_per_decision(self):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            board = [parse_snapshot(json.loads(line), {}) for line in stream][1]
        self.assertEqual(board.player.class_id, PLAYER_CLASS_WARRIOR)
        policy = HengbotPolicy()
        policy._build_grid_index(board)
        policy._map_predicate_snapshot = board
        preparation = SimpleNamespace(
            blockers=("incomplete-equipment-catalog",), ready=False, transaction=None,
            result=SimpleNamespace(incomplete_item_ids=frozenset({"pack:1"})))
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=preparation) as prepare, \
                patch.object(HengbotPolicy, "_safe_optional_equipment_failure_departure",
                             return_value=False):
            for sequence in (1, 2):
                policy._decision_sequence = sequence
                policy._decision_terminal_admissions = []
                for rung in ("_fixed_quest_key#1", "_fixed_quest_key#2", "_fixed_quest_key#2"):
                    self.assertIsNone(policy._town_producer_entry(rung, lambda: "walk"))
                self.assertEqual(prepare.call_count, sequence)
                record, = policy._decision_terminal_admissions
                self.assertEqual(record["codes"], ["incomplete-equipment-catalog"])
        self.assertIsNone(policy._equipment_departure_cache_token)


if __name__ == "__main__":
    unittest.main()
