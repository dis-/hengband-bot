import tests  # noqa: F401

import unittest
from unittest import mock

from hengbot import policy_town as policy_town_module
from hengbot.policy import ConservativePolicy
from tests.test_town_decision_speed_caches import (
    CAPTURES,
    build_policy,
    checkpoint_without_elapsed_telemetry,
    load_rows,
    parse_board,
)


def _per_snapshot_refresh(policy):
    """Reproduce the af25b541 refresh: skip only for the same snapshot object."""
    def refresh(snapshot):
        if snapshot is not policy._town_fact_snapshot:
            policy._town_fact_snapshot = None
        return ConservativePolicy._refresh_town_facts(policy, snapshot)
    return refresh


class TownFactRefreshOncePerDecisionTest(unittest.TestCase):
    def test_recorded_boards_refresh_town_facts_once_per_decision(self):
        # Issue #72: Home probes derived with dataclasses.replace share the
        # decision's grids, and the public choose_key reads the decision input
        # whose grid objects the merged view holds on the emitted window; each
        # of them re-ran the whole emitted-window refresh (13,068 town cells).
        original = policy_town_module._town_store_position_index
        for capture in CAPTURES:
            boards = [parse_board(row) for row in load_rows(capture)]
            policy = build_policy()
            policy.prime(boards[0])
            calls = []
            with mock.patch.object(
                policy_town_module, "_town_store_position_index",
                side_effect=lambda current: calls.append(1) or original(current),
            ):
                counts = []
                for board in boards:
                    calls.clear()
                    policy.choose_key(board)
                    counts.append(len(calls))
            self.assertLessEqual(max(counts), 1, f"{capture}: {counts}")

    def test_recorded_boards_decide_as_per_snapshot_refresh(self):
        # The skipped reruns must leave the checkpointed state byte-identical,
        # including which cell objects the fact sets share and whether the
        # entrance cache was dropped.
        for capture in CAPTURES:
            rows = load_rows(capture)
            memoised = build_policy()
            legacy = build_policy()
            refresh = _per_snapshot_refresh(legacy)
            memoised.prime(parse_board(rows[0]))
            legacy.prime(parse_board(rows[0]))
            for line_number, row in enumerate(rows, 1):
                legacy._refresh_town_facts = refresh
                legacy_key = legacy.choose_key(parse_board(row))
                del legacy._refresh_town_facts
                self.assertEqual(
                    (memoised.choose_key(parse_board(row)), memoised.last_reason),
                    (legacy_key, legacy.last_reason),
                    f"{capture}:{line_number}",
                )
                self.assertEqual(
                    checkpoint_without_elapsed_telemetry(memoised),
                    checkpoint_without_elapsed_telemetry(legacy),
                    f"{capture}:{line_number} policy state",
                )


if __name__ == "__main__":
    unittest.main()
