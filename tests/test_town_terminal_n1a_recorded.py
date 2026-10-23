"""ROOT-FIX S1: the quest rung asks its entry admission before taking a board.

Fixture ``fixtures/n1a-townalt-20261023.jsonl.gz`` holds four raw
``player_turn`` boards of the n1-a stops of 2026-10-23 (bot 062241f2, town 1,
quest 2 TAKEN, entrance (25,47)): rows 0/1 are turns 534279 (24,48) and
534285 (23,49) of capture 20261023-183351-loop-detected, rows 2/3 are turns
534891 (27,46) and 534903 (26,46) of 20261023-183418-town-blocked-owner-
retired-burst.  Live, quest-request ('1' / '8' quest:enter:approach) and the
Morivant full-identify trip alternated 1,446 times.

Measured at 062241f2 (LUNA-DIAG-townalt.txt): the quest owner's keys were
None, '1', '8', None with the live entry verdict False, and '1', '1', '8',
'9' with it True.

DECLARED WALL: a fresh policy has no character calibration, so the real
``_equipment_departure_ready`` admits through its calibration branch.  The
tests patch it to the live value (False, refused by the two pack items that
wait for *Identify*: code ``identification-flow``) or to True for the
control, and give the policy the live Morivant expedition (travel phase,
origin town 1).  Boards moved along the inn route with ``dataclasses.replace``
are DECLARED CONSTRUCTED.
"""

import tests  # noqa: F401

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot import town_terminal
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import TOWN_TRAVEL_STALL_LIMIT
from hengbot.policy_types import (
    DecisionContext,
    MorivantFullIdentifyExpedition,
    TownTeleportRoute,
)
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.town_maps import find_outpost_map, find_town_map, parse_town_map
from hengbot.town_terminal import Server, TerminalRef


FIXTURE = Path(__file__).parent / "fixtures" / "n1a-townalt-20261023.jsonl.gz"
TURNS = (534279, 534285, 534891, 534903)
ENTRY = TerminalRef("quest-entry", (2,))
RUNG = "_fixed_quest_key#2"


def _town_maps():
    maps = {0: parse_town_map(find_outpost_map(Path(__file__)))}
    for town_index in range(2, 6):
        path = find_town_map(town_index, Path(__file__))
        if path is not None:
            maps[town_index - 1] = parse_town_map(path)
    return maps


def _entry_ready(ready):
    def fake(self, snapshot, *, destination_depth=None, commit=True, codes=None):
        if not ready and codes is not None:
            codes.append("identification-flow")
        return ready
    return fake


