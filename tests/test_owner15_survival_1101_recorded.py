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
import tempfile
import unittest
from pathlib import Path

from hengbot import threat_tiers, unseen_strike
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.equipment_optimizer import equipment_identity
from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.random_quest_reserve import RANDOM_QUEST_TELEPORT_RESERVE, RETURN_TRIGGER
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_depart2_1101_recorded as depart2
from tests.support import recorded as executor_pins
from tests.test_dungeon_1031_recorded import READ_PROMPT, decide
from tests import test_dungeon_1031_recorded as _test_dungeon_1031_recorded
from tests import test_hit_no_action_1101_recorded as hit
from tests import test_n1c_deaths_1101_recorded as d57
from tests.support.recorded import EDIT


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
        # Threat tiers step 6 (answer 6, design 3.2): afraid with no ranged answer the jelly is T1
        # and is left; it is faster (120 against 110), so the leave does not walk: the flee rung
        # reads Teleportation (before step 6 it walked away, '2' flee).
        raw, key, reason = self.drive_afraid(missile_charges=0)[-1]
        self.assertEqual((key, reason), ("rf", "flee:scroll"))
        policy = d57.lamp_policy()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        hostiles = policy._strategic_hostiles(board)
        self.assertEqual(threat_tiers.assess(policy, board, hostiles).tier, threat_tiers.T1)
        self.assertFalse(threat_tiers.walk_leaves(policy, board, hostiles))


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


class WargProblemTeleportReserveRecordedTest(_test_dungeon_1031_recorded.RecordedHarness):
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


class ConquestDiveOverExtensionRecordedTest(nav.RecordedDrive):
    """Answer 5 「緊急の逃げも数える」: a conquest target's dive counts them.

    n1-c life-083's recorded Labyrinth dive (tests/fixtures/
    d57-n1c-083-1101.json.gz: emergency teleports, no pickup, Word of Recall
    home at turn 1187204), driven as test_d57_nav_depth_1101_recorded drives
    it.  DECLARED CONSTRUCTED: Angband's recall is unlocked on every board;
    the Labyrinth is the conquest target (the conquest selection,
    ``_conquest_target``, names it; no over-extension alternate); the streak
    starts at 1 with the recorded row's last over-extended depth.
    """

    def drive(self, *, conquest):
        boards = copy.deepcopy(nav.CASE_083["boards"])
        for raw in boards:
            raw["progress"]["angband_recall_unlocked"] = True
        policy = nav.new_policy(nav.CASE_083, boards)
        start = nav.CASE_083["decisions"][0]["over_extension"]
        if conquest:
            policy._conquest_target = lambda _snapshot: nav.LABYRINTH
            policy._target_dungeon_id = nav.LABYRINTH
            policy._target_dungeon_reason = "conquest"
        else:
            policy._alternate_dungeon = start["alternate_dungeon_id"]
            policy._alternate_dungeon_reason = "over_extended_dives"
            policy._target_dungeon_id = start["target_dungeon_id"]
        policy._target_empty_dives = 1
        policy._last_overextended_depth = start["last_overextended_depth"]
        rows = self.drive_boards(nav.CASE_083, boards, policy)
        self.assertEqual(rows[-1][0]["turn"], nav.ARRIVAL_TURN)
        self.assertTrue(rows[-1][0]["floor"]["in_town"])
        reasons = [reason for _raw, _key, reason in rows]
        self.assertGreaterEqual(reasons.count("emergency:teleport"), 2, reasons)
        self.assertNotIn("esp-threat:leave-recall", reasons)
        return policy

    def test_conquest_dive_advances_the_streak(self):
        policy = self.drive(conquest=True)
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason),
                         (nav.LABYRINTH, "conquest"))
        # Unfixed: 1, the guardian-bounce-only judgement held the streak.
        self.assertEqual(policy._target_empty_dives, 2)

    def test_control_alternate_dive_advances_the_streak(self):
        policy = self.drive(conquest=False)
        self.assertEqual((policy._target_empty_dives, policy._alternate_dungeon),
                         (2, nav.LABYRINTH))


