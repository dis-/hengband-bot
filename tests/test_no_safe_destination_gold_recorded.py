"""No safe recall landing above the fundraising gold target (c4-a life-014).

Capture 2026-10-19 23:16:44 (bot dcf664fa, the restarted process; extracted
by tests/extract_no_safe_dest_gold_fixture.py): Level 28, gold 20,238, in
town after a mining set.  Angband lands on 26 (missing resist_acid,
resist_elec); the other entered dungeons land on 23 (Forest, missing
free_action), 25 and 30, and no fixed quest is ready.  Before the fix the
no-safe-destination fundraising set refused to open at or above
FUNDRAISING_GOLD_TARGET, so the recorded boards ended in
``town:blocked:depth-gate:destination-26:missing-resist_acid,resist_elec``
(decision row 6) and later ``owner-retired-burst``.

OWNER DECISION 2026-10-19 (AskUserQuestion answer, verbatim: 「金額に関係なく
資金稼ぎ (Recommended)」; extends the 2026-10-02 decision): with no safe landing
the town fundraises at the Yeek cave whatever the gold; the set does not end
by gold and returns after the ordinary run count; the depth requirements are
not relaxed.

Substrate: the restarted process's state rows replayed through the public
response path on one fresh policy (live argv: --crossarea-fundraising,
--in-store-shop-ops).  Each decision consumes its drained record count; the
last decision of a game turn also consumes that turn's remaining rows
(decision row 3's store-observation row).  Rows 0..4 reproduce the live keys;
the set opens during decision 4 (its key is the periodic save that rides
the board), so decision 5 is the first changed key and no later recorded
board is consumed (R4).

DECLARED WALL (control only): ``with_abilities`` adds abilities to every
replayed board's player; it is the board WITH the required abilities.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import dataclasses
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    SV_DIGGING_SHOVEL,
    STORE_ALCHEMIST,
    STORE_HOME,
    TVAL_DIGGING,
    Position,
    Snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (
    FUNDRAISING_GOLD_TARGET,
    FUNDRAISING_START_GOLD,
    TOWN_TRAVEL_STORE_SYMBOLS,
)
from hengbot.policy_state import normalize_policy_state
from policy_fixtures import grid, item, player
from policy_shop_fixture import _TownShopFixtureBase
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures/no-safe-dest-gold-20261019.json.gz"
SHA256 = "acb1c9616ca25eba0e74ff685ab8bd1692d92087504dd9d4311998a3665f8b4d"
RECORDED_GOLD = 20238
FIRST_CHANGED = 5
BLOCKED = ("1", "town:blocked:depth-gate:destination-26:"
                "missing-resist_acid,resist_elec")


def _segments(lines, decisions):
    """Drained counts in order; a turn's last decision takes its leftovers."""
    turns = [json.loads(line)["turn"] for line in lines]
    cursor = 0
    for index, decision in enumerate(decisions):
        end = cursor + decision["drained"]
        following = decisions[index + 1]["turn"] if index + 1 < len(decisions) else None
        while (end < len(lines) and turns[end] == decision["turn"]
               and following != decision["turn"]):
            end += 1
        yield index, lines[cursor:end]
        cursor = end


class NoSafeDestinationGoldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay(self, last, *, with_abilities=frozenset()):
        """Replay decisions 0..last; return (keys, policy, boards)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv
        decisions = self.pin["decisions"]
        keys, boards = [], []
        previous = None
        for index, segment in _segments(self.pin["lines"], decisions):
            if index > last:
                break
            recorded = decisions[index]
            if previous is not None and previous["key"]:
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, parsed = _consume_response_sequence(
                segment, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = parsed[-1]
            if with_abilities:
                board = dataclasses.replace(board, player=dataclasses.replace(
                    board.player, abilities=board.player.abilities | with_abilities))
            if index == 0:
                policy.prime(board)
            if recorded["reason"] == "periodic:game-save":
                policy.request_game_save()
            elif recorded["reason"] == "periodic:character-dump":
                policy.request_character_dump()
            key = policy.choose_key(board)
            keys.append((str(key), policy.last_reason))
            boards.append(board)
            policy.confirm_key_posted(key)
            previous = recorded
        return keys, policy, boards

    def _live(self, index):
        decision = self.pin["decisions"][index]
        return decision["key"], decision["reason"]

    def test_board_facts(self):
        self.assertEqual(self._live(6), BLOCKED)
        keys, policy, boards = self._replay(FIRST_CHANGED - 1)
        board = boards[-1]
        self.assertEqual(board.player.gold, RECORDED_GOLD)
        self.assertGreaterEqual(board.player.gold, FUNDRAISING_GOLD_TARGET)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 26)
        self.assertEqual(policy._missing_required_abilities(board, 26),
                         frozenset({"resist_acid", "resist_elec"}))
        self.assertEqual(policy._missing_required_abilities(board, 23),
                         frozenset({"free_action"}))
        self.assertFalse(policy._fixed_quest_ready_for_travel(board, 18))

    def test_set_opens_above_the_gold_target(self):
        keys, policy, boards = self._replay(FIRST_CHANGED)
        self.assertEqual(keys[:FIRST_CHANGED],
                         [self._live(index) for index in range(FIRST_CHANGED)])
        board = boards[-1]
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._no_safe_destination_set)
        # The gate is not relaxed: the landing is still refused.
        self.assertFalse(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertEqual(
            [(need.store_type, need.category)
             for need in policy._town_need_candidates(board)],
            [(STORE_HOME, "fundraising-kit"),
             (STORE_ALCHEMIST, "fundraising-detection")])
        # First changed key (live: the periodic character dump, then the
        # named depth-gate stop on row 6): travel to the Home for the kit.
        self.assertEqual(self._live(FIRST_CHANGED),
                         ("Cf\ry\x1b\x1b", "periodic:character-dump"))
        self.assertEqual(
            keys[FIRST_CHANGED],
            (f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[STORE_HOME]}.", "shop:travel"))

    def test_gold_end_leaves_the_set_and_the_run_count_ends_it(self):
        _keys, policy, boards = self._replay(FIRST_CHANGED)
        board = boards[-1]
        policy._end_fundraising_set_at_gold_target(board)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._no_safe_destination_set)
        for mode in ("mine", "scavenge"):
            with self.subTest(mode=mode), patch.object(
                    policy, "_fundraising_supplies_ready", return_value=False):
                # Supplies not ready: a scavenge set is not promoted to mine
                # on this board (the detectionless set the run count ends).
                policy._fundraising_mode = mode
                policy._mining_runs_completed = policy._effective_mining_run_target()
                policy._town_special_key(board)
                self.assertIsNone(policy._fundraising_mode)
                self.assertFalse(policy._no_safe_destination_set)
                policy._no_safe_destination_set = True

    def test_control_board_with_the_abilities_departs_normally(self):
        abilities = frozenset({"free_action", "resist_acid", "resist_elec"})
        keys, policy, boards = self._replay(4, with_abilities=abilities)
        self.assertEqual(keys[:4], [self._live(index) for index in range(4)])
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)
        self.assertTrue(policy._recall_destination_safe(boards[-1], DUNGEON_ANGBAND))
        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(getattr(policy, "_no_safe_destination_set", False))
        # The pre-dive character sheet of the ordinary departure (the board
        # where the live run opened the set instead).
        self.assertEqual(keys[4], ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertTrue(policy._char_dump_done_this_visit)


class NoSafeDestinationSetRunTest(_TownShopFixtureBase):
    """The set's gold objective and run count on synthetic boards."""

    def _yeek_board(self, *, gold, detection=3):
        return Snapshot(
            player(10, 10, gold=gold, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10, upstairs=True)},
            [],
            floor_key=(DUNGEON_YEEK_CAVE, 1, 0),
            inventory=self._strict_supplies(recall=0, detection=detection),
            equipment=[
                item("main_hand", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True),
                self._lantern(),
            ],
        )

    def test_mining_at_the_gold_target_keeps_running_in_the_set(self):
        board = self._yeek_board(gold=FUNDRAISING_GOLD_TARGET)
        control = HengbotPolicy()
        control._fundraising_mode = "mine"
        self.assertEqual(control.choose_key(board), "<")
        self.assertEqual(control.last_reason, "fundraise:ascend")
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        policy._no_safe_destination_set = True
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "fundraise:ascend")
        self.assertTrue(policy.last_reason.startswith("fundraise:"))

    def test_no_gold_objective_in_the_run_verdict(self):
        board = self._yeek_board(gold=FUNDRAISING_GOLD_TARGET)
        policy = HengbotPolicy()
        policy._fundraising_mode = "mine"
        self.assertTrue(policy._fundraising_facts(board).objective_achieved)
        policy._no_safe_destination_set = True
        self.assertFalse(policy._fundraising_facts(board).objective_achieved)

    def test_a_scavenge_return_counts_as_a_run(self):
        town = Snapshot(
            player(10, 10, gold=FUNDRAISING_GOLD_TARGET, class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)},
            [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        counted = {}
        for flag in (False, True):
            policy = HengbotPolicy()
            policy._fundraising_mode = "scavenge"
            policy._no_safe_destination_set = flag
            policy._floor_key = (DUNGEON_YEEK_CAVE, 1, 0)
            policy._observe(town)
            counted[flag] = policy._mining_runs_completed
        self.assertEqual(counted, {False: 0, True: 1})

    def test_control_ordinary_set_still_ends_at_the_gold_target(self):
        poor = Snapshot(
            player(10, 10, gold=FUNDRAISING_START_GOLD - 1,
                   class_id=PLAYER_CLASS_WARRIOR),
            {Position(10, 10): grid(10, 10)}, [],
            inventory=self._strict_supplies(recall=0),
            equipment=[self._lantern()],
        )
        policy = HengbotPolicy()
        # A flag left by a set that ended through another path.
        policy._no_safe_destination_set = True
        self.assertTrue(policy._start_fundraising(poor))
        self.assertFalse(policy._no_safe_destination_set)
        rich = dataclasses.replace(poor, player=dataclasses.replace(
            poor.player, gold=FUNDRAISING_GOLD_TARGET))
        policy._end_fundraising_set_at_gold_target(rich)
        self.assertIsNone(policy._fundraising_mode)

    def test_flag_defaults(self):
        policy = HengbotPolicy()
        self.assertIs(policy.__dict__["_no_safe_destination_set"], False)
        del policy.__dict__["_no_safe_destination_set"]
        normalize_policy_state(policy, restart=True)  # restored checkpoint
        self.assertIs(policy.__dict__["_no_safe_destination_set"], False)


if __name__ == "__main__":
    unittest.main()