class N1aTerminalAdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [parse_snapshot(json.loads(line), {}) for line in stream]
        cls.maps = _town_maps()

    def policy(self, board, sequence=1):
        policy = HengbotPolicy(town_map=self.maps[0], town_maps=self.maps)
        policy._build_grid_index(board)
        self.decide(policy, board, sequence)
        policy._morivant_full_identify = MorivantFullIdentifyExpedition(
            origin_town_id=1, target_signatures=(("katana", 0, 0), ("hammer", 0, 0)))
        return policy

    @staticmethod
    def decide(policy, board, sequence):
        policy._map_predicate_snapshot = board
        policy._decision_context = DecisionContext(
            equipment_transaction_owned=False, identity=sequence)
        policy._decision_sequence = sequence
        policy._decision_terminal_admissions = []

    @staticmethod
    def quest_key(policy, board):
        return policy._town_producer_entry(
            RUNG, lambda: QuestFloorNavigator.enter_from_town(policy, board, 2))

    def test_recorded_boards(self):
        self.assertEqual(tuple(board.turn for board in self.boards), TURNS)
        for board in self.boards:
            self.assertTrue(board.in_town)
            self.assertEqual(board.quests[2].status, 1)
            self.assertTrue(board.grid_at(Position(25, 47)).has_quest_enter)

    def test_refused_entry_yields_without_the_claim_switch(self):
        expected_live = ["1", "1", "8", "9"]
        for board, live_ready_key in zip(self.boards, expected_live):
            with self.subTest(turn=board.turn):
                policy = self.policy(board)
                self.assertFalse(getattr(policy, "_town_claim_bar_enforced", False))
                with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)):
                    self.assertIsNone(self.quest_key(policy, board))
                self.assertIsNone(policy._town_blocked_reason)
                record, = policy._decision_terminal_admissions
                self.assertEqual(record["terminal"], ["quest-entry", [2]])
                self.assertEqual(record["codes"], ["identification-flow"])
                self.assertEqual(record["live"], [["cross-town", None]])
                self.assertIsNone(record["closed"])
                # Control: the admitted entry keeps today's approach.
                policy = self.policy(board)
                with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(True)):
                    key = self.quest_key(policy, board)
                self.assertEqual(None if key is None else str(key), live_ready_key)
                self.assertFalse(policy._decision_terminal_admissions)

    def test_walk_to_the_inn_keeps_yielding(self):
        board = self.boards[1]
        policy = self.policy(board)
        steps = 0
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)):
            while True:
                steps += 1
                self.decide(policy, board, steps)
                self.assertIsNone(self.quest_key(policy, board))
                record, = policy._decision_terminal_admissions
                self.assertIsNone(record["closed"])
                self.assertLess(record["yields"], 2)
                route = policy._town_teleport_route(board, 2).route
                if route is None or route.remaining_edges == 0 or steps > 60:
                    break
                board = replace(board, player=replace(board.player, position=route.first_step))
                policy._build_grid_index(board)
        self.assertGreater(steps, 3)
        self.assertLessEqual(steps, 60)
        self.assertEqual(policy._town_visit_ledger.closed_terminals, {})

    def test_yields_without_server_progress_close_the_entry(self):
        board = self.boards[1]
        policy = self.policy(board)
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)):
            for sequence in range(1, TOWN_TRAVEL_STALL_LIMIT + 2):
                self.decide(policy, board, sequence)
                self.assertIsNone(self.quest_key(policy, board))
        ledger = policy._town_visit_ledger
        self.assertEqual(ledger.terminal_yields[ENTRY], TOWN_TRAVEL_STALL_LIMIT)
        self.assertEqual(ledger.closed_terminals, {ENTRY: "yield-without-server-progress"})

    def test_unroutable_trip_is_not_progress(self):
        board = self.boards[1]
        policy = self.policy(board)
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)), \
                patch.object(HengbotPolicy, "_town_teleport_route",
                             return_value=TownTeleportRoute(failure="route-unavailable")):
            self.assertIsNone(self.quest_key(policy, board))
        self.assertEqual(policy._town_visit_ledger.closed_terminals,
                         {ENTRY: "terminal-refused-unserved:identification-flow"})

    def test_identification_is_served_by_the_cross_town_trip(self):
        self.assertIn(Server("cross-town"),
                      town_terminal.REFUSAL_SERVERS["identification-flow"])
        board = self.boards[1]
        policy = self.policy(board)
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)), \
                patch.dict(town_terminal.REFUSAL_SERVERS, {
                    "identification-flow": (Server("identification"),)}):
            self.assertIsNone(self.quest_key(policy, board))
        self.assertEqual(policy._town_visit_ledger.closed_terminals,
                         {ENTRY: "terminal-refused-unserved:identification-flow"})

    def test_reward_terminal_is_not_the_refused_entry(self):
        board = self.boards[1]
        policy = self.policy(board)
        policy._fixed_quest_reward_pending = 2
        self.assertEqual(town_terminal.fixed_quest_intended_terminal(policy, board),
                         TerminalRef("quest-reward", (2,)))
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)):
            self.assertEqual(policy._town_producer_entry(RUNG, lambda: "reward"), "reward")
        self.assertFalse(policy._decision_terminal_admissions)

    def test_material_read_does_not_commit(self):
        board = self.boards[1]
        policy = self.policy(board)
        policy._morivant_full_identify = None
        with patch.object(HengbotPolicy, "_equipment_departure_ready", _entry_ready(False)):
            material = town_terminal.gather_quest_entry(policy, board, 2)
            self.assertIsNone(policy._town_blocked_reason)
            self.assertFalse(policy._quest_equipment_entry_allowed(board, 2))
        self.assertEqual(town_terminal.verdict_quest_entry(material).codes,
                         ("identification-flow",))
        self.assertEqual(policy._town_blocked_reason, "equipment-departure-incomplete")

    def test_q34_readiness_reason_is_committed_only_at_the_entry(self):
        board = self.boards[1]
        policy = self.policy(board)
        policy._morivant_full_identify = None
        policy.last_reason = "before"
        with patch.object(HengbotPolicy, "_opening_q34_active", return_value=True):
            material = town_terminal.gather_quest_entry(policy, board, 34)
            self.assertEqual(policy.last_reason, "before")
            self.assertEqual(policy._fixed_quest_readiness, {})
            self.assertFalse(policy._quest_equipment_entry_allowed(board, 34))
        self.assertEqual(town_terminal.verdict_quest_entry(material).codes, ("not-in-town",))
        self.assertEqual(policy.last_reason, "quest:readiness:not-in-town")
        self.assertEqual(policy._fixed_quest_readiness["reason"], "not-in-town")


if __name__ == "__main__":
    unittest.main()
