"""Owner 2026-11-05: Angband stays shut until Q2 is resolved (shaft-hold-1105).

「階段の行き先を地形で見分け、坑道なら2階下として判定します。クエストの階をまたぐ
坑道は使わず、ほかの階段を探します」.  The viewing Magic-Eater n1-b life-313 (Lv14,
Q2 not taken) stood on the down shaft [51,56] of 鉄獄4階 (terrain 14) at turn 704848,
its posted '>' at 12:45:58 was ``descend``, and turn 704849 was 鉄獄6階, random
quest 49, which it failed.  The hold asked for the current floor + 1.

Pinned through the public chooser and the production executor port on the
recorded boards: with Q2 open the bot walks past the shaft to the ordinary stair
[31,78]; with Q2 resolved the same boards descend as recorded.

Fixture: tests/fixtures/shaft-hold-n1b-313-1105.json.gz
(tests/extract_shaft_hold_1105_fixture.py).
DECLARED RECONSTRUCTED: the decision log of 12:45 has rotated away; the recorded
key and reason come from bot-posted-characters.jsonl.  The absorbed-power memory
of the floor visit is its new-floor casts (posted at 12:45:14), seeded at the
shaft.  The absorbed staffs are the life's later policy state.  The quest
knowledge is the fixture's RANDOM rows of lib/edit/quests.
DECLARED CONSTRUCTED: the after-Q2 case adds the Q2 row to every board, the
only-shaft case turns the other stairs of the recorded board into floor, and the
gate cases arrange a landing-floor refusal or a kill quest row on the 5F between.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_powers, random_quest_hold
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import DOWN_STAIRS_KEY, QUEST_STATUS_TAKEN, QUEST_STATUS_UNTAKEN
from hengbot.quest_knowledge import QUEST_TYPE_KILL_LEVEL, QuestInfo
from hengbot.stair_destination import down_destination
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_rq_after_q2_recorded import Q2_FINISHED, RandomQuestAfterQ2RecordedTest


FIXTURE = Path(__file__).with_name("fixtures") / "shaft-hold-n1b-313-1105.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SHAFT_TURN = 704848
SHAFT = Position(51, 56)
ANGBAND_4F = (1, 4, 0)
ORDINARY_STAIR = Position(31, 78)
NEW_FLOOR_CASTS = ("mAp", "mAm", "mAj")  # detect-evil, detect-traps, map-area
FLOOR_TERRAIN = 1
UP_STAIR_TERRAIN = 6
DOWN_STAIR_TERRAIN = 7
QUEST_ON_5F = 90  # constructed: no quest file holds this id


def power_memory(first_turn):
    uses = []
    for key in NEW_FLOOR_CASTS:
        ident = (me_powers.kind_of(key[1]), me_powers.decode_letter(key[2]))
        uses.append(me_powers.Use(ident, ident, "new-floor", SHAFT, first_turn - 1, "seed", key))
    return me_powers.FloorMemory(ANGBAND_4F, first_turn - 400, uses)


_undo_past_junk = None


def setUpModule():
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


def turned_to_floor(raw, terrains):
    """The board with these stairs' palette rows drawn as the board's own floor."""
    palette = raw["grid_map"]["palette"]
    floor = next(row for row in palette if row[0] == FLOOR_TERRAIN)
    raw["grid_map"]["palette"] = [
        list(floor) if row[0] in terrains else row for row in palette]
    return raw


class ShaftHoldRecordedTest(d57.PostedDeathKey):
    send = RandomQuestAfterQ2RecordedTest.send

    def boards(self, *, q2_done=False):
        boards = [copy.deepcopy(raw) for raw in CASE["shaft"] if raw["turn"] <= SHAFT_TURN]
        if q2_done:
            for raw in boards:
                raw["progress"]["quests"].append(dict(Q2_FINISHED))
        return boards

    def new_policy(self, boards):
        policy = d57.new_policy(dict(CASE, boards=boards))
        policy._quest_knowledge.update(
            {row["id"]: QuestInfo(**row) for row in CASE["random_quests"]})
        setattr(policy, me_powers.MEMORY, power_memory(boards[0]["turn"]))
        return policy

    def drive(self, boards, arrange=None):
        """Decide every board; the last key goes through the executor port."""
        policy = self.new_policy(boards)
        if arrange is not None:
            arrange(policy)
        rows = []
        for raw in boards:
            key = loops.decide(policy, raw)
            rows.append((raw["turn"], key, policy.last_reason))
            if raw is not boards[-1]:
                policy.confirm_key_posted(key)
        following = dict(copy.deepcopy(boards[-1]), turn=SHAFT_TURN + 1)
        self.send(policy, boards[-1], rows[-1][1], following)
        return rows

    def test_recorded_shaft_terrain_and_destination(self):
        raw = next(row for row in CASE["shaft"] if row["turn"] == SHAFT_TURN)
        board = parse_snapshot(copy.deepcopy(raw))
        grid = board.grid_at(SHAFT)
        self.assertEqual((grid.terrain_id, grid.has_down_stairs), (14, True))
        self.assertEqual(down_destination(4, grid), 6)
        self.assertEqual(down_destination(4, board.grid_at(ORDINARY_STAIR)), 5)
        arrival = next(row for row in CASE["shaft"] if row["turn"] == SHAFT_TURN + 1)
        self.assertEqual(arrival["floor"]["level"], 6)

    def test_before_q2_the_shaft_is_walked_past(self):
        rows = self.drive(self.boards())
        self.assertNotIn(DOWN_STAIRS_KEY, [key for _turn, key, _reason in rows], rows)
        self.assertEqual(rows[-1][2], "approach-descent", rows)

    def test_after_q2_the_same_boards_descend(self):
        rows = self.drive(self.boards(q2_done=True))
        self.assertEqual(rows[-1], (SHAFT_TURN, DOWN_STAIRS_KEY, "descend"), rows)

    def test_only_the_held_shaft_known_explores_for_another_stair(self):
        # Owner: 「ほかの階段を探します」.  With up stairs known or not, it explores.
        for terrains in ({DOWN_STAIR_TERRAIN}, {DOWN_STAIR_TERRAIN, UP_STAIR_TERRAIN}):
            boards = [turned_to_floor(raw, terrains) for raw in self.boards()]
            rows = self.drive(boards)
            self.assertNotIn(DOWN_STAIRS_KEY, [key for _turn, key, _reason in rows], rows)
            self.assertEqual(rows[-1][2], "explore", rows)

    def after_q2_on_the_shaft(self, arrange, *, quest=None):
        """The last row of the after-Q2 walk, ``arrange`` applied to the policy."""
        boards = self.boards(q2_done=True)
        if quest is not None:
            for raw in boards:
                raw["progress"]["quests"].append(dict(quest))
        return self.drive(boards, arrange)[-1]

    def test_every_gate_of_the_descent_reads_the_landing_floor(self):
        def missing_on_the_landing(policy):
            real = policy._missing_required_abilities
            policy._missing_required_abilities = lambda snapshot, depth: (
                frozenset({"resist_conf"}) if depth == 6 else real(snapshot, depth))

        def guardian_on_the_landing(policy):
            policy._dungeon_knowledge[1] = DungeonInfo(
                id=1, name="Angband", min_depth=1, max_depth=6, min_player_level=0, guardian_id=1)
            policy._guardian_fight_viable = lambda snapshot, info: False

        def supplies_short_for_the_landing(policy):
            policy._depth_supply_shortage = lambda snapshot, depth: depth == 6

        for arrange in (missing_on_the_landing, guardian_on_the_landing,
                        supplies_short_for_the_landing):
            with self.subTest(arrange.__name__):
                row = self.after_q2_on_the_shaft(arrange)
                self.assertNotEqual(row[1], DOWN_STAIRS_KEY, row)
                self.assertEqual(row[2], "approach-descent", row)

    def kill_quest_on_5f(self, policy):
        info = next(iter(CASE["random_quests"]))
        policy._quest_knowledge[QUEST_ON_5F] = QuestInfo(**dict(
            info, id=QUEST_ON_5F, type=QUEST_TYPE_KILL_LEVEL, level=5, dungeon=1))

    def test_a_shaft_does_not_overshoot_a_kill_quest_floor(self):
        taken = dict(id=QUEST_ON_5F, status=QUEST_STATUS_TAKEN, type=QUEST_TYPE_KILL_LEVEL,
                     level=5, fixed=True, name="q", cur_num=0, max_num=1, r_idx=1)
        row = self.after_q2_on_the_shaft(
            self.kill_quest_on_5f, quest=taken)
        self.assertNotEqual(row[1], DOWN_STAIRS_KEY, row)

        def regenerating(policy):
            self.kill_quest_on_5f(policy)
            policy._quest_regen_id = QUEST_ON_5F
            policy._quest_regen_phase = "descend"

        row = self.after_q2_on_the_shaft(regenerating, quest=taken)
        self.assertNotEqual(row[1], DOWN_STAIRS_KEY, row)

    def test_a_shaft_does_not_overshoot_an_untaken_kill_quest_floor(self):
        # The fixed quest row of the allowlist that steers the dive (Q14's shape).
        untaken = dict(id=14, status=QUEST_STATUS_UNTAKEN, type=QUEST_TYPE_KILL_LEVEL,
                       level=5, fixed=True, name="q", cur_num=0, max_num=1, r_idx=1)
        info = next(iter(CASE["random_quests"]))

        def steering(policy):
            policy._quest_knowledge[14] = QuestInfo(**dict(
                info, id=14, type=QUEST_TYPE_KILL_LEVEL, level=5, dungeon=1))

        boards = self.boards(q2_done=True)
        for raw in boards:
            raw["progress"]["quests"] = [
                row for row in raw["progress"]["quests"] if row["id"] != 14] + [dict(untaken)]
        row = self.drive(boards, steering)[-1]
        self.assertNotEqual(row[1], DOWN_STAIRS_KEY, row)

    def test_a_shaft_cannot_pass_over_a_held_floor(self):
        # Below the first random quest floor the next one is still held.
        boards = self.boards()
        policy = self.new_policy(boards)
        board = parse_snapshot(copy.deepcopy(boards[-1]))
        self.assertTrue(random_quest_hold.crossing_held(policy, board, 1, 5, 7))
        self.assertTrue(random_quest_hold.crossing_held(policy, board, 1, 7, 12))
        self.assertFalse(random_quest_hold.crossing_held(policy, board, 1, 3, 5))


if __name__ == "__main__":
    import unittest

    unittest.main()
