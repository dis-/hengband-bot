"""n1-c's loot left at its returns (2026-11-13 08:41-13:30), pinned on its recorded boards.

1. A full pack's exchange comes before the return the full pack starts.
   Owner 2026-11-13 「価値の低い品を捨てて拾う」 (n1c-loot-recall-answers-20261113, answer 3).
   n1-c life-205 (Orc cave 23F): seven of 31 visits returned with ``return:recall`` /
   ``pack-full`` and known loot left; on each the board that filled the pack read Recall although
   a dearer single item lay on the floor, because the exchange was asked only from the loot
   owner, below the full pack's return (full_pack_exchange, ladder_objectives).
2. A choke hold sets the loot walk it interrupts aside (summoner_wait.hold_key,
   ``_set_aside_loot_goal``).  The navigation ledger charged the committed loot goal on every
   board of the hold and deferred it for the floor (13:26:32, a heavy chain mail two cells
   away); two of the 31 visits left such a goal when they returned by ``stuck:recall-escape``.

Recorded: tests/fixtures/n1c-loot-left-1113pm.jsonl.gz
(tests/extract_n1c_loot_left_1113pm_fixture.py): the 09:22:12 boards (turns 3629396-3629410)
and the 13:26 choke hold (turns 4044384-4044417).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path

from hengbot import full_pack_exchange
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, SV_SCROLL_PHASE_DOOR, TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support import recorded


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-loot-left-1113pm.jsonl.gz"
FIXTURE_SHA256 = "c770396104ef0daa1227886959f8f9812c623e79e541fbdca92a07d55eeb6d9f"
# The recorded floor's single items worth more than the spare (base cost, k_info).
HEAVY_CHAIN_MAIL = Position(35, 22)  # 重鎖かたびら [16], 900
STAFF_OF_EARTHQUAKES = Position(39, 84)  # 地震の杖, 350
# The choke-hold window's loot walk: live (57,164); with the left-cell registry (owner 2026-11-13
# 「1と2だけ」) the loot walk does not step back into (56,165), the cell detected:prepare-choke
# left at 4044398, and commits to the pile at (55,163) instead -- the hold then interrupts that walk.
COMMITTED_LOOT = Position(55, 163)


class N1cLootLeft1113pmRecordedTest(recorded.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.full_pack = [row["board"] for row in rows if row["role"] == "full-pack"]
        cls.live = next(row for row in rows if row["role"] == "live-return")
        cls.choke_hold = [row["board"] for row in rows if row["role"] == "choke-hold"]
        cls.monrace = load_monrace_knowledge(recorded.EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(recorded.EDIT / "BaseitemDefinitions.jsonc")

    def filled(self, here=None):
        """The policy after the walk and the pickup, and the board that filled the pack."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        recorded.skill(policy, self.full_pack[-1])
        for raw in self.full_pack[:-1]:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                policy.confirm_key_posted(key)
        raw = copy.deepcopy(self.full_pack[-1])
        if here is not None:
            raw["player"]["y"], raw["player"]["x"] = here.y, here.x
        snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
        self.assertEqual((snapshot.turn, len(snapshot.inventory)), (self.live["turn"], 23))
        self.assertFalse(snapshot.floor_key[2])  # an ordinary floor: its return is not locked
        return policy, raw, snapshot

    def test_the_filled_pack_walks_to_the_dearer_item_instead_of_reading_recall(self):
        policy, raw, snapshot = self.filled()
        self.assertEqual((self.live["reason"], self.live["key"]), ("return:recall", "ri"))
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("9", full_pack_exchange.SEEK_REASON))
        self.assertFalse(policy._returning_to_town)
        accepted = self.post(policy, raw, key, [], self.later(raw))
        self.assertEqual(accepted, ["9"])

    def test_phase_door_is_a_teleport_necessity_the_exchange_keeps(self):
        policy, _raw, snapshot = self.filled()
        policy.choose_key(snapshot)
        self.assertTrue(any(item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_PHASE_DOOR
                            for item in snapshot.inventory))
        spare = full_pack_exchange.spare(policy, snapshot)
        self.assertEqual((spare.tval, spare.sval, spare.count), (70, 18, 1))  # 武器ダメージ増加
        cost = self.costs[(spare.tval, spare.sval)]
        worth = {position for position in policy._loot_candidates(snapshot)
                 if (full_pack_exchange.pile_value(policy, snapshot, position) or 0) > cost}
        self.assertEqual(worth, {HEAVY_CHAIN_MAIL, STAFF_OF_EARTHQUAKES})

    def test_on_the_pile_the_spare_is_destroyed(self):
        """Declared constructed: the filled board with the player moved onto the chain mail."""
        policy, _raw, snapshot = self.filled(HEAVY_CHAIN_MAIL)
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, full_pack_exchange.DESTROY_REASON)
        self.assertIsNotNone(key)

    def held(self, repeats=1):
        """The choke-hold window replayed; its last board decided ``repeats`` times."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        recorded.skill(policy, self.choke_hold[-1])
        for raw in self.choke_hold[:-1]:
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if key:
                policy.confirm_key_posted(key)
        self.assertEqual(policy._loot_target, COMMITTED_LOOT)
        for advanced in range(repeats):
            raw = copy.deepcopy(self.choke_hold[-1])
            raw["turn"] += advanced
            key = policy.choose_key(parse_snapshot(raw, self.monrace))
            self.assertEqual((key, policy.last_reason), ("5", "detected:hold-choke"))
            policy.confirm_key_posted(key)
        return policy

    def test_the_choke_hold_sets_the_loot_walk_aside(self):
        policy = self.held()
        self.assertIsNone(policy._loot_target)
        self.assertFalse(policy._nav_ledger.is_expired("loot", COMMITTED_LOOT))
        self.assertNotIn(("loot", COMMITTED_LOOT), policy._nav_ledger._progress)

    def test_a_long_hold_does_not_defer_the_loot_for_the_floor(self):
        """Declared constructed: the recorded hold board decided 40 times, a game turn apart
        (the live hold lasted 25 boards before the walk's goal was deferred)."""
        policy = self.held(repeats=40)
        self.assertNotIn(COMMITTED_LOOT, policy._deferred_loot)
        self.assertIn(COMMITTED_LOOT, policy._loot_candidates(
            parse_snapshot(copy.deepcopy(self.choke_hold[-1]), self.monrace)))


if __name__ == "__main__":
    import unittest
    unittest.main()