CONFIRMED_LOADOUT = Path(__file__).with_name("fixtures") / "owner15-confirmed-loadout-1101.json"


class ClosedVisitDepartureRecordedTest(depart2.Depart2RecordedBase):
    """D59 follow-up: the 10-03 rule 「失敗した任意の装備の変更は今の確定した
    装備で出発」 also covers an equipment transaction the visit closed.

    The 13:54 stop board of n1-c life-092 (decision 3061,
    town:blocked:departure-unsatisfiable, failed ["equipment_departure_ready"],
    equipment result_source "town-visit-transaction-closed": the 3044
    deposit-missing closure).  dc3ff4126 keeps the recorded deposit from
    closing, so DECLARED RECONSTRUCTED: the closure decision 3044 wrote (its
    visit, its reason, the trident's identity), the failed item of the
    capture's policy-state, the visit ledger of decision 3061
    (departure_block.town_ledger: Home visited three times, two unsatisfied
    passes), and the process's confirmed loadout and optimizer input key
    (life-092 jsonlog/confirmed-loadout.json, frozen by
    tests/extract_owner15_depart_1101_fixture.py; the policy reads it from a
    temporary directory).

    The check reads the departure gate every departure producer reads
    (``_town_departure_ready``): on this board the current staff sequence
    owns ``choose_key`` (me-staff:travel-morivant, the Tower trip that
    replaced the recorded build's step-off), so the decision does not reach
    the departure.
    """

    case_name = "trident"

    def closed_visit(self, *, ledger=True):
        policy, raw = self.boundary()
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        record = json.loads(CONFIRMED_LOADOUT.read_text(encoding="utf-8"))["record"]
        (directory / "confirmed-loadout.json").write_text(json.dumps(record), encoding="utf-8")
        policy._confirmed_loadout_path = directory / "confirmed-loadout.json"
        policy._equipment_optimizer_input_key = record["optimizer_input_key"]
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.prime(board)
        plain = next(item for item in self.case["boards"]["plain"]["inventory"]
                     if item["name"].startswith(depart2.TRIDENT))
        policy._equipment_transaction_visit_closure = {
            "epoch": policy._town_visit_epoch, "reason": "deposit-missing",
            "target_loadout_id": None,
            "item_identity": equipment_identity(_parse_items([plain], protocol=3)[0]),
            "turn": self.case["boards"]["home"]["turn"]}
        policy._equipment_transaction_failed_items = set(
            self.case["state"]["_equipment_transaction_failed_items"])
        if ledger:
            recorded = self.decision(3061)["departure_block"]["town_ledger"]
            for name in ("store_visits", "unsatisfied_passes"):
                for store, count in recorded[name].items():
                    getattr(policy._town_visit_ledger, name)[int(store)] = count
        return policy, board

    def test_recorded_closure(self):
        row = self.decision(3061)
        self.assertEqual((row["reason"], row["departure_block"]["failed"]),
                         ("town:blocked:departure-unsatisfiable", ["equipment_departure_ready"]))
        self.assertEqual(row["equipment"]["result_source"], "town-visit-transaction-closed")
        self.assertEqual(self.decision(3044)["reason"], "equipment-transaction:deposit-missing")
        self.assertEqual(row["departure_block"]["town_ledger"]["unsatisfied_passes"],
                         {str(STORE_HOME): 2})

    def test_closed_visit_departs_on_the_current_loadout(self):
        policy, board = self.closed_visit()
        codes = []
        # Unfixed: False, ['preparation-unavailable'] (no preparation).
        self.assertTrue(policy._equipment_departure_ready(board, commit=False, codes=codes), codes)
        self.assertTrue(policy._town_departure_ready(board))
        self.assertEqual(policy.equipment_optimization_state(board)["blockers"],
                         ["equipment-transaction-failed"])

    def test_control_a_live_home_route_keeps_the_gate(self):
        # Without the visit's Home passes the work is not proven unexecutable
        # this visit (_equipment_failure_unexecutable_this_visit).
        policy, board = self.closed_visit(ledger=False)
        self.assertFalse(policy._equipment_departure_ready(board, commit=False))


if __name__ == "__main__":
    unittest.main()
