import tests  # noqa: F401

import unittest
from unittest import mock

from hengbot import policy_town as policy_town_module
from hengbot.policy import ConservativePolicy
from tests.test_town_decision_speed_caches import (
    CAPTURES,
    build_policy,
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
        for capture in CAPTURES:
            boards = [parse_board(row) for row in load_rows(capture)][:30]
            memoised = build_policy()
            legacy = build_policy()
            legacy._refresh_town_facts = _per_snapshot_refresh(legacy)
            memoised.prime(boards[0])
            legacy.prime(boards[0])
            for line_number, board in enumerate(boards, 1):
                self.assertEqual(
                    (memoised.choose_key(board), memoised.last_reason),
                    (legacy.choose_key(board), legacy.last_reason),
                    f"{capture}:{line_number}",
                )
                self.assertEqual(
                    memoised._town_store_positions,
                    legacy._town_store_positions,
                )
                self.assertEqual(
                    memoised._town_visit_entrances,
                    legacy._town_visit_entrances,
                )


if __name__ == "__main__":
    unittest.main()
