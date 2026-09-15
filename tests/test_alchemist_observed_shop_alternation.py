"""Recorded pins for the Alchemist observed-page owner alternation."""

from __future__ import annotations

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, parse_snapshot
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
            rows[8],  # 3024728 adjacent outside composition boundary
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
        self.assertEqual(replay[2], (
            3_024_720, *live_decision(3_024_720),
        ))
        live = live_decision(3_024_728)
        self.assertEqual(live, (
            "7", "shop:approach",
        ))
        self.assertEqual(replay[3], (
            3_024_728, "5", "shop:one-shot-sell",
        ))
        print(f"replay={replay[3][1:]!r} live={live!r}")
        self.assertEqual(policy._store_visit.owner, "shop-one-shot")
        self.assertEqual(policy._store_visit.store_type, STORE_ALCHEMIST)
        self.assertTrue(policy._store_visit.operation_posted)
        self.assertFalse(policy._store_visit.operation_released)
        self.assertEqual(policy._store_visit.operation_key, "d0y\x1b")
        self.assertEqual(policy._acquire_store_visit_attempt, {
            "acquire_store_visit_called": True,
            "requested_owner": "shop-one-shot",
            "requested_store": STORE_ALCHEMIST,
            "acquire_result": "granted-observed-outside",
        })
        self.assertEqual(
            policy._town_errand_plan.need_categories[STORE_ALCHEMIST],
            ("low-level-sale", "identification-source"),
        )
        self.assertFalse(any(
            reason == "town:blocked:owner-retired"
            for _, _, reason in replay
        ))

    def test_component_general_store_uses_the_same_outside_handoff(self):
        # Component test: preserve the recorded player/inventory/page shape,
        # changing only the shop identity and matching entrance glyph.
        rows = recorded_rows()
        inside = parse_snapshot(rows[7], {})
        outside = parse_snapshot(rows[8], {})
        inside = replace(
            inside, store=replace(inside.store, store_type=STORE_GENERAL),
        )
        entrance = outside.grid_at(outside.player.position)
        outside = replace(
            outside,
            grids={
                **outside.grids,
                outside.player.position: replace(
                    entrance, store_number=STORE_GENERAL,
                ),
            },
        )
        policy = HengbotPolicy()

        leave = policy.choose_key(inside)
        composed = policy.choose_key(outside)

        self.assertEqual((leave, composed, policy.last_reason), (
            "\x1b", "7", "explore",
        ))
        self.assertIsNone(policy._shop_observation)
        self.assertNotEqual(policy._store_visit.store_type, STORE_GENERAL)
        self.assertNotEqual(policy.last_reason, "shop:approach")


if __name__ == "__main__":
    unittest.main()
