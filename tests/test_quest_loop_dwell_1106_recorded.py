"""A retreat's vetoes must not wall a random quest's hunt and search into one side of the floor.

Recorded: n1-b life-317, Angband 50F, RANDOM quest 40 (暗黒城の魔術師『アンサロム』, race 1005), build
bot-4b394f178, stopped 2026-11-05 22:03 with stall:floor-dwell:quest-search:loop.  Five retreats
from a half-giant (turns 2344826-2344864) left the column (3..7, 93) of vetoes across a five-wide
hall.  The half-giant later came to the player and changed shape, the vetoes stayed, and for 81,000
game turns the bot walked 203 round trips over 34 cells of the 259 on its side.  83 detect-all
casts showed the target past the column.  The restart emptied the vetoes, and the player stood
beside the target 486 game turns later.

Owner 2026-11-04 on vetoes that hold the player: 「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で
動けなくなったら帰還。」; 2026-11-05 on the search: 「ランダムクエストで標的が見つからないときはフロアを周回
して探す」 with no cap on laps.  The floor's one Teleportation is read (retreat_enclosure).  Walled off
again, owner 2026-11-06: dig, disarm, strike a weak enemy, then Teleportation again or Recall at or
below the reserve (tests/test_walled_off_again_1106_recorded).

The stall itself is named by the runner's dwell timer (linux_soak.py, outside this repository, on
the floor and the character level alone), so it has no pin here.

Fixture: tests/extract_quest_loop_dwell_1106_fixture.py: the boards from the arrival to the
give-up, the stop's last board, and the first recorded board past the column.

DECLARED CONSTRUCTED: the half-giant shown by a detection on the stop board where the search reads
(``shown``; the recorded stop board lifts the column, tests/test_veto_life_1106_recorded); on the stop board, the ground visited, its frontiers written off and the
target's cell given up (the 14,000 boards between did it, and a replay of them takes minutes); the later turn of a
repeated board; the Teleportation's landing (the board past the column was reached on foot after the restart).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from test_floor_dwell_seen_floor_recorded import EDIT, _Replay

from hengbot import hunt_target, quest_target_search, retreat_enclosure
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_LIMIT
from tests import test_loops_1104_recorded as loops

FIXTURE = Path(__file__).parent / "fixtures" / "quest-loop-dwell-1106.json.xz"
COLUMN = {Position(y, 93) for y in range(3, 8)}
READ_PROMPT = "どの巻物を読みますか? "
# The walk keys and the (dy, dx) of their step.
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
VETOES_DONE_TURN = 2344864
# The half-giant the column was set for (index 76, race 1301), as the fixture's last detection
# showed it (2345271).
HALF_GIANT = {"asleep": True, "confused": False, "detected": True, "esp": False, "fast": False,
              "fearful": False, "friendly": False, "health": "unhurt", "index": 76,
              "invulnerable": False, "level": None, "name": "ハーフジャイアント", "pet": False,
              "race_id": 1301, "slow": False, "stunned": False, "x": 85, "y": 4}


def shown(raw):
    """DECLARED: a detection shows the half-giant on this board, so its column stands
    (retreat_veto_life lifts it otherwise, 84,000 game turns after it was last shown)."""
    raw["detected_monsters"] = [*raw.get("detected_monsters", []), dict(HALF_GIANT)]


def without_stone_to_mud(raw):
    """DECLARED: the recorded kit without its two Stone to Mud wands (slot h)."""
    raw["inventory"] = [item for item in raw["inventory"] if "岩石溶解" not in item["name"]]


class WalledOffBoards(loops.ItemCommandBoards):
    """The fixture's boards through choose_key (no tests of its own)."""

    # The target's T1 verdict (hunt_target._judge_quest_target, owner 2026-11-13 「階を諦めて帰還
    # する」) is left out: アンサロム reads T1 from contact against this Lv34 warrior (HP 486, its
    # no-supply damage 1213 over 29 turns), so the floor is given up at its first detection
    # (``test_the_t1_target_gives_the_floor_up_at_its_first_detection``).  These pins are the
    # vetoes' walls, not the target (DECLARED CONSTRUCTED).
    judge_target = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.boards = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        super().setUp()
        if not self.judge_target:
            verdict = mock.patch.object(hunt_target, "_judge_quest_target", lambda *_: None)
            verdict.start()
            self.addCleanup(verdict.stop)

    def replay(self, until=None):
        """The recorded entry through choose_key, as far as ``until`` answers True."""
        replay = _Replay(self, self.monrace)
        for line in self.boards["entry"]:
            try:
                board, key, reason = replay.decide(line)
            except IndexError:  # the same board again: no new decision
                continue
            if until is not None and until(board, reason):
                return replay, line, key, reason
        return replay, line, key, reason

    def stop_raw(self, *, later=0, edit=None):
        """The stop's last board, ``later`` game turns on, changed by ``edit`` (DECLARED)."""
        raw = json.loads(self.boards["stop"])
        raw["turn"] += later
        if edit is not None:
            edit(raw)
        return raw

    def at_the_stop(self, replay, *, later=0, edit=None):
        """The stop's last board as the loop met it (DECLARED, the module docstring)."""
        line = json.dumps(self.stop_raw(later=later, edit=edit), ensure_ascii=False)
        board = replay.board(line)
        policy = replay.policy
        ground = [*board.grids, *(Position(*cell) for cell in policy._floor_t)]
        policy._probed_frontiers.update(ground)
        policy._visit_counts.update(ground)
        policy._blocked_doors.update(policy._door_t)
        policy._blocked_rubble.update(policy._rubble_t)
        here = board.player.position
        policy._search_counts[(here.y, here.x)] = SEARCH_LIMIT
        getattr(policy, hunt_target.MEMORY).position = None
        return replay.decide(line)


