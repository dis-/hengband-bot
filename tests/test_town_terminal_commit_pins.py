"""ROOT-FIX S1: the material read never commits; the entry's call site does.

``_equipment_departure_ready(commit=False, codes=[...])`` is the terminal
admission's material read (design 3.2): the same verdict, the refusal codes,
and none of the confirmation writes.  Each test drives one write branch with
a DECLARED CONSTRUCTED preparation stand-in on the recorded n1-a board row 1
(turn 534285, a Warrior in town 1, see test_town_terminal_n1a_recorded).
Also pinned: the restored-checkpoint defaults of the new ledger fields and
the per-decision reset of the admission records.
"""

import tests  # noqa: F401

import gzip
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import MorivantFullIdentifyExpedition
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map
from hengbot.town_terminal import TerminalRef


FIXTURE = Path(__file__).parent / "fixtures" / "n1a-townalt-20261023.jsonl.gz"
LEDGER_FIELDS = ("terminal_yields", "closed_terminals", "terminal_route_edges",
                 "terminal_server_vectors")


def _board():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [parse_snapshot(json.loads(line), {}) for line in stream][1]


def _preparation(blockers=(), *, ready=False, actions=()):
    return SimpleNamespace(
        blockers=tuple(blockers), ready=ready,
        transaction=SimpleNamespace(actions=tuple(actions)),
        result=SimpleNamespace(incomplete_item_ids=frozenset()),
        current=SimpleNamespace(item_ids=frozenset({"worn:1"})))


class MaterialReadDoesNotCommitTest(unittest.TestCase):
    def setUp(self):
        self.board = _board()
        self.policy = HengbotPolicy()
        self.policy._build_grid_index(self.board)
        self.policy._map_predicate_snapshot = self.board
        self.policy._decision_sequence = 7

    def ready(self, **kwargs):
        return self.policy._equipment_departure_ready(
            self.board, destination_depth=1, **kwargs)

    def test_complete_loadout_is_confirmed_only_on_commit(self):
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(ready=True)), \
                patch.object(HengbotPolicy, "_safe_optional_equipment_failure_departure",
                             return_value=False), \
                patch.object(HengbotPolicy, "_record_confirmed_loadout") as record:
            self.assertTrue(self.ready(commit=False, codes=[]))
            record.assert_not_called()
            self.assertIsNone(self.policy._equipment_departure_cache_token)
            self.assertTrue(self.ready())
            record.assert_called_once()
            self.assertEqual(self.policy._equipment_departure_cache_token, (7, 1))

    def test_optional_failure_is_staged_only_on_commit(self):
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(("no-valid-loadout",))), \
                patch.object(HengbotPolicy, "_safe_optional_equipment_failure_departure",
                             return_value=True), \
                patch.object(HengbotPolicy, "_stage_optional_equipment_failure_departure") as stage:
            self.assertTrue(self.ready(commit=False))
            stage.assert_not_called()
            self.assertTrue(self.ready())
            stage.assert_called_once()

    def test_home_full_closure_is_written_only_on_commit(self):
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(("pack-space-required:1",), actions=("a",))), \
                patch.object(HengbotPolicy, "_current_worn_loadout_confirmed", return_value=True), \
                patch.object(HengbotPolicy, "_home_is_full", return_value=True):
            self.assertTrue(self.ready(commit=False))
            self.assertIsNone(self.policy._equipment_transaction_visit_closure)
            self.assertIsNone(self.policy._equipment_optional_failure_pending)
            self.assertTrue(self.ready())
        self.assertEqual(self.policy._equipment_transaction_visit_closure["reason"],
                         "pack-space-home-full")

    def test_unactionable_suppression_is_staged_only_on_commit(self):
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(("pending-random-teleport-suppression",),
                                                    actions=("a",))), \
                patch.object(HengbotPolicy, "_current_worn_loadout_confirmed", return_value=True), \
                patch.object(HengbotPolicy, "_random_teleport_suppression_actionable",
                             return_value=False):
            self.assertTrue(self.ready(commit=False))
            self.assertIsNone(self.policy._equipment_optional_failure_pending)
            self.assertTrue(self.ready())
        self.assertIsNotNone(self.policy._equipment_optional_failure_pending)

    def test_codes_bypass_the_bool_cache(self):
        self.policy._equipment_departure_cache_token = (7, 1)
        self.policy._equipment_departure_cache_value = False
        codes = []
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(("home-scan-incomplete",))):
            self.assertFalse(self.ready(commit=False, codes=codes))
        self.assertEqual(codes, ["home-scan-incomplete"])

    def test_calibration_branch_names_the_open_session(self):
        self.policy._equipment_transaction_session = object()
        codes = []
        with patch.object(HengbotPolicy, "_prepare_equipment_optimization",
                          return_value=_preparation(("calibration-required",))):
            self.assertFalse(self.ready(commit=False, codes=codes))
        self.assertEqual(codes, ["session-active"])


class LedgerRestoreAndRecordTest(unittest.TestCase):
    def test_old_checkpoint_ledger_gets_the_terminal_fields(self):
        policy = HengbotPolicy()
        for name in LEDGER_FIELDS:
            del policy._town_visit_ledger.__dict__[name]
        restored = normalize_policy_state(policy)
        ledger = restored._town_visit_ledger
        self.assertEqual([getattr(ledger, name) for name in LEDGER_FIELDS], [{}, {}, {}, {}])
        ledger.terminal_yields[TerminalRef("quest-entry", (2,))] += 1

    def test_restore_defaults_are_the_fresh_attributes(self):
        policy = HengbotPolicy()
        fresh = set(vars(policy))
        for name in ("_terminal_admission_memo", "_decision_terminal_admissions"):
            del policy.__dict__[name]
        restored = normalize_policy_state(policy)
        self.assertEqual(set(vars(restored)), fresh)
        self.assertIsNone(restored._terminal_admission_memo)
        self.assertEqual(restored._decision_terminal_admissions, [])
        self.assertEqual(set(vars(normalize_policy_state(HengbotPolicy()))), fresh)

    def test_each_decision_records_its_own_admission(self):
        board = _board()
        maps = {0: parse_town_map(find_outpost_map(Path(__file__)))}
        for town_index in range(2, 6):
            path = find_town_map(town_index, Path(__file__))
            if path is not None:
                maps[town_index - 1] = parse_town_map(path)
        policy = HengbotPolicy(town_map=maps[0], town_maps=maps)
        # Declared setup: the live process had already scanned Home.
        policy._home_knowledge_scan_epoch = 0
        policy._morivant_full_identify = MorivantFullIdentifyExpedition(
            origin_town_id=1, target_signatures=(("katana", 0, 0),))

        def refused(self, snapshot, *, destination_depth=None, commit=True, codes=None):
            if codes is not None:
                codes.append("identification-flow")
            return False

        with patch.object(HengbotPolicy, "_equipment_departure_ready", refused), \
                patch.object(HengbotPolicy, "_skill_exp_request_key", return_value=None):
            yields = []
            for _decision in range(2):
                policy.choose_key(board)
                rows = policy.decision_claim["terminal_admission"]
                self.assertEqual(len(rows), 1)
                yields.append(rows[0]["yields"])
        self.assertEqual(yields, [1, 2])


if __name__ == "__main__":
    unittest.main()
