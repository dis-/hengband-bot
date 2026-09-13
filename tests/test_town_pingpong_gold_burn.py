"""Regression pins for paid town travel and shifted item letters."""

import copy
import json
import unittest
from types import SimpleNamespace

from hengbot.cli import PostingContract
from hengbot.emit_ownership import emit_ownership_verdict
from hengbot.model import parse_snapshot
from hengbot.policy_constants import WAIT_KEY
from tests.test_quest_travel_progress import QuestTravelFixtureMixin


class TownPingPongGoldBurnPins(QuestTravelFixtureMixin, unittest.TestCase):
    def _return_1_records(self):
        import gzip
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / (
            "tests/fixtures/quest-prepare-return-town1-recurrence-stage2.jsonl.gz"
        )
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return list(zip(range(292, 329), (json.loads(line) for line in stream)))

    def test_paid_return_flight_owns_stale_source_snapshots(self):
        policy = self._policy()
        posted = None
        stale = []
        for number, raw in self._return_1_records():
            line = json.dumps(raw, ensure_ascii=False)
            if raw.get("type") in {"character", "look", "knowledge", "store"}:
                self._dispatch(policy, line)
                continue
            snapshot = parse_snapshot(raw, self.monrace)
            if number == 292:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            if number == 310:
                self.assertEqual(str(key), "3ma")
                posted = snapshot
            if number in {311, 312}:
                stale.append((str(key), policy.last_reason, snapshot, copy.copy(
                    policy._town_travel_flight
                )))
            policy.confirm_key_posted(key)
        self.assertIsNotNone(posted)
        self.assertEqual(
            [(key, reason) for key, reason, _snapshot, _flight in stale],
            [(WAIT_KEY, "fixedquest:quest-travel:await-arrival")] * 2,
        )
        self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        verdict = emit_ownership_verdict(
            None, stale[0][2], "7", None, stale[0][3]
        )
        self.assertTrue(verdict.blocked)
        self.assertEqual(
            verdict.in_flight_clause,
            "quest-teleport-posted-arrival-unobserved",
        )
        self.assertEqual(stale[0][3].pre_post_gold, posted.player.gold)
        arrival_raw = copy.deepcopy(raw)
        arrival_raw["floor"]["town_id"] = 0
        arrival_raw["floor"]["town_index"] = 1
        arrival_raw["turn"] += 8
        arrival_raw["player"]["gold"] = posted.player.gold - 500
        arrival = parse_snapshot(arrival_raw, self.monrace)
        policy.choose_key(arrival)
        self.assertIsNone(policy._town_travel_flight)

    @staticmethod
    def _item_snapshot(*, turn, x, inventory, messages=()):
        return SimpleNamespace(
            turn=turn, floor_key=(0, 0, 0), store=None,
            inventory=inventory, equipment=[], messages=messages,
            player=SimpleNamespace(
                position=SimpleNamespace(y=37, x=x), gold=1080,
                recalling=False,
            ),
        )

    @staticmethod
    def _item(slot, tval, sval, name):
        return SimpleNamespace(
            slot=slot, tval=tval, sval=sval, name=name, count=1, charges=None,
            inscription="", known=True, fully_known=True, is_equipment=False,
        )

    def test_letter_shift_identify_waits_for_observed_projection(self):
        identify = self._item("f", 70, 23, "Scroll of *Identify*")
        light = self._item("g", 70, 24, "Scroll of Light")
        contract = PostingContract()
        owner = "identify:full"
        before = self._item_snapshot(turn=2856845, x=37, inventory=[identify, light])
        contract.posted(before, "rfk", owner)
        moved = self._item_snapshot(turn=2856852, x=36, inventory=[identify, light])
        self.assertFalse(contract.allow(moved, "rfk", owner))
        self.assertEqual(
            contract.last_incident["marker"],
            "posting-contract:identical-repost-unobserved",
        )
        shifted_light = self._item("f", 70, 24, "Scroll of Light")
        observed = self._item_snapshot(
            turn=2856863, x=36, inventory=[shifted_light]
        )
        self.assertTrue(contract.allow(observed, "rfk", owner))
        self.assertEqual((shifted_light.tval, shifted_light.sval), (70, 24))


if __name__ == "__main__":
    unittest.main()
