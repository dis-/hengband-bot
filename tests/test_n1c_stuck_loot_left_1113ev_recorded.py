"""n1-c's loot left at its returns after the 2026-11-13 loot fixes (15:23-20:06), pinned on its boards.

1. The full pack's exchange destroys a spare the destroy accepts.  Owner 2026-11-13
   「価値の低い品を捨てて拾う」 (n1c-loot-recall-answers-20261113, answer 3).  n1-c life-205
   (Orc cave 23F, 15:44:20): the exchange walked onto a metal scale mail pile (base 1100) to
   destroy its cheapest spare, an amulet of resist lightning (300), which the destroy refuses as
   the best of its comparable gear (``_destroy_would_discard_superior_item``); the exchange's
   finder is bound to that one item, so nothing was destroyed and the full pack's return read
   Recall on the pile (full_pack_exchange.spare).  12:34:28 the same amulet, the same return.
2. The navigation ledger charges a committed loot goal only on the board after its own walk
   (``_loot_walked_target``).  19:17:22: a polearm three cells from the anaguma pocket was
   deferred for the floor on the 32nd board of the hold, and the visit returned by
   ``stuck:recall-escape`` with it on the floor (13:26 the same with a choke hold, mended for
   that one owner by ``_set_aside_loot_goal``).

Recorded: tests/fixtures/n1c-stuck-loot-left-1113ev.jsonl.gz
(tests/extract_n1c_stuck_loot_left_1113ev_fixture.py): the 15:44:19-20 boards (turns
4269104-4269118) and the 19:17:00-23 hold (turns 4607100-4607260) with each live decision.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
from unittest import mock

from hengbot import anaguma, full_pack_exchange
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support import recorded


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-stuck-loot-left-1113ev.jsonl.gz"
FIXTURE_SHA256 = "ad3272c80ecc561f110f16c35a3cb9a678bed215720c0ba058fff19b9b097e13"
SCALE_MAIL = Position(7, 61)  # 金属製スケイル・メイル (37, 9), base 1100
AMULET = (40, 30)  # 耐電のアミュレット, base 300: the destroy refuses it
POLEARM = Position(55, 60)  # the pile beside the anaguma pocket (tval 65 in the found row)


class N1cStuckLootLeft1113evRecordedTest(recorded.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.pack_full = [row["board"] for row in rows if row["role"] == "pack-full"]
        cls.live_return = next(row for row in rows if row["role"] == "live-return")
        cls.hold = [row for row in rows if row["role"] == "hold"]
        cls.live_deferral = next(row for row in rows if row["role"] == "live-deferral")
        cls.monrace = load_monrace_knowledge(recorded.EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(recorded.EDIT / "BaseitemDefinitions.jsonc")

    def policy(self, last):
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        recorded.skill(policy, last)
        return policy

    def on_the_pile(self):
        """The policy after the pickup and the exchange's walk, and the board on the pile."""
        policy = self.policy(self.pack_full[-1])
        for raw in self.pack_full[:-1]:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                policy.confirm_key_posted(key)
        raw = copy.deepcopy(self.pack_full[-1])
        snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
        self.assertEqual((snapshot.turn, snapshot.player.position, len(snapshot.inventory)),
                         (self.live_return["turn"], SCALE_MAIL, 23))
        return policy, raw, snapshot

    def test_on_the_pile_the_exchange_destroys_a_spare_instead_of_reading_recall(self):
        policy, raw, snapshot = self.on_the_pile()
        self.assertEqual((self.live_return["reason"], self.live_return["key"]),
                         ("return:recall", "rj"))
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, full_pack_exchange.DESTROY_REASON)
        self.assertFalse(policy._returning_to_town)
        accepted = self.post(policy, raw, key, [], self.later(raw))
        self.assertEqual(accepted, [key])

    def test_the_spare_is_one_the_destroy_accepts(self):
        policy, _raw, snapshot = self.on_the_pile()
        amulet = next(item for item in snapshot.inventory if (item.tval, item.sval) == AMULET)
        self.assertTrue(policy._destroy_would_discard_superior_item(snapshot, amulet))
        spare = full_pack_exchange.spare(policy, snapshot)
        self.assertNotEqual((spare.tval, spare.sval), AMULET)
        self.assertFalse(policy._destroy_would_discard_superior_item(snapshot, spare))
        self.assertLess(self.costs[(spare.tval, spare.sval)],
                        full_pack_exchange.pile_value(policy, snapshot, SCALE_MAIL))

    def held(self):
        """The 19:17 window decided board by board; on each board the live bot gave to another
        owner (the anaguma walk, dig, hold and strike, the device shots) that owner's live key
        is imposed, the player held in the pocket as live (declared constructed: the replay has
        no Magic-Eater power list, so the anaguma plan and the absorbed devices are not its own)."""
        policy = self.policy(self.hold[-1]["board"])
        for row in self.hold:
            raw, live = row["board"], row["live"]
            snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
            if live["reason"] in ("explore", "seek-loot"):
                key = policy.choose_key(snapshot)
            else:
                def imposed(policy, _snapshot, _hostiles, live=live):
                    policy.last_reason = live["reason"]
                    return live["key"]
                with mock.patch.object(anaguma, "key", imposed),                         mock.patch.object(anaguma, "holds", lambda *_args: True):
                    key = policy.choose_key(snapshot)
                self.assertEqual((key, policy.last_reason), (live["key"], live["reason"]))
            if key:
                policy.confirm_key_posted(key)
        return policy, snapshot

    def test_the_hold_does_not_defer_the_loot_its_walk_committed_to(self):
        policy, snapshot = self.held()
        self.assertEqual(snapshot.turn, 4607260)
        self.assertEqual(self.live_deferral["deferred"], [POLEARM.y, POLEARM.x])
        self.assertNotIn(POLEARM, policy._deferred_loot)
        self.assertFalse(policy._nav_ledger.is_expired("loot", POLEARM))
        self.assertIn(POLEARM, policy._loot_candidates(snapshot))


if __name__ == "__main__":
    import unittest
    unittest.main()
