"""#47: the owner answers of 2026-11-01 17h on the survival rungs.

Memory owner-answers-15-decisions-20261101 (answers 1-5, each the
recommended option); diagnosis LUNA-DIAG-owner15-survival-1101.txt.

Boards: n1-c life-085 (tests/fixtures/death-n1c-085-1101.json.gz, the D57
extraction; Lv18 zombie Magic-Eater, 236 max HP, 迷宮11階; the jelly
『スーパー・グレート・シルバー・ゼリー』 (race 1273, speed +10) touches the
player from (12,4) on boards 1445315-1445328 and from (8,6) on 1445613-1445625).
Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_n1c_deaths_1101_recorded.PostedDeathKey).
DECLARED RECONSTRUCTED: the staff record and the lamp memory as in
test_n1c_deaths_1101_recorded.  DECLARED CONSTRUCTED, as each case states:
the light messages are stripped from the lit boards (so no light recovery
answers first); the unseen cases take the jelly out of the visible list and
name it as the game names a hidden actor, 「何か」 (monster-attack-player.cpp:
298-304, monster-describer.cpp); the arrow control replaces the messages by
mspell-bolt.cpp:21's 「何かが矢を放った。」; the recall-wait case sets
``player.recalling``; the afraid cases set ``player.status.afraid`` (the
controls also the player's speed 130, above the jelly's 120, or an empty
absorbed Magic Missile, ``_magic_eater_wand_charges`` 0 as the power list
reports it); the NO_MELEE cases add that flag to the Labyrinth's
loaded dungeon definition (as test_anti_melee_dungeon_recorded's controls
change only the flag) and, on the dark boards, take the oil flasks and the
spare lantern out of the pack (test_hit_no_action_1101_recorded.constructed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from pathlib import Path

from hengbot import unseen_strike
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.random_quest_reserve import RANDOM_QUEST_TELEPORT_RESERVE, RETURN_TRIGGER
from tests import test_input_executor as executor_pins
from tests.test_dungeon_1031_recorded import READ_PROMPT, RecordedHarness, decide
from tests import test_hit_no_action_1101_recorded as hit
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_esp_threat_rest_recorded import EDIT


JELLY_NAME = "『スーパー・グレート・シルバー・ゼリー』"
LIT_FIRST, LIT_LAST = 1445321, 1445328
ARROW = "何かが矢を放った。"


def lit_boards(*, unseen=False, arrow=False, recalling=False, afraid=False,
               speed=None, missile_charges=None):
    """life-085's lit boards beside the jelly, without the light messages."""
    rows = d57.boards(d57.CASE_085, LIT_FIRST, LIT_LAST, light_messages=False)
    for raw in rows:
        raw["player"]["status"]["afraid"] = afraid
        if unseen:
            raw["visible_monsters"] = [m for m in raw["visible_monsters"]
                                       if m["race_id"] != d57.JELLY]
            raw["messages"] = [m.replace(JELLY_NAME, "何か") for m in raw["messages"]]
        if arrow:
            raw["messages"] = [ARROW]
        if recalling:
            raw["player"]["recalling"] = True
        if speed is not None:
            raw["player"]["speed"] = speed
        if missile_charges is not None:
            raw["_magic_eater_wand_charges"] = missile_charges
    return rows


