"""n1-c life-205 2026-11-13 18:54: a fallback lands no shallower than the deepest reached - 20.

Owner 2026-11-13 (verbatim): 「n1-cがまた23Fに落ちている。フォールバックは最新到達-20Fまでにする。」
(fallback_depth_floor).

Recorded (tests/extract_n1c_205_fallback_depth_1113_fixture.py): the town arrival of the Lv46
Magic-Eater after an Orc cave 23F dive (pack-full).  The arrival policy holds the over-extension
switch made at the Mountain (14) 50F -- the Orc cave (3), the deepest entered landing below 50
that passed the checks -- on its fifth doubled lease (80 dives, 59 done), as the live
alternate-dungeon.json shows.  Recall landings: Angband 80, dungeon 12 62, dungeon 20 60, the
Mountain 50, dungeon 18 30, the Orc cave 23, dungeon 4 18, Forest 15, the Yeek cave 13.  The
deepest reached is 80 (the saved landings; the arrival policy's ``_deepest_level`` is 23, seeded
from the Orc cave after a restart), so the floor is 60.  Row 0 observes the arrival, row 50 read
Word of Recall to the Orc cave (``rgc`` town:recall-to-alt-dungeon).  Every decision is the
public ``choose_key`` on the restored arrival policy; rows 0-49 replay as recorded on the
unfixed and the fixed code, and the read is posted through the production ``_ExecutorInputPort``.
DECLARED CONSTRUCTED: the read prompt, the chooser screen (its rows in the game's format,
dungeon-service.cpp, names from the dungeon knowledge) and the game's reply; the controls'
landings and entered dungeons (named in each test).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hengbot import alternate_lease, fallback_depth_floor, random_quest_hold
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE
from tests.support import recorded as executor_pins
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-205-fallback-depth-1113"
ORC_CAVE, MOUNTAIN, DUNGEON_12, DUNGEON_20 = 3, 14, 12, 20
LANDINGS = {1: 80, 12: 62, 14: 50, 18: 30, 2: 13, 20: 60, 3: 23, 4: 18, 7: 15}
RECALL_ROW = 50
READ_PROMPT = "どの巻物を読みますか? "
CHOOSER = "どのダンジョンに帰還しますか:"


class FallbackDepthFloorVisit(RecordedVisit):
    fixtures = FIXTURES
    fixture = "visit"

    def arrival(self):
        board, _key, _reason = self.decide(0)
        return board


class FallbackDepthFloorRecordedTest(FallbackDepthFloorVisit):
    def test_arrival_policy_holds_the_orc_cave_switch(self):
        policy = self.policy
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason,
                          policy._last_overextended_depth), (ORC_CAVE, "over_extended_dives", 50))
        self.assertEqual((policy._alternate_lease, policy._alternate_dives), (80, 59))
        self.assertEqual(policy._deepest_level, 23)
        self.assertEqual((self.journal[RECALL_ROW]["key"], self.journal[RECALL_ROW]["reason"]),
                         ("rgc", "town:recall-to-alt-dungeon"))

    def test_the_arrival_ends_the_switch_under_the_floor(self):
        board = self.arrival()
        policy = self.policy
        self.assertEqual(dict(board.dungeon_recall_depths), LANDINGS)
        self.assertEqual(fallback_depth_floor.floor(policy, board), 60)
        # Unfixed: the Orc cave 23F stays the target for the lease's last 21 dives.
        self.assertIsNone(policy._alternate_dungeon)
        # The switch ended as a finished lease ends (C5): the conquest target whose landing
        # may be taken, dungeon 20's 60.
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (DUNGEON_20, "conquest"))

    def test_the_over_extended_mountain_takes_no_landing_under_sixty(self):
        """The valve's question at the Mountain 50F: nothing below 50 is at 60 or deeper, so no
        switch (the next rules decide); unfixed it answered the Orc cave."""
        board = self.arrival()
        policy = self.policy
        policy._alternate_dungeon = None  # the switch the arrival ended (unfixed: still held)
        policy._last_overextended_depth = LANDINGS[MOUNTAIN]
        self.assertIsNone(policy._pick_alternate_dungeon(board, prefer_deepest=True))

    def test_the_recall_read_lands_at_sixty(self):
        for row in range(RECALL_ROW):
            _board, key, reason = self.decide(row)
            self.assertEqual((key, reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
        board, key, reason = self.decide(RECALL_ROW)
        letter = chr(ord("a") + board.entered_dungeon_ids.index(DUNGEON_20))
        # Unfixed (live, and replayed on the unfixed code): 'rgc', the Orc cave 23F.
        self.assertEqual((key, reason), ("rg" + letter, "town:recall-to-alt-dungeon"))
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_20], 60)
        accepted, sent = self.post_read(board, key, reason)
        self.assertTrue(sent)
        self.assertEqual(accepted, ["r", "g", letter])

    def post_read(self, board, key, reason):
        entry = self.journal[RECALL_ROW]
        raw = json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])
        chooser = executor_pins.prompt_screen(CHOOSER)
        for index, did in enumerate(board.entered_dungeon_ids):
            info = self.policy._dungeon_knowledge.get(did)
            chooser["lines"][2 + index] = " " * 14 + "      {}) {:<12} : 最大 {} 階".format(
                chr(ord("a") + index), info.name if info else str(did),
                board.dungeon_recall_depths.get(did, 0))
        screens = [executor_pins.prompt_screen(READ_PROMPT), chooser,
                   executor_pins.command_screen(raw["turn"] + 1)]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = screens
        game.states = [copy.deepcopy(raw) for _ in screens]
        game.states[-1]["turn"] = raw["turn"] + 1
        game.states[-1]["player"]["recalling"] = True
        harness = executor_pins.ProductionHarness()
        harness.addCleanup = self.addCleanup
        _game, _client, executor = harness.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence, "reason": reason},
            snapshot=board, posting_contract=PostingContract())
        return game.accepted, sent


class FallbackDepthFloorControlTest(FallbackDepthFloorVisit):
    """Constructed controls on the recorded arrival board."""

    def test_deepest_thirty_floor_ten_keeps_the_orc_cave(self):
        # DECLARED CONSTRUCTED: every landing at most 30 (Angband 30, 12 and 20 left out).
        board = self.arrival()
        policy = self.policy
        shallow = {1: 30, 14: 28, 18: 30, 2: 13, 3: 23, 4: 18, 7: 15}
        board = replace(board, dungeon_recall_depths=shallow,
                        entered_dungeon_ids=tuple(sorted(shallow)))
        self.assertEqual(fallback_depth_floor.floor(policy, board), 10)
        policy._alternate_dungeon = None
        policy._last_overextended_depth = 28
        self.assertEqual(policy._pick_alternate_dungeon(board, prefer_deepest=True), ORC_CAVE)

    def test_the_deepest_destination_lands_at_the_floor_or_deeper(self):
        """C5's deepest recall destination: Angband 80 on the recorded board."""
        board = self.arrival()
        self.assertEqual(alternate_lease.deepest_destination(self.policy, board),
                         DUNGEON_ANGBAND)

    def test_the_deepest_destination_under_the_floor_is_none(self):
        # DECLARED CONSTRUCTED: Angband 80, 62 and 60 refused at their landings, so the deepest
        # destination left is the Mountain 50, under the floor 60.  Unfixed: the Mountain.
        board = self.arrival()
        policy = self.policy
        refused = {DUNGEON_ANGBAND, DUNGEON_12, DUNGEON_20}
        safe = policy._recall_destination_safe
        with mock.patch.object(policy, "_recall_destination_safe",
                               side_effect=lambda snap, did: did not in refused and safe(snap, did)):
            self.assertIsNone(alternate_lease.deepest_destination(policy, board))
            # An Orc cave held as the deepest destination (DECLARED CONSTRUCTED: a switch made
            # before the rule) is ended too, and nothing under the floor replaces it.
            policy._alternate_dungeon = ORC_CAVE
            policy._alternate_dungeon_reason = alternate_lease.DEEPEST_REASON
            self.assertTrue(fallback_depth_floor.settle(policy, board))
        self.assertIsNone(policy._alternate_dungeon)

    def test_guardian_valve_skips_a_shallow_angband(self):
        # DECLARED CONSTRUCTED: Angband's landing 30 (deepest reached stays 62: floor 42); a
        # Mountain bounce takes the shallowest other landing at 42 or deeper.  Unfixed: Angband.
        board = self.arrival()
        policy = self.policy
        board = replace(board, dungeon_recall_depths={**LANDINGS, DUNGEON_ANGBAND: 30})
        policy._alternate_dungeon = None
        self.assertEqual(policy._pick_alternate_dungeon(board, guardian_bounced_dungeon=MOUNTAIN),
                         DUNGEON_20)

    def test_a_conquest_target_under_the_floor_is_kept(self):
        """Owner 2026-11-13 (answer 「征服には当てない」): the floor is not read by the conquest
        target.  DECLARED CONSTRUCTED: the latch on the Mountain (unconquered, its bottom 50
        within the resistance limit) instead of dungeon 20; its landing 50 is under the floor
        60 and it is still the target once the Orc cave switch ends."""
        policy = self.policy
        policy._conquest_committed = MOUNTAIN
        board = self.arrival()
        self.assertLess(board.dungeon_recall_depths[MOUNTAIN],
                        fallback_depth_floor.floor(policy, board))
        self.assertIsNone(policy._alternate_dungeon)
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (MOUNTAIN, "conquest"))

    def test_the_random_quest_hold_keeps_its_deepest_open_floor(self):
        """Owner 2026-11-13 (answer 「Q2 前は当てない」): the floor is not read here."""
        # DECLARED CONSTRUCTED: Q2's hold active, 12 and 20 not entered: the deepest open landing
        # is the Mountain 50, under the floor 60 -- the hold's own choice, not a fallback.
        board = self.arrival()
        policy = self.policy
        entered = tuple(did for did in board.entered_dungeon_ids
                        if did not in (DUNGEON_12, DUNGEON_20))
        board = replace(board, entered_dungeon_ids=entered, yeek_cave_conquered=True)
        policy._alternate_dungeon = None
        with mock.patch.object(random_quest_hold, "hold_active", return_value=True):
            random_quest_hold.settle_target(policy, board)
        self.assertNotEqual(policy._target_dungeon_id, DUNGEON_YEEK_CAVE)
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (MOUNTAIN, random_quest_hold.DEEPEST_OPEN_REASON))


if __name__ == "__main__":
    unittest.main()
