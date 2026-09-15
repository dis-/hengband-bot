"""Recorded pins for the Alchemist observed-page owner alternation."""

from __future__ import annotations

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import HengbotPolicy


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "alchemist-observed-shop-alternation-20260916.jsonl.gz"
)
SOURCE = ROOT / "jsonlog" / "bot-state-fixed.jsonl"
DECISIONS = ROOT / "jsonlog" / "bot-decisions.jsonl"


def recorded_rows() -> list[dict]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def live_decision(turn: int) -> tuple[str, str]:
    with DECISIONS.open(encoding="utf-8") as stream:
        matches = [
            row for row in map(json.loads, stream)
            if row.get("turn") == turn
        ]
    assert len(matches) == 1, (turn, matches)
    return matches[0]["key"], matches[0]["reason"]


class AlchemistObservedShopAlternationTest(unittest.TestCase):
    def test_fixture_is_the_byte_faithful_incident_window(self):
        with gzip.open(FIXTURE, "rb") as stream:
            frozen = stream.read()
        selected = []
        with SOURCE.open("rb") as stream:
            for line in stream:
                turn = int(json.loads(line).get("turn", -1))
                if 3_024_656 <= turn <= 3_024_766:
                    selected.append(line)
        self.assertEqual(frozen, b"".join(selected))
        rows = recorded_rows()
        self.assertEqual(len(rows), 17)
        self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (
            3_024_656, 3_024_766,
        ))

    def test_three_entries_freeze_owner_needs_shelf_and_prompt_keys(self):
        rows = recorded_rows()
        pages = [
            row for row in rows
            if row.get("store", {}).get("store_type") == STORE_ALCHEMIST
        ]
        self.assertEqual([row["turn"] for row in pages], [
            3_024_720, 3_024_738, 3_024_759,
        ])
        for page in pages:
            shelf = {
                (item["letter"], item["name"], item["price"])
                for item in page["store"]["items"]
            }
            self.assertIn(("j", "帰還の詔の巻物", 233), shelf)
            self.assertIn(("l", "*鑑定*の巻物", 2326), shelf)

        prompt = next(
            row for row in rows
            if row["turn"] == 3_024_720 and "store" not in row
        )
        self.assertEqual(prompt["messages"], ["トラベルを継続しますか？[y/n]"])
        self.assertEqual(live_decision(3_024_665), (
            "\x1b`n%.", "shop:travel",
        ))
        self.assertEqual(live_decision(3_024_676), (
            "\x1b`n%.", "store:entry-interrupted-replan",
        ))

    def test_recorded_route_owner_consumes_page_at_first_r4_divergence(self):
        rows = recorded_rows()
        # Consume the final board available to each live decision. The 3024676
        # command-barrier retry has no executor metadata in bot-state JSONL, so
        # its identical posted travel key is represented by the resulting
        # 3024720 store page, not replayed as a counterfactual policy decision.
        route = [
            rows[1],  # 3024656 Weapon Shop page
            rows[3],  # 3024665 surface: real Alchemist route entry point
            rows[7],  # 3024720 observed Alchemist page
        ]
        policy = HengbotPolicy()
        replay = []
        for raw in route:
            snapshot = parse_snapshot(raw, {})
            replay.append((snapshot.turn, policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(replay[:2], [
            (3_024_656, *live_decision(3_024_656)),
            (3_024_665, *live_decision(3_024_665)),
        ])
        live = live_decision(3_024_720)
        self.assertEqual(live, (
            "\x1b", "town-progress-invariant:continue-observed-shop",
        ))
        self.assertEqual(replay[2], (
            3_024_720, "d0y\x1b", "shop:one-shot-sell",
        ))
        print(f"replay={replay[2][1:]!r} live={live!r}")
        self.assertEqual(policy._store_visit.owner, "town-errand")
        self.assertEqual(policy._store_visit.store_type, STORE_ALCHEMIST)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertTrue(policy._store_visit.operation_released)
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_ALCHEMIST],
            ("low-level-sale", "identification-source"),
        )
        self.assertFalse(any(
            reason == "town:blocked:owner-retired"
            for _, _, reason in replay
        ))


if __name__ == "__main__":
    unittest.main()
