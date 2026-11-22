"""n1-b life-415, Angband 76F, RANDOM quest 42, 2026-11-22 17:08: killed by the target 『タラスク』.

Recorded: tests/fixtures/n1b-415-tarrasque-1122.json.xz
(tests/extract_n1b_415_tarrasque_1122_fixture.py): the boards of decisions 8017-8037.  The Lv36
Magic-Eater (HP 773, the absorbed *Destruction* with 7 charges) descended to the quest's floor;
the quest list showed quest 42 = 76F with r_idx 838 (『タラスク』, Lv84, speed +20, NO_SLEEP,
1_IN_2 BR_FIRE/BR_COLD/BR_DISE) before the descent.  On the arrival's up staircase (24,102) it
quaffed Speed (8018), stepped off toward a sleeping T1 for *Destruction* (8019, 8020), Detect
Evil showed the target 20 cells off (8021), Word of Recall was read (8023, the 11-13 rule), and it
waited 13 turns (return:wait-recall) while the target closed from 20 to 6; *Destruction* was
withheld for it (destruction_use spares the quest target).  Two breaths (about 1,040) killed it
on 8037.

Pinned here:

 A (the defect, owner 2026-11-13 「T1 の標的と分かったら追わずに帰還を読み、クエストは失敗にする。
   標的が近づく前に離れる。」): the arrival judges the target from the quest list's race
   (hunt_target ``_judge_quest_race``), gives the floor up at once, and leaves by the up staircase
   underfoot before any approach steps off it (threat_tiers ``given_up_stairs``).
 B (owner 2026-11-22 「帰還すると決めたら標的を破壊に巻き込んで良い」): once the Recall away from
   the target is decided, *Destruction* is no longer withheld for the target in its radius
   (destruction_use ``_target_race``); before that decision the target is still spared.

Every decision is the public ``choose_key`` of a fresh fully loaded policy fed the recorded
boards in order (tests/support/recorded ``_policy``).  DECLARED CONSTRUCTED: the absorbed staff
list (the death dump's rows: テレポート 15, 邪悪存在感知 25, スピード 11, *破壊* 7; the live process
had read it, the state tail does not carry it); the live keys are posted, not the replayed ones
(the boards are the game's), and each board after a recorded ``m`` cast carries the cast's
completed operation (the CLI's ``_completed_operation_owner``); after the recorded Word of Recall
the boards carry ``recalling`` as recorded.  A replayed use the game did not see shows no flash
on the next board, which reads as a failed use (destruction_use ``_falls_back``).  The constructed
boards are named where they are built.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, hunt_target, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy, skill
from tests.test_me_device_attacks import power_list, row

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-415-tarrasque-1122.json.xz"
TARRASQUE = 838
QUEST = 42
ARRIVAL = 2124039                      # decision 8018, on the up staircase (24,102)
FIRST_SHOWN = 2124052                  # decision 8021's board: Detect Evil shows it, 20 off
IN_REACH = 2124076                     # decision 8029's board: the target 12 cells off
DEATH = 2124107                        # decision 8037
BEGGAR = 10                            # 醜い浮浪者 (Lv0), a beatable stand-in
STAFF = (row("テレポート", 3, current=15, count=15), row("邪悪存在感知", 1, current=25, count=25),
         row("スピード", 5, current=11, count=11), row("*破壊*", 10, current=7, count=7))
DESTRUCTION_REASONS = ("emergency:destruction:absorbed-power",
                       "emergency:destruction:deep-teleport:absorbed-power")


class N1b415Tarrasque1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.rows, cls.decisions = payload["rows"], payload["decisions"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.live = {row["turn"]: row for row in cls.decisions}

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def row(self, turn):
        """The first board of ``turn`` (the arrival turn has two)."""
        return copy.deepcopy(next(raw for raw in self.rows if raw["turn"] == turn))

    def policy(self, first):
        policy = _policy(self.root, self.races)
        policy.prime(parse_snapshot(copy.deepcopy(first), self.races))
        skill(policy, first)
        listed = dict(copy.deepcopy(first), turn=first["turn"] - 1,
                      _magic_eater_power_list=power_list("staff", *STAFF))
        observe_lists(policy, parse_snapshot(listed, self.races))
        return policy

    def replay(self):
        """(policy, {turn: (key, reason)}) over the 76F boards, the live keys posted; a turn's
        last board is its decision (the arrival turn's first board primes the policy)."""
        boards = [raw for raw in self.rows if raw["floor"]["level"] == 76]
        policy = self.policy(boards[0])
        decided, previous, recalling = {}, None, False
        for index, raw in enumerate(boards):
            if index + 1 < len(boards) and boards[index + 1]["turn"] == raw["turn"]:
                continue
            raw = copy.deepcopy(raw)
            if previous is not None and previous["key"].startswith("m"):
                raw["_completed_operation_owner"] = previous["reason"]  # DECLARED (docstring)
            if recalling:
                raw["player"]["recalling"] = True
            board = parse_snapshot(raw, self.races)
            key = policy.choose_key(board)
            decided[raw["turn"]] = ("" if key is None else str(key), policy.last_reason)
            live = self.live[raw["turn"]]
            policy.confirm_key_posted(live["key"])
            previous = live
            recalling = recalling or live["key"] == "rh"
        return policy, decided

    def target(self, board):
        return next(m for m in board.detected_monsters if m.race_id == TARRASQUE)

    # ------------------------------------------------------------------ the recorded scene

    def test_the_recorded_scene(self):
        live = {row["sequence"]: (row["key"], row["reason"]) for row in self.decisions}
        self.assertEqual(live[8018], ("mAw", "quest:quaff-speed:absorbed-power"))
        self.assertEqual(live[8019], ("9", "sensed-t1:approach-destruction"))
        self.assertEqual(live[8020], ("mA3", "emergency:destruction:absorbed-power"))
        self.assertEqual(live[8023], ("rh", "sensed-t1:recall"))
        self.assertEqual({live[sequence] for sequence in range(8025, 8037)},
                         {("5", "return:wait-recall")})
        self.assertEqual(live[8037], ("8", "emergency:seek-upstairs"))
        arrival = self.row(ARRIVAL)
        self.assertEqual((arrival["floor"]["level"], arrival["floor"]["quest_id"]), (76, QUEST))
        quest = next(q for q in arrival["progress"]["quests"] if q["id"] == QUEST)
        self.assertEqual((quest["r_idx"], quest["level"]), (TARRASQUE, 76))
        board = parse_snapshot(arrival, self.races)
        self.assertTrue(board.grid_at(board.player.position).has_up_stairs)
        for turn in (ARRIVAL, 2124042, 2124045, 2124049):
            raw = self.row(turn)
            self.assertNotIn(TARRASQUE, [m["race_id"] for m in
                                          (*raw["visible_monsters"], *raw["detected_monsters"])])
        shown = parse_snapshot(self.row(FIRST_SHOWN), self.races)
        self.assertEqual(game_distance(shown.player.position, self.target(shown).position), 20)
        # On IN_REACH the target is inside the sure radius and the only hostile there.
        reach = parse_snapshot(self.row(IN_REACH), self.races)
        self.assertEqual([m.race_id for m in (*reach.visible_monsters, *reach.detected_monsters)
                          if destruction_use.in_sure_radius(reach, m)], [TARRASQUE])
        self.assertTrue(reach.player.recalling)

    # ------------------------------------------------------------------ A: the arrival

    def test_the_arrival_gives_the_floor_up_and_takes_the_stair_underfoot(self):
        """Live 8018-8019: Speed, then a step off the up staircase toward a sleeping T1; now '<'
        on the arrival board, the floor given up from the quest list's race."""
        policy, decided = self.replay()
        self.assertEqual(decided[ARRIVAL], ("<", "sensed-t1:stairs"))
        board = parse_snapshot(self.row(ARRIVAL), self.races)
        self.assertEqual(policy._unviable_quest_floor, board.floor_key)

    def test_the_quest_list_race_is_judged_on_arrival(self):
        raw = self.row(ARRIVAL)
        policy = self.policy(raw)
        board = parse_snapshot(raw, self.races)
        key = policy.choose_key(board)
        visit = hunt_target._visit(policy, board)
        self.assertTrue(visit.quest_race_judged)
        self.assertTrue(visit.quest_unbeatable)
        self.assertTrue(hunt_target.quest_target_unbeatable(policy, board))
        self.assertFalse(policy._quest_floor_exit_locked(board))
        self.assertEqual((key, policy.last_reason), ("<", "sensed-t1:stairs"))

    def test_a_beatable_quest_race_does_not_give_the_floor_up(self):
        """CONSTRUCTED: the quest list's race made a 醜い浮浪者 (Lv0): no verdict gives the floor
        up, its exit lock holds and no stair is taken."""
        raw = self.row(ARRIVAL)
        next(q for q in raw["progress"]["quests"] if q["id"] == QUEST)["r_idx"] = BEGGAR
        policy = self.policy(raw)
        board = parse_snapshot(raw, self.races)
        key = policy.choose_key(board)
        self.assertTrue(hunt_target._visit(policy, board).quest_race_judged)
        self.assertFalse(hunt_target.quest_target_unbeatable(policy, board))
        self.assertIsNone(policy._unviable_quest_floor)
        self.assertTrue(policy._quest_floor_exit_locked(board))
        self.assertNotEqual(key, "<")

    def test_a_sleeping_t1_in_reach_does_not_keep_the_player_on_the_given_up_floor(self):
        """CONSTRUCTED: the arrival board with the sleeping スカイ・ドレイク (race 793, the T1 the
        approach went to, 14 cells off) moved to (22,113), 12 off: the use could be cast from the
        staircase, and the emergency layer's sensed T1 *Destruction* declines for the staircase
        underfoot (threat_tiers ``sensed_t1_destruction_key``), as it does where no approach
        owns the board."""
        raw = self.row(ARRIVAL)
        drake = next(m for m in raw["detected_monsters"] if m["race_id"] == 793)
        drake["x"] = 113
        policy = self.policy(raw)
        board = parse_snapshot(raw, self.races)
        moved = next(m for m in board.detected_monsters if m.race_id == 793)
        self.assertEqual(game_distance(board.player.position, moved.position), 12)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("<", "sensed-t1:stairs"))

    # ------------------------------------------------------------------ B: after the decision

    def test_destruction_is_used_with_the_target_in_reach_after_the_recall_decision(self):
        """Live 8029-8036: return:wait-recall with the target 12 to 6 cells off; now the absorbed
        *Destruction* on the first board it is in the sure radius, and on the death board."""
        _, decided = self.replay()
        self.assertEqual(decided[IN_REACH], ("mA3", DESTRUCTION_REASONS[0]))
        self.assertEqual(decided[DEATH], ("mA3", DESTRUCTION_REASONS[1]))
        reach = [turn for turn in decided if IN_REACH <= turn <= DEATH]
        # Between the uses only the fallback of a use the game did not see (DECLARED).
        for turn in reach:
            self.assertIn(decided[turn][1], (*DESTRUCTION_REASONS, "return:wait-recall"), turn)

    def test_the_target_is_spared_only_until_the_recall_decision(self):
        """The same board (IN_REACH) without and with the decision: before it the quest's target
        is spared (the 2026-11-04 rule: the use only heals and moves a QUESTOR), after it the use
        takes it."""
        raw = self.row(IN_REACH)
        policy = self.policy(raw)  # no board decided: no verdict, no latch
        board = parse_snapshot(raw, self.races)
        target = self.target(board)
        self.assertIsNone(policy._unviable_quest_floor)
        self.assertFalse(destruction_use.target_given_up(policy, board))
        self.assertTrue(destruction_use.spares(policy, board, target))
        self.assertEqual(destruction_use.quest_target_race(policy, board), TARRASQUE)
        self.assertFalse(destruction_use.usable(policy, board, leaving=[target]))
        policy._unviable_quest_floor = board.floor_key  # the Recall away from it decided
        self.assertTrue(destruction_use.target_given_up(policy, board))
        self.assertFalse(destruction_use.spares(policy, board, target))
        self.assertIsNone(destruction_use.quest_target_race(policy, board))
        self.assertTrue(destruction_use.usable(policy, board, leaving=[target]))
        self.assertIn(target, threat_tiers._sensed_strong(policy, board)[1])


if __name__ == "__main__":
    unittest.main()
