"""Recorded pins: town native travel is never posted while the own grid is unseen.

Linux soak c4-a life-014 (Level 24), 2026-10-19 10:38-10:39, town at 22:22
right after a recall arrival.  The worn torch and the pack lantern both had
0 turns of fuel, so every board reported ``can_see_own_grid`` False (the
game's ``!no_lite()``; ``player.status.blind`` was False).  The bot posted the
native-travel macro ``\\x1b`n%.`` (shop:travel); travel-execution.cpp
``decide_travel_step_dir`` refuses every step when ``no_lite()`` or blind
("目が見えない！"), no new board followed, and the entry wait posted the empty
key until ``<no-key-exhausted>`` stopped the bot (twice, before and after a
restart).

Substrate: the restarted process's first three decision inputs, unchanged
(tests/extract_town_unseen_travel_fixture.py), replayed from a fresh policy
through the live response path.  The process restarted, so the fresh policy is
the recorded process's policy; the startup flag
enforce_crossarea_fundraising=True is the recorded one.

DECLARED CONSTRUCTED walls (controls only):
- ``lit``: the same rows with only ``player.can_see_own_grid`` set True -- an
  ordinary town arrival still travels natively;
- ``blind``: the same rows with only ``player.status.blind`` set True -- the
  existing status producer cures blindness with a carried potion first.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "town-unseen-travel-20261019.jsonl.gz"
FIXTURE_SHA256 = "5a3ecdb2a16a1e83c20ef1fb5b779787c4aedd0621fd9627670a729c6c074d81"
DECISIONS = FIXTURE.with_suffix(".decisions.json")
# Input rows consumed before each recorded decision 0, 1, 2.
GROUPS = (4, 2, 3)
TRAVEL_KEY = "\x1b`n%."
# #82: the replayed errand is the Home oil trip (see the comments below).
HOME_TRAVEL_KEY = "\x1b`n(."


def _rows(mode=None):
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    for row in rows:
        if row.get("type") != "player_turn":
            continue
        if mode == "lit":
            row["player"]["can_see_own_grid"] = True
        elif mode == "blind":
            row["player"]["status"]["blind"] = True
    return [json.dumps(row, ensure_ascii=False) + "\n" for row in rows]


class TownUnseenTravelRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        cls.recorded = json.loads(DECISIONS.read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, mode=None):
        lines = _rows(mode)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        policy = _policy(path, self.monrace)
        policy._crossarea_fundraising_enforced = True
        decided, boards, cursor = [], [], 0
        for count in GROUPS:
            _decoded, snapshots = _consume_response_sequence(
                lines[cursor:cursor + count], policy, lambda _key: True,
                self.monrace, knowledge_ledger_path=path / "knowledge.jsonl",
            )
            cursor += count
            board = snapshots[-1]
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            decided.append((key, policy.last_reason))
            boards.append(board)
        return decided, boards

    def test_recorded_process_posted_native_travel_on_unseen_grid(self):
        self.assertEqual(
            [(row["decision_sequence"], row["turn"], row["key"], row["reason"])
             for row in self.recorded],
            [(0, 1068208, "~f\x1b", "periodic:skill-exp-knowledge"),
             (1, 1068208, "~9\x1b\x1b", "home:request-knowledge-scan"),
             (2, 1068208, TRAVEL_KEY, "shop:travel")],
        )
        _decided, boards = self.replay()
        board = boards[2]
        self.assertTrue(board.in_town)
        self.assertIs(board.can_see_own_grid, False)
        self.assertFalse(board.player.blind)
        light = next(item for item in board.equipment if item.is_light)
        self.assertEqual(light.fuel, 0)

    def test_unseen_grid_walks_instead_of_native_travel(self):
        decided, _boards = self.replay()
        self.assertEqual(
            decided[:2],
            [(row["key"], row["reason"]) for row in self.recorded[:2]],
        )
        # #82, owner decision 2026-10-19 (light supply first): the Home lamp no
        # longer waives the lantern's oil, so the errand is the Home oil
        # withdrawal (Home holds the flasks); old ("4", Alchemist), new ("6", Home).
        self.assertEqual(decided[2], ("6", "shop:approach"))

    def test_control_lit_arrival_travels_as_recorded(self):
        decided, boards = self.replay("lit")
        self.assertIs(boards[2].can_see_own_grid, True)
        # #82, owner decision 2026-10-19 (light supply first): the Home lamp no
        # longer waives the lantern's oil, so the errand is the Home oil
        # withdrawal (Home holds the flasks); old TRAVEL_KEY (Alchemist), new HOME_TRAVEL_KEY.
        self.assertEqual(decided[2], (HOME_TRAVEL_KEY, "shop:travel"))

    def test_control_blind_arrival_cures_first(self):
        decided, boards = self.replay("blind")
        self.assertTrue(boards[2].player.blind)
        self.assertEqual(decided[2], ("qc", "item:cure-critical"))


FIXTURE_111025 = Path(__file__).parent / "fixtures" / "town-unseen-travel-111025.jsonl.gz"
FIXTURE_111025_SHA256 = "5fe2ab2bdebdade740959e0eab62693f52baf1136a5461be805525bbdc60dce0"
# Input rows consumed before each recorded decision 0..7 of the 111025 process.
GROUPS_111025 = (1, 2, 2, 1, 2, 1, 2, 1)


class TownTravelEndsUnseenRecordedTest(unittest.TestCase):
    """Round 2 (soak 2026-10-19 11:10:25, bot = ac9ed592 + round 1).

    The travel macro was posted from (33,104), whose own grid was lit
    (can_see_own_grid True), so the round-1 gate correctly allowed it.  Travel
    moved three cells into the dark and stopped at (34,107) with
    "目が見えない！" and can_see_own_grid False; the first decision after the post
    treated that board as the lagged entry surface and returned '' forever.

    The whole restarted process is replayed from a fresh policy.  DECLARED
    walls: (1) the CLI wall-clock timer that requested the recorded save and
    character dump is fired before decision 2, as recorded; (2) the recorded
    errand was the equipment transaction's Home trip (``\\x1b`n(.``), whose
    optimizer result is computed by a background worker that this replay does
    not run, so the replayed errand is the store-router's Alchemist trip
    (``\\x1b`n%.``).  Both go through _shopping_approach_key/_town_travel_key
    and arm the same store visit (phase entering, posted_sequence 6), so the
    board after the post meets the same entry wait; (3) ``provenance`` adds the
    executor's ``_completed_operation_sequence`` to that board as the live
    executor does (JSONL rows never carry it); both variants are pinned.
    """

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE_111025.read_bytes()).hexdigest() == (
            FIXTURE_111025_SHA256)
        cls.recorded = json.loads(
            FIXTURE_111025.with_suffix(".decisions.json").read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, provenance):
        with gzip.open(FIXTURE_111025, "rt", encoding="utf-8") as stream:
            lines = list(stream)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        policy = _policy(path, self.monrace)
        policy._crossarea_fundraising_enforced = True
        decided, boards, cursor = [], [], 0
        for index, count in enumerate(GROUPS_111025):
            segment = lines[cursor:cursor + count]
            cursor += count
            if index == 2:
                policy.request_game_save()
                policy.request_character_dump()
            visit = policy._store_visit
            if provenance and visit is not None and visit.posted_sequence is not None:
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = visit.posted_sequence
                segment[-1] = json.dumps(row, ensure_ascii=False) + "\n"
            _decoded, snapshots = _consume_response_sequence(
                segment, policy, lambda _key: True,
                self.monrace, knowledge_ledger_path=path / "knowledge.jsonl",
            )
            board = snapshots[-1]
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            decided.append((key, policy.last_reason))
            boards.append(board)
        return decided, boards

    def test_recorded_travel_from_lit_grid_then_empty_entry_wait(self):
        self.assertEqual(
            [(row["decision_sequence"], row["turn"], row["key"], row["reason"])
             for row in self.recorded[4:]],
            [(4, 1068217, "6", "equipment-transaction:approach-home"),
             (5, 1068229, "6", "equipment-transaction:approach-home"),
             (6, 1068238, "\x1b`n(.", "equipment-transaction:travel-home"),
             (7, 1068268, "", "store:entry-await-observation")],
        )
        decided, boards = self.replay(provenance=False)
        self.assertEqual(
            decided[:4], [(row["key"], row["reason"]) for row in self.recorded[:4]])
        self.assertIs(boards[6].can_see_own_grid, True)
        # #82, owner decision 2026-10-19 (light supply first): the Home lamp no
        # longer waives the lantern's oil, so the errand is the Home oil
        # withdrawal (Home holds the flasks); old TRAVEL_KEY (Alchemist), new HOME_TRAVEL_KEY.
        self.assertEqual(decided[6], (HOME_TRAVEL_KEY, "shop:travel"))
        self.assertIs(boards[7].can_see_own_grid, False)
        self.assertEqual(boards[7].player.position.y, 34)
        self.assertEqual(boards[7].player.position.x, 107)
        self.assertIn("目が見えない！", boards[7].messages)

    def test_unseen_end_of_travel_releases_entry_wait_and_walks(self):
        for provenance in (False, True):
            with self.subTest(provenance=provenance):
                decided, _boards = self.replay(provenance)
                # #82, owner decision 2026-10-19 (light supply first): the Home lamp no
                # longer waives the lantern's oil, so the errand is the Home oil
                # withdrawal (Home holds the flasks); old step "7" (toward the Alchemist), new "3" (toward Home).
                self.assertEqual(decided[7], ("3", "store:entry-interrupted-replan"))


if __name__ == "__main__":
    unittest.main()