class UnseenRetreatStrikeRecordedTest(d57.PostedDeathKey):
    """Answer 1 「近接で殴られたら反撃」: melee evidence is struck back."""

    def drive_lit(self, **construct):
        rows = lit_boards(unseen=True, **construct)
        # While recalling, the second hit in a row reads Teleportation
        # (urgent relocation, policy_combat.py); only the first is driven.
        return self.drive(d57.lamp_policy(), rows[:1] if construct.get("recalling") else rows)

    def test_constructed_board_is_an_unseen_melee_hit(self):
        raw = lit_boards(unseen=True)[0]
        self.assertEqual(raw["visible_monsters"], [])
        self.assertIn("何かに触られた。", raw["messages"])
        self.assertLess(raw["player"]["hp"], d57.CASE_085["boards"][0]["player"]["hp"])

    def test_unseen_retreat_strikes_the_melee_attacker(self):
        rows = self.drive_lit()
        # Unfixed: ('7', 'unseen:reverse-choke') on both boards, a walk away.
        for raw, key, reason in rows:
            self.assertEqual((key[0], reason), ("+", unseen_strike.RETREAT_REASON),
                             (raw["turn"], key, reason))

    def test_recall_wait_strikes_the_melee_attacker(self):
        raw, key, reason = self.drive_lit(recalling=True)[0]
        self.assertEqual(raw["turn"], LIT_FIRST)
        # Unfixed: ('7', 'unseen-recall:move').
        self.assertEqual((key[0], reason), ("+", unseen_strike.RECALL_REASON))

    def test_control_arrow_evidence_keeps_the_retreat(self):
        rows = self.drive_lit(arrow=True)
        self.assertEqual({reason for _raw, _key, reason in rows}, {"unseen:reverse-choke"})
        raw, key, reason = self.drive_lit(arrow=True, recalling=True)[0]
        self.assertEqual(reason, "unseen-recall:move")


class AfraidOutpacedRangedRecordedTest(d57.PostedDeathKey):
    """Answer 2 「遠隔の手段があれば撃つ」: afraid beside a faster attacker."""

    def drive_afraid(self, **construct):
        return self.drive(d57.lamp_policy(), lit_boards(afraid=True, **construct))

    def test_afraid_beside_the_faster_jelly_fires(self):
        knowledge = d57.new_policy(d57.CASE_085)._monrace_knowledge
        rows = self.drive_afraid()
        for raw, key, reason in rows:
            board = parse_snapshot(copy.deepcopy(raw), knowledge)
            jelly, = board.visible_monsters
            self.assertEqual((jelly.race_id, jelly.distance), (d57.JELLY, 1))
            self.assertGreater(jelly.speed, board.player.speed)
            # Unfixed: the flee episode, its Speed sustain ('qb',
            # emergency:quaff-speed) then ('2', 'flee'), steps the jelly follows.
            self.assertEqual((key, reason), ("mBp8", MISSILE_REASON), raw["turn"])

    def test_control_faster_player_still_flees(self):
        rows = self.drive_afraid(speed=130)
        self.assertEqual({(key, reason) for _raw, key, reason in rows}, {("2", "flee")})

    def test_control_without_a_ranged_answer_flees(self):
        raw, key, reason = self.drive_afraid(missile_charges=0)[-1]
        self.assertEqual((key, reason), ("2", "flee"))


def no_melee_policy():
    """life-085's policy in a Labyrinth whose definition carries NO_MELEE."""
    policy = d57.lamp_policy()
    dungeon = d57.CASE_085["boards"][0]["floor"]["dungeon_id"]
    info = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")[dungeon]
    policy._dungeon_knowledge[dungeon] = dataclasses.replace(
        info, flags=frozenset(info.flags) | {"NO_MELEE"})
    assert not policy._can_fight_in_dungeon(dungeon)
    return policy


class NoMeleeRangedOrderRecordedTest(d57.PostedDeathKey):
    """Answer 3 「遠隔と取り込んだ力は使う」: NO_MELEE refuses melee only."""

    def test_low_hp_gate_fires_at_the_adjacent_jelly(self):
        rows = [hit.constructed(raw) for raw in
                d57.boards(d57.CASE_085, hit.STRIKE_FROM, hit.STRIKE_AT)]
        raw, key, reason = self.drive(no_melee_policy(), rows)[-1]
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]],
                         [(d57.JELLY, 8, 6)])
        # Unfixed: ('5', 'emergency:wait') beside the jelly.
        self.assertEqual((key, reason), ("mBp8", MISSILE_REASON))

    def test_combat_rung_fires_instead_of_hunting(self):
        rows = self.drive(no_melee_policy(), lit_boards())
        # Unfixed: ('7', 'hunt') on both boards, a walk around the jelly.
        for raw, key, reason in rows:
            self.assertEqual((key, reason), ("mBp8", MISSILE_REASON), raw["turn"])

    def test_control_melee_allowed_the_jelly_is_answered_too(self):
        raw, key, reason = self.drive(d57.lamp_policy(), lit_boards())[-1]
        self.assertEqual(key[-1], "8", (key, reason))