class TargetVerdict(WalledOffBoards):
    judge_target = True

    def test_the_t1_target_gives_the_floor_up_at_its_first_detection(self):
        """Owner 2026-11-13: the T1 target is not hunted; the board that first shows it (turn
        2344271, detected 40 cells off) gives the floor up and Word of Recall is read on the
        next (2344275), long before the column (turns 2344826-2344864)."""
        replay, line, key, reason = self.replay(lambda _board, reason: reason == "return:recall")
        self.assertEqual(reason, "return:recall")
        self.assertEqual(json.loads(line)["turn"], 2344275)
        self.assertEqual(replay.policy._unviable_quest_floor[2], 40)


class WalledOffHuntAndSearch(WalledOffBoards):
    def test_the_retreats_leave_the_recorded_column(self):
        # The half-giant lay asleep through the five retreats: a strong monster is retreated
        # from asleep too (owner 2026-11-07).
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        self.assertEqual(replay.policy._engagement_owned_avoid_cells, COLUMN)

    def test_a_hunt_walled_off_by_the_column_reads_teleportation_once(self):
        replay, line, key, reason = self.replay(
            lambda _board, reason: reason == retreat_enclosure.TELEPORT_REASON)
        policy = replay.policy
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        raw = json.loads(line)
        self.assertEqual((raw["turn"], raw["player"]["y"], raw["player"]["x"]), (2344898, 8, 100))
        scroll = next(item for item in parse_snapshot(
            copy.deepcopy(raw), policy._monrace_knowledge).inventory if key[1:] == item.slot)
        self.assertEqual(scroll.tval, 70)
        self.assertEqual(policy._find_teleport_scroll(parse_snapshot(
            copy.deepcopy(raw), policy._monrace_knowledge)).slot, scroll.slot)
        self.post_item_command(policy, raw, key, READ_PROMPT)
        self.assertEqual(policy._engagement_owned_avoid_cells, COLUMN)  # every veto is kept
        # The board past the column: the walk goes on, and there is no second read.
        west = json.loads(self.boards["west"])
        _board, _key, reason = replay.decide(json.dumps(west, ensure_ascii=False))
        self.assertEqual(reason, hunt_target.REASON)

    def test_a_search_walled_off_by_the_column_reads_teleportation_then_melts_a_way(self):
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        _board, key, reason = self.at_the_stop(replay, edit=shown)
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.post_item_command(replay.policy, self.stop_raw(edit=shown), key, READ_PROMPT)
        # DECLARED: the read landed on this side after all.  Walled off again with no digger,
        # the recorded kit's Stone to Mud wands open a way round the column (owner 2026-11-06
        # 「壁を掘る」, Stone to Mud 「数える」): the walk toward the route's first wall.
        _board, key, reason = self.at_the_stop(replay, later=10, edit=shown)
        self.assertEqual(reason, retreat_enclosure.MELT_REASON)
        self.assertIn(key, set("12346789"))
        # DECLARED: each walk is taken (the player moved by the key, 10 game turns a step)
        # until the route's first wall is beside it, where the wand (slot h) is aimed at it.
        here, later = self.stop_raw(), 10
        position = [here["player"]["y"], here["player"]["x"]]
        for _ in range(60):
            if key[0] != "a":
                dy, dx = STEPS[key]
                position = [position[0] + dy, position[1] + dx]
            later += 10

            def moved(raw, position=tuple(position)):
                shown(raw)
                raw["player"]["y"], raw["player"]["x"] = position
            _board, key, reason = self.at_the_stop(replay, later=later, edit=moved)
            self.assertEqual(reason, retreat_enclosure.MELT_REASON)
            if key[0] == "a":
                break
        self.assertEqual(key[:2], "ah")
        self.assertIn(key[2:], set("12346789"))

    def test_a_veto_that_walls_nothing_off_leaves_the_loop_walking(self):
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        policy = replay.policy
        for cell in COLUMN - {Position(3, 93)}:
            policy._engagement_owned_avoid_cells.discard(cell)
            policy._engagement_avoid_cells.discard(cell)
        board, _key, reason = self.at_the_stop(replay)
        self.assertFalse(retreat_enclosure.holds_ground(policy, board))
        self.assertEqual(reason, quest_target_search.LOOP_REASON)


if __name__ == "__main__":
    unittest.main()
