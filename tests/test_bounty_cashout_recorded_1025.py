"""Issue #47: n1-b bounty cash-out replaced by supplier travel (recorded).

DECLARED CONSTRUCTED checkpoint: the CLI checkpoint is absent.  The boards
are recorded (tests/fixtures/bounty-cashout-1025.jsonl.gz, state.jsonl lines
4613-4643).  Installed from the recorded decision telemetry only: the Home
census is complete (home_scan source ~9), the remembered supplier is the
Alchemist at (37,91) with its recorded stock page (board 4643), and the
procurement fingerprint has already been seen once.  choose_key dispatches the
real bounty producer and the town result arbiter.  Each board is an
independent seam, never a command-effect replay after divergence.
"""
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

import tests  # noqa: F401
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from s33_phase2_fixtures import town_map

_ROWS = [
    json.loads(line)
    for line in gzip.open(
        Path(__file__).parent / "fixtures/bounty-cashout-1025.jsonl.gz",
        "rt", encoding="utf-8")
]
_BOARDS = {int(row["source_line"]): row["board"]
           for row in _ROWS if row["type"] == "recorded-board"}
_DECISIONS = {int(row["decision_sequence"]): row
              for row in _ROWS if row["type"] == "decision"}


def board(line):
    # DECLARED CONSTRUCTED: the ~f cache is absent from the capture.
    return replace(parse_snapshot(_BOARDS[line]), protocol_version=2)


def recorded_policy(snapshot):
    policy = HengbotPolicy(town_map=town_map())
    policy.prime(snapshot)
    policy._home_knowledge_current = True
    policy._equipment_catalog.home_scan_complete = True
    policy._shopping_approach_goal = Position(37, 91)
    policy._shopping_approach_store_type = 4
    policy._town_supplier_stock[4] = board(4643).store
    policy._town_progress_history().append(
        policy._town_progress_fingerprint(snapshot))
    return policy


class BountyCashoutRecordedTest(unittest.TestCase):
    def test_recorded_rows_show_the_replaced_cashout(self):
        # Recorded on 0f8835a7: the final office step was replaced by travel.
        for sequence in (4951, 4972):
            with self.subTest(sequence=sequence):
                row = _DECISIONS[sequence]
                self.assertEqual(row["key"], "\x1b`n%.")
                self.assertEqual(
                    row["reason"],
                    "town-progress-invariant:defect:bounty:cashout"
                    "=>town-progress-invariant:approach")

    def test_recorded_final_office_step_hands_over_the_bounty(self):
        for line in (4617, 4640):
            with self.subTest(line=line):
                snapshot = board(line)
                policy = recorded_policy(snapshot)
                key = policy.choose_key(snapshot)
                self.assertEqual(key, "7cy\x1b")
                self.assertEqual(policy.last_reason, "bounty:cashout")
                self.assertEqual(policy.decision_claim["owner"], "quest-request")

    def test_recorded_approach_boards_unchanged(self):
        for line, key in ((4613, "1"), (4621, "7")):
            with self.subTest(line=line):
                snapshot = board(line)
                policy = recorded_policy(snapshot)
                self.assertEqual(policy.choose_key(snapshot), key)
                self.assertEqual(policy.last_reason, "bounty:approach")

    def test_constructed_handover_effect_ends_the_bounty_errand(self):
        snapshot = board(4617)
        policy = recorded_policy(snapshot)
        self.assertEqual(policy.choose_key(snapshot), "7cy\x1b")
        # DECLARED CONSTRUCTED effect: the office took the only wanted remain.
        after = replace(snapshot, turn=snapshot.turn + 1, inventory=tuple(
            item for item in snapshot.inventory if not item.is_bounty))
        policy.choose_key(after)
        self.assertFalse(policy.last_reason.startswith("bounty:"),
                         policy.last_reason)

    def test_constructed_refused_handover_retires_within_owner_budget(self):
        snapshot = board(4617)
        policy = recorded_policy(snapshot)
        budget = policy._town_turn_arbiter.registry["quest-request"].budget
        keys = []
        retired = None
        for _ in range(budget + 2):
            # DECLARED CONSTRUCTED: the hand-over has no effect on the board.
            snapshot = replace(snapshot, turn=snapshot.turn + 1)
            keys.append(policy.choose_key(snapshot))
            current = policy._claim_register.current
            if current.closed == "retired":
                retired = current
        self.assertEqual(keys[:budget], ["7cy\x1b"] * budget)
        self.assertIsNotNone(retired)
        self.assertEqual(retired.owner.value, "quest-request")
        self.assertNotEqual(policy._claim_register.current.owner.value,
                            "quest-request")
        self.assertNotEqual(keys[-1], "7cy\x1b")


if __name__ == "__main__":
    unittest.main()
