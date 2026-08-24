from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.cli import POLICY_FINAL_STOP_REASONS, _policy_final_stop_banner
from hengbot.model import (
    InventoryItem,
    Position,
    SV_FLASK_OIL,
    TVAL_FLASK,
    parse_snapshot,
)
from hengbot.policy import HengbotPolicy, PROBE_LIMIT, READ_KEY, WAIT_KEY
from hengbot.policy_types import OWNER_EXPECTATION_MAX_TURNS


FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot_fixture():
    path = FIXTURES / "incident-darkread-guard-miss-turn-1029477.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return parse_snapshot(json.loads(next(stream)), {})


class DarkwalkIncidentTest(unittest.TestCase):
    def test_missing_own_cell_is_dark_and_public_choice_does_not_read(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()

        self.assertTrue(snapshot.grids_observed)
        self.assertNotIn(snapshot.player.position, snapshot.grids)
        self.assertTrue(policy._is_dark(snapshot))
        self.assertFalse(policy._can_read_scrolls(snapshot))
        self.assertFalse(policy.choose_key(snapshot).startswith(READ_KEY))
        self.assertEqual(policy.last_reason, "dark:probe")

    def test_frozen_decisions_pin_the_historical_read_refusal_cadence(self):
        path = FIXTURES / "incident-darkread-guard-miss-20260824.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]

        decisions = [row for row in rows if "inventory" in row]
        reads = [
            (index, row)
            for index, row in enumerate(decisions)
            if row.get("key") == "rd"
        ]
        self.assertEqual(len(rows), 420)
        self.assertEqual(len(reads), 107)
        self.assertEqual(
            {second[0] - first[0] for first, second in zip(reads, reads[1:])},
            {3, 4},
        )
        self.assertGreaterEqual(
            min(
                second[1]["turn"] - first[1]["turn"]
                for first, second in zip(reads, reads[1:])
            ),
            OWNER_EXPECTATION_MAX_TURNS,
        )
        self.assertEqual(
            {tuple(sorted(row["inventory"].items())) for row in decisions},
            {(('free', 11), ('used', 12))},
        )

    def test_dark_probe_is_bounded_and_ends_at_visible_terminal(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()
        actions = []

        for _ in range(8 * PROBE_LIMIT + 2):
            key = policy.choose_key(snapshot)
            actions.append((key, policy.last_reason))
            if policy.last_reason == "dark:locomotion-exhausted":
                break

        self.assertTrue(any(reason == "dark:probe" for _, reason in actions))
        self.assertEqual(actions[-1], (WAIT_KEY, "dark:locomotion-exhausted"))
        self.assertIn("dark:locomotion-exhausted", POLICY_FINAL_STOP_REASONS)
        self.assertIn(
            "stopping the bot for investigation",
            _policy_final_stop_banner("dark:locomotion-exhausted"),
        )

    def test_dark_backtrack_uses_the_existing_remembered_graph(self):
        snapshot = _snapshot_fixture()
        policy = HengbotPolicy()
        origin = snapshot.player.position
        target = Position(origin.y + 1, origin.x)
        template = next(iter(snapshot.grids.values()))
        routed = replace(
            snapshot,
            grids={
                **snapshot.grids,
                target: replace(template, position=target, passable=True, wall=False),
            },
        )
        policy._build_grid_index(routed)
        policy._visit_counts[target] = 1
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                       (-1, 1), (1, -1), (1, 1)):
            policy._probe_counts[(origin.y + dy, origin.x + dx)] = PROBE_LIMIT

        key = policy._dark_locomotion_key(routed)

        self.assertEqual(key, "2")
        self.assertEqual(policy.last_reason, "dark:backtrack")

    def test_unknown_lantern_uses_missing_cell_as_the_empty_signal(self):
        snapshot = _snapshot_fixture()
        lantern = next(item for item in snapshot.equipment if item.is_lantern)
        oil = InventoryItem(
            "z", "oil", 1, TVAL_FLASK, SV_FLASK_OIL, True, True, fuel=7500
        )
        unknown = replace(
            snapshot,
            equipment=[
                replace(item, known=False, fully_known=False)
                if item is lantern else item
                for item in snapshot.equipment
            ],
            inventory=[*snapshot.inventory, oil],
        )

        self.assertEqual(HengbotPolicy()._light_refill_item(unknown), oil)
        template = next(iter(snapshot.grids.values()))
        lit = replace(
            unknown,
            grids={
                **unknown.grids,
                unknown.player.position: replace(
                    template,
                    position=unknown.player.position,
                    passable=True,
                    wall=False,
                    lit=True,
                ),
            },
        )
        self.assertIsNone(HengbotPolicy()._light_refill_item(lit))

    def test_legacy_snapshot_without_grid_observation_remains_readable(self):
        snapshot = _snapshot_fixture()
        legacy = replace(snapshot, grids_observed=False)

        self.assertFalse(HengbotPolicy()._is_dark(legacy))


if __name__ == "__main__":
    unittest.main()
