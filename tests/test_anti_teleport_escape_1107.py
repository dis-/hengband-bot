"""A worn anti-teleport piece and the dungeon escape (threat tiers 4.2, plan step 3).

Game (C:/hengband/src): a worn NO_TELE piece sets ``anti_tele`` and the game
refuses Teleportation and Phase Door (teleport_player_aux,
spells-teleport.cpp:286-289) and Teleport Level (teleport_level,
spells-world.cpp:80-83) with 「不思議な力がテレポートを防いだ！」.  Before this
change the dungeon escape finders never read ``_teleport_blocked_by_equipment``,
so the bot read a scroll the game refuses.

Owner 2026-11-07 (answer 8) 「逃げる手段を取り戻すのが先」: a removable piece
(not cursed: do_cmd_takeoff refuses a cursed one, cmd-equipment.cpp:372-389)
comes off first, then the escape is read; with a cursed piece no relocation
scroll is offered and the rung falls to its next answer.  Inside an approved
quest plan the plan decides (answer 11): Q25 wears its piece on purpose
(tests/test_q25_phase_battle.py ``Q25DrujGearTest`` keeps its walk-out retreat).

Board: the recorded n1-a adjacent-paralyzer board (turn 3305879,
tests/fixtures/incident-paralyzer-adjacent-escape.jsonl), where the bot reads
its Teleportation (``status-threat:scroll``), through the public ``choose_key``.
DECLARED CONSTRUCTED: NO_TELE (TR flag 68) known on a worn piece, cursed or not.
And the recorded Forest 32F board 534 (``emergency:teleport``), for the
emergency composer.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, READ_KEY
from hengbot.quest_strategies import load_quest_strategies
from tests import policy_fixtures as fixtures
from tests import test_immobile_summoner_recorded as summoner
from tests import test_low_hp_no_unchecked_walk as low_hp
from tests import test_policy_combat as combat
from tests.test_policy import item

TR_NO_TELE = 68
TAKEOFF_REASON = "escape:take-off-anti-teleport"


class WornAntiTeleportEscapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = combat.paralyzer_escape_snapshots(combat.PARALYZER_ESCAPE_KNOWLEDGE)[3305879]

    def _wearing(self, *, cursed=False):
        piece = next(item for item in self.board.equipment if item.slot != "main_hand")
        worn = replace(piece, known_flags=frozenset({*piece.known_flags, TR_NO_TELE}),
                       is_cursed=cursed)
        board = replace(self.board, equipment=[
            worn if item is piece else item for item in self.board.equipment])
        return board, worn

    def _choose(self, board):
        policy = HengbotPolicy(monrace_knowledge=combat.PARALYZER_ESCAPE_KNOWLEDGE)
        return str(policy.choose_key(board)), policy.last_reason

    def test_control_the_recorded_board_reads_teleportation(self):
        self.assertEqual(self._choose(self.board), (READ_KEY + "e", "status-threat:scroll"))

    def test_a_removable_piece_comes_off_before_the_escape(self):
        board, worn = self._wearing()
        key, reason = self._choose(board)
        self.assertNotEqual(key, READ_KEY + "e", reason)   # the read the game refuses
        self.assertEqual(reason, TAKEOFF_REASON, key)
        self.assertEqual(key, "t" + EQUIPMENT_SLOT_KEY[worn.slot])

    def test_once_it_is_off_the_escape_is_read(self):
        board, worn = self._wearing()
        # DECLARED CONSTRUCTED: the engine's reply to the takeoff (the piece in the pack).
        off = replace(board, equipment=[item for item in board.equipment if item is not worn],
                      inventory=[*board.inventory, replace(worn, slot="p")])
        self.assertEqual(self._choose(off), (READ_KEY + "e", "status-threat:scroll"))

    def test_inside_an_approved_plan_the_plan_decides(self):
        # Answer 11 and C-13: on a floor an approved quest plan runs, the bot takes no
        # piece off (Q25 wears one on purpose) and reads no scroll the game refuses.
        # DECLARED CONSTRUCTED: the board as the floor of approved QUEST_14.
        board, _ = self._wearing()
        board = replace(board, floor_key=(*board.floor_key[:2], 14))
        strategies = load_quest_strategies(Path(__file__).resolve().parents[1] / "strategy" / "quests")
        self.assertIsNotNone(strategies[14].execution_eligible and strategies[14])
        policy = HengbotPolicy(monrace_knowledge=combat.PARALYZER_ESCAPE_KNOWLEDGE,
                               quest_strategies=strategies)
        key = str(policy.choose_key(board))
        self.assertNotEqual(policy.last_reason, TAKEOFF_REASON, key)
        self.assertNotEqual(key, READ_KEY + "e", policy.last_reason)

    def test_a_cursed_piece_reads_no_scroll(self):
        board, _ = self._wearing(cursed=True)
        key, reason = self._choose(board)
        self.assertNotEqual(key, READ_KEY + "e", reason)
        self.assertNotEqual(reason, TAKEOFF_REASON, key)
        # The board's answer without a teleport scroll
        # (RecordedAdjacentParalyzerEscapeTest.test_adjacent_paralyzer_without_scroll_still_walks_away).
        self.assertEqual((key, reason), ("4", "threat:paralyzer-avoid"))


class EmergencyTeleportWithAntiTeleportTest(low_hp._Boards):
    """The recorded Forest 32F board 534 after an unseen bite (``LowHpHealVsTeleportTest``,
    DECLARED CONSTRUCTED there: Healing turned into Cure Serious Wounds, recall removed),
    where ``emergency:teleport`` reads Teleportation through ``_issue_emergency_consumable``.
    DECLARED CONSTRUCTED here: NO_TELE known on a worn piece."""

    def test_the_piece_comes_off_and_no_emergency_read_is_counted(self):
        board = low_hp.LowHpHealVsTeleportTest._kit_board(self, cure_serious=True)
        control = copy.deepcopy(self.policy)
        scroll = next(i for i in board.inventory if i.is_teleport_scroll)
        self.assertEqual((str(control.choose_key(board)), control.last_reason),
                         ("r" + scroll.slot, "emergency:teleport"))
        piece = next(item for item in board.equipment if item.slot != "main_hand" and not item.is_cursed)
        worn = replace(piece, known_flags=frozenset({*piece.known_flags, TR_NO_TELE}))
        board = replace(board, equipment=[worn if item is piece else item for item in board.equipment])
        policy = copy.deepcopy(self.policy)
        key = str(policy.choose_key(board))
        self.assertEqual((key, policy.last_reason), ("t" + EQUIPMENT_SLOT_KEY[worn.slot], TAKEOFF_REASON))
        # No read was issued, so none is watched or counted toward the town return.
        self.assertIsNone(policy._emergency_consumable_issue_watch)


class ImmobileSummonerTeleportLevelTest(unittest.TestCase):
    """The immobile-summoner exit's Teleport Level (``_immobile_summoner_exit_key`` composes
    the read itself): the constructed corridor of tests/test_immobile_summoner_recorded.py
    (``test_constructed_teleport_level_precedes_recall``: ``summoner:teleport-level``).
    DECLARED CONSTRUCTED here: a ring of anti-teleportation worn."""

    @classmethod
    def setUpClass(cls):
        summoner.ImmobileSummonerRecordedTest.setUpClass.__func__(cls)

    _corridor = summoner.ImmobileSummonerRecordedTest._corridor
    _policy = summoner.ImmobileSummonerRecordedTest._policy

    def _decide(self, *, cursed):
        board = self._corridor(inventory=[fixtures.item("t", 70, 10), fixtures.item("r", 70, 11)])
        ring = item("main_ring", 45, 0, is_equipment=True,
                    known_flags=frozenset({TR_NO_TELE}), is_cursed=cursed)
        board = replace(board, equipment=[*board.equipment, ring])
        policy = self._policy(board)
        return str(policy.choose_key(board)), policy.last_reason

    def test_a_removable_ring_comes_off_before_teleport_level(self):
        self.assertEqual(self._decide(cursed=False),
                         ("t" + EQUIPMENT_SLOT_KEY["main_ring"], TAKEOFF_REASON))

    def test_a_cursed_ring_leaves_recall(self):
        # Word of Recall is not refused by anti-teleportation (spells-world.cpp).
        self.assertEqual(self._decide(cursed=True), ("rr", "summoner:recall"))


if __name__ == "__main__":
    unittest.main()
