"""The over-extension switch lasts 5, 10, 20 dives; then the deepest recall destination (C3, C5).

Owner 2026-11-11 (verbatim), C3 「5回で本来の行き先へ戻す」: 「切り替え先に5回潜ったら、一度本来の
行き先へ戻す。そこでまた厳しければ、次は10回、その次は20回と切り替えの期間を延ばす。」  C5
「一番深い帰還先」: 「帰還先の中で一番深い所（今ならメインのダンジョンの70階）で稼ぐ。」
(alternate_lease).  n1-b's alternate-dungeon.json of 2026-11-10 22:55 (copied in PLAN-50F's
directory) held the Orc cave as the over-extension alternate with no end but a conquest; all
three viewing characters were on it.

Recorded: n1-b life-367 (the same character as life-362; landings Angband 70, Castle 48,
Mountain 50, the Anti-melee cave 40, the Chameleon cave 30, the Orc cave 23, the conquered
Yeek cave, the maze and the Orc cave) through the castle-summoner-loot harness's public
``choose_key`` and observer (``_observe``, the public observer every decision runs); its
first board restores the alternate record exactly as written live (alternate-dungeon.json's
state), wired to the policy as cli.py wires it.
DECLARED CONSTRUCTED: the record's turn (the live record is from 22:55, the boards from 20:43,
and a record is restored only on a later board); the town and Orc-cave 23F boards of each dive
(the recorded board moved there, without monsters); the over-extended Angband dives (two
emergency escapes each: the escape decision named, as test_dungeon_escapes_counted_1109 does);
Angband's recall locked and the Castle's landing 64 (life-367 after 20:54) for C5.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import tests.test_castle_summoner_loot_1110_recorded as castle
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.policy_constants import EMPTY_DIVE_LIMIT
from tests.test_guardian_floor_above_1111_recorded import quiet

ORC_CAVE, CASTLE = 3, 12
LIVE_RECORD = {"turn": 5573602, "conquered": [2, 3, 4], "state": {
    "_alternate_dungeon": 3, "_alternate_dungeon_reason": "over_extended_dives",
    "_last_overextended_depth": 50, "_target_empty_dives": 0, "_guardian_bounce_dives": 0,
    "_no_depth_progress_dives": 0}}  # deep-dive-1110/alternate-dungeon.json


class AlternateLeaseRecordedTest(castle.CastleSummonerLootRecordedTest):
    test_no_pack_to_dig_for_keeps_the_recorded_destruction = None
    test_a_valuable_drop_asks_the_pocket_first = None
    test_no_valuable_drop_keeps_the_destruction = None

    def start(self, *, angband=True, castle_landing=None):
        record = self.root / "alternate-dungeon.json"
        live = copy.deepcopy(LIVE_RECORD)
        live["turn"] = self.boards[0]["turn"]
        record.write_text(json.dumps(live), encoding="utf-8")
        self.record = record
        if not angband or castle_landing is not None:
            self.boards = copy.deepcopy(self.boards)
            for raw in self.boards:
                raw["progress"]["angband_recall_unlocked"] = angband
                if castle_landing is not None:
                    raw["progress"]["dungeon_recall_depths"][str(CASTLE)] = castle_landing
        make_policy = castle._policy

        def wired(directory, monrace):
            policy = make_policy(directory, monrace)
            policy._alternate_dungeon_record_path = record  # as cli.py wires it
            return policy

        with mock.patch.object(castle, "_policy", wired):
            policy, _ = self.drive(quiet(self.boards[-1], 48))
        board = parse_snapshot(quiet(self.boards[-1], 48), self.monrace)
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (ORC_CAVE, "over_extended_dives"))
        self.turn = board.turn
        self.town = replace(board, floor_key=(0, 0, 0), town_flag=True)
        return policy, board

    def at(self, board, floor_key):
        self.turn += 100
        return replace(board, floor_key=floor_key, turn=self.turn)

    def dive(self, policy, board, floor_key, *, escapes=0):
        policy._observe(self.at(self.town, (0, 0, 0)))
        policy._observe(self.at(board, floor_key))
        for _ in range(escapes):
            policy.last_reason = "emergency:teleport"  # DECLARED: the escape decision
            policy._observe(self.at(board, floor_key))
        policy._observe(self.at(self.town, (0, 0, 0)))

    def test_five_orc_cave_dives_then_the_deepest_destination(self):
        policy, board = self.start()
        for number in range(1, 5):
            self.dive(policy, board, (ORC_CAVE, 23, 0))
            self.assertEqual(policy._alternate_dungeon, ORC_CAVE, number)
        self.assertEqual((policy._alternate_lease, policy._alternate_dives), (5, 4))
        self.dive(policy, board, (ORC_CAVE, 23, 0))
        # The Mountain 50F conquest target is refused as a landing (P3), so the deepest
        # destination holds: Angband 70.
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (DUNGEON_ANGBAND, "deepest_destination"))
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)

    def test_hard_again_the_next_switch_lasts_ten(self):
        policy, board = self.start()
        for _ in range(5):
            self.dive(policy, board, (ORC_CAVE, 23, 0))
        for _ in range(EMPTY_DIVE_LIMIT):
            self.dive(policy, board, (DUNGEON_ANGBAND, 70, 0), escapes=2)
        self.assertIsNotNone(policy._alternate_dungeon)
        self.assertEqual(policy._alternate_dungeon_reason, "over_extended_dives")
        self.assertEqual((policy._alternate_lease, policy._alternate_dives), (10, 0))

    def test_a_restart_keeps_the_lease(self):
        policy, board = self.start()
        for _ in range(3):
            self.dive(policy, board, (ORC_CAVE, 23, 0))
        stored = json.loads(Path(self.record).read_text(encoding="utf-8"))["state"]
        self.assertEqual((stored["_alternate_lease"], stored["_alternate_dives"]), (5, 3))

    def test_with_angband_shut_the_castle_64_is_the_deepest(self):
        """C5 with C2: the Castle's landing 64 (the floor above its guardian) qualifies; the
        Mountain 50 is P3's T1 guardian floor, the Anti-melee cave refuses melee."""
        policy, board = self.start(angband=False, castle_landing=64)
        for _ in range(5):
            self.dive(policy, board, (ORC_CAVE, 23, 0))
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (CASTLE, "deepest_destination"))
        self.assertEqual(policy._target_dungeon_id, CASTLE)


if __name__ == "__main__":
    unittest.main()