Q14_FIXTURE = Path(__file__).with_name("fixtures") / "owner15-q14-1101.json.gz"
WARG_PROBLEM = 14
TVAL_SCROLL, SV_TELEPORT = 70, 9


class WargProblemTeleportReserveRecordedTest(RecordedHarness):
    """Answer 4 「014 だけ広げる」: the five-scroll reserve covers Q14.

    n1-c life-092 on イークの洞穴5階 with quest 14 TAKEN (1/16 wargs), fifteen
    Scrolls of Teleportation (tests/extract_owner15_q14_1101_fixture.py).  A
    new process with the repository's quest and monster data (as the CLI
    loads them) replays the recorded boards; DECLARED CONSTRUCTED: the last
    board carries four (or, for the control, five) scrolls, as if the
    quest's emergencies had read the rest; the skill knowledge is supplied
    before each decision (test_dungeon_1031_recorded.decide); the executor
    reply is the same board ten turns later.
    """

    @classmethod
    def setUpClass(cls):
        with gzip.open(Q14_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        root = Path(__file__).resolve().parents[1]
        cls.monraces = load_monrace_knowledge(find_monrace_definitions(root, None))
        cls.quests = load_quest_knowledge(find_quest_definitions(root))

    def replay(self, scrolls):
        boards = copy.deepcopy(self.case["boards"])
        for item in boards[-1]["inventory"]:
            if (item["tval"], item["sval"]) == (TVAL_SCROLL, SV_TELEPORT):
                item["count"] = scrolls
        policy = HengbotPolicy(monrace_knowledge=dict(self.monraces), quest_knowledge=self.quests)
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
        for raw in boards[:-1]:
            decide(policy, raw)
        raw = boards[-1]
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._active_kill_quest_id(board), WARG_PROBLEM)
        self.assertEqual(policy._count_teleport_scrolls(board), scrolls)
        return policy, raw, board

    def test_recorded_rows(self):
        self.assertEqual({(row["reason"]) for row in self.case["decisions"]}, {"explore"})
        for raw in self.case["boards"]:
            self.assertEqual((raw["floor"]["dungeon_id"], raw["floor"]["level"]), (2, 5))
            quest, = [q for q in raw["progress"]["quests"] if q["id"] == WARG_PROBLEM]
            self.assertEqual((quest["status"], quest["cur_num"], quest["max_num"]), (1, 1, 16))
            self.assertEqual(sum(item["count"] for item in raw["inventory"]
                                 if (item["tval"], item["sval"]) == (TVAL_SCROLL, SV_TELEPORT)), 15)
            self.assertEqual(raw["visible_monsters"], [])

    def test_below_the_reserve_the_return_reads_recall(self):
        policy, raw, board = self.replay(RANDOM_QUEST_TELEPORT_RESERVE - 1)
        key = decide(policy, copy.deepcopy(raw))
        # Unfixed: the lock held and the bot explored on ('4', 'explore').
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertEqual((policy.last_reason, policy._last_return_trigger),
                         ("return:recall", RETURN_TRIGGER))
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(READ_PROMPT)],
                                   self.later(raw)), ["r", recall.slot])

    def test_control_at_the_reserve_the_floor_stays_locked(self):
        policy, raw, board = self.replay(RANDOM_QUEST_TELEPORT_RESERVE)
        decide(policy, copy.deepcopy(raw))
        self.assertTrue(policy._quest_floor_exit_locked(board))
        self.assertNotEqual(policy.last_reason, "return:recall")


if __name__ == "__main__":
    unittest.main()
