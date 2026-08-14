import json
from dataclasses import replace
from pathlib import Path
import unittest

from hengbot.cli import PostingContract
from hengbot.model import Snapshot
from hengbot.policy import HengbotPolicy, WildernessMap
from test_policy import player


ROOT = Path(__file__).resolve().parents[1]


def incident_world_snapshot() -> Snapshot:
    return Snapshot(
        player(48, 5), {}, [], turn=329516, floor_key=(0, 0, 0),
        width=99, height=66, town_flag=False, town_id=-1, town_index=0,
    )


def incident_wilderness_map() -> WildernessMap:
    rows = ["." * 99 for _ in range(66)]
    rows[48] = f"{rows[48][:5]}1{rows[48][6:]}"
    return WildernessMap(tuple(rows))


class WorldMapKeyHygieneTest(unittest.TestCase):
    def test_frozen_capture_characterizes_owner_key_and_refusal_counts(self):
        rows = [
            json.loads(line)
            for line in (ROOT / "evidence/evidence-entertown-decisions.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        incident = [
            row for row in rows
            if row.get("decision_sequence") in range(6734, 6762)
            or row.get("reason") == "posting-contract:identical-repost-unobserved"
        ]

        self.assertEqual(
            sum(row.get("key") == "\x1b`n(." for row in incident), 1
        )
        self.assertEqual(
            sum(row.get("reason") == "posting-contract:identical-repost-unobserved"
                for row in incident), 11
        )
        self.assertEqual(
            sum(row.get("reason") == "wilderness:enter-town"
                and row.get("key") == ">" for row in incident), 12
        )

    def test_world_map_preempts_every_retained_town_owner_family(self):
        snapshot = incident_world_snapshot()
        for retained_reason in (
            "equipment-transaction:travel-home",
            "shop:travel",
            "town:repetition-required-shopping",
            "fundraise:ascend",
        ):
            with self.subTest(retained_reason=retained_reason):
                policy = HengbotPolicy(wilderness_map=incident_wilderness_map())
                policy.last_reason = retained_reason
                policy._fundraising_mode = "scavenge"

                self.assertEqual(policy.choose_key(snapshot), ">")
                self.assertEqual(policy.last_reason, "wilderness:enter-town")

    def test_refusal_probe_breaks_identity_then_reposts_enter_town(self):
        snapshot = incident_world_snapshot()
        policy = HengbotPolicy(wilderness_map=incident_wilderness_map())
        contract = PostingContract()

        first = policy.choose_key(snapshot)
        self.assertEqual((first, policy.last_reason), (">", "wilderness:enter-town"))
        self.assertTrue(contract.allow(snapshot, first, policy.last_reason))
        contract.posted(snapshot, first, policy.last_reason)

        refused = policy.choose_key(replace(snapshot))
        self.assertEqual(refused, ">")
        self.assertFalse(contract.allow(snapshot, refused, policy.last_reason))
        policy.refuse_key_posting("wilderness:enter-town", refused)

        probe = policy.choose_key(replace(snapshot))
        self.assertEqual((probe, policy.last_reason),
                         ("l\x1b", "wilderness:enter-town"))
        self.assertTrue(contract.allow(snapshot, probe, policy.last_reason))
        contract.posted(snapshot, probe, policy.last_reason)

        repost = policy.choose_key(replace(snapshot))
        self.assertEqual((repost, policy.last_reason),
                         (">", "wilderness:enter-town"))
        self.assertTrue(contract.allow(snapshot, repost, policy.last_reason))

    def test_two_fresh_instances_have_the_same_world_map_gate(self):
        snapshot = incident_world_snapshot()
        results = []
        for _ in range(2):
            policy = HengbotPolicy(wilderness_map=incident_wilderness_map())
            results.append((policy.choose_key(snapshot), policy.last_reason))

        self.assertEqual(results, [
            (">", "wilderness:enter-town"),
            (">", "wilderness:enter-town"),
        ])

