"""ROOT-FIX S2-b: one preparation read per decision, and the need evidence (ii).

Design 5.2: the terminal's material read (``commit=False``) and the need
list's departure verdict share one ``_prepare_equipment_optimization`` read
per decision and board; the next decision reads again.

Design 3.5 (ii): a refusal server named by a need category is live while
that need is on this decision's need list (the claims evaluation's stamp)
and its supplier's store-buy verdict admits.  Without the evidence the
refused terminal closes at once (``terminal-refused-unserved``).

Board: row 1 (turn 534285) of ``fixtures/n1a-townalt-20261023.jsonl.gz``
(see test_town_terminal_n1a_recorded), town 1, quest 2 TAKEN.  DECLARED
CONSTRUCTED: the preparation stand-in, the patched entry verdict (refused by
``identification-flow`` as live), and the need-list stamp (one
``identification-source`` need at the Alchemist).  No Morivant expedition,
so the cross-town server is not live.
"""

import tests  # noqa: F401

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import DecisionContext, TownNeed
from hengbot.town_terminal import TerminalRef


FIXTURE = Path(__file__).parent / "fixtures" / "n1a-townalt-20261023.jsonl.gz"
ENTRY = TerminalRef("quest-entry", (2,))
RUNG = "_fixed_quest_key#2"
NEED = TownNeed(store_type=STORE_ALCHEMIST, category="identification-source",
                ordering_class="before-withdrawal")


def _board():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [parse_snapshot(json.loads(line), {}) for line in stream][1]


def _refused(self, snapshot, *, destination_depth=None, commit=True, codes=None):
    if codes is not None:
        codes.append("identification-flow")
    return False


class PreparationReadOncePerDecisionTest(unittest.TestCase):
    def setUp(self):
        self.board = _board()
        self.policy = HengbotPolicy()
        self.policy._build_grid_index(self.board)
        self.policy._map_predicate_snapshot = self.board
        self.preparation = SimpleNamespace(
            blockers=("no-valid-loadout",), ready=False, transaction=None, result=None)

    def reads(self, calls):
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=self.preparation) as prepare, \
                patch.object(HengbotPolicy, "_safe_optional_equipment_failure_departure",
                             return_value=False):
            for sequence, snapshot in calls:
                self.policy._decision_sequence = sequence
                codes: list[str] = []
                self.assertFalse(self.policy._equipment_departure_ready(
                    snapshot, destination_depth=5, commit=False, codes=codes))
                self.assertEqual(codes, ["no-valid-loadout"])
                self.assertFalse(self.policy._equipment_departure_ready(
                    snapshot, destination_depth=7))
        return prepare.call_count

    def test_material_and_need_list_share_the_read(self):
        self.assertEqual(self.reads([(1, self.board)]), 1)

    def test_next_decision_reads_again(self):
        # Control: the memo never outlives the decision.
        self.assertEqual(self.reads([(1, self.board), (2, self.board)]), 2)

    def test_other_board_is_not_memoized(self):
        # Control: a probe board (not the decision's board) reads each time.
        probe = replace(self.board)
        self.assertEqual(self.reads([(1, probe)]), 2)


class NeedEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.board = _board()
        self.policy = HengbotPolicy()
        self.policy._build_grid_index(self.board)
        self.policy._map_predicate_snapshot = self.board
        self.policy._decision_context = DecisionContext(
            equipment_transaction_owned=False, identity=3)
        self.policy._decision_sequence = 3
        self.policy._decision_terminal_admissions = []

    def entry(self):
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _refused):
            self.assertIsNone(self.policy._town_producer_entry(RUNG, lambda: "walk"))
        record, = self.policy._decision_terminal_admissions
        self.assertEqual(record["codes"], ["identification-flow"])
        return record

    def test_supplied_need_keeps_the_server_live(self):
        self.policy._decision_claim_needs = (3, self.board, (NEED,))
        record = self.entry()
        self.assertEqual(record["live"], [["shop-buy", "identification-source"]])
        self.assertIsNone(record["closed"])
        self.assertEqual(record["yields"], 1)

    def test_without_the_need_the_terminal_closes(self):
        # Control: no need list in this decision.
        record = self.entry()
        self.assertEqual(record["live"], [])
        self.assertEqual(self.policy._town_visit_ledger.closed_terminals,
                         {ENTRY: "terminal-refused-unserved:identification-flow"})

    def test_stale_need_list_is_not_evidence(self):
        # Control: the previous decision's list.
        self.policy._decision_claim_needs = (2, self.board, (NEED,))
        self.assertEqual(self.entry()["live"], [])

    def test_supplier_without_an_offer_is_not_evidence(self):
        # Control: the attempted Alchemist's remembered page offers nothing.
        self.policy._decision_claim_needs = (3, self.board, (NEED,))
        self.policy._town_store_attempted[STORE_ALCHEMIST] = self.board.turn
        self.policy._town_supplier_stock[STORE_ALCHEMIST] = SimpleNamespace(items=())
        self.assertEqual(self.entry()["live"], [])


if __name__ == "__main__":
    unittest.main()
