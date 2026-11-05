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

DECLARED CONSTRUCTED: on the stop board, the ground visited, its frontiers written off and the
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
VETOES_DONE_TURN = 2344864


class WalledOffBoards(loops.ItemCommandBoards):
    """The fixture's boards through choose_key (no tests of its own)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.boards = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

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


class WalledOffHuntAndSearch(WalledOffBoards):
    def test_the_retreats_leave_the_recorded_column(self):
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

    def test_a_search_walled_off_by_the_column_reads_teleportation_then_again(self):
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        _board, key, reason = self.at_the_stop(replay)
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.post_item_command(replay.policy, json.loads(self.boards["stop"]), key, READ_PROMPT)
        # DECLARED: the read landed on this side after all.  Walled off again, with no digger,
        # trap or weak enemy and 15 scrolls over the reserve of 5, the owner's 2026-11-06 answer
        # reads Teleportation again (retreat_enclosure; tests/test_walled_off_again_1106_recorded).
        _board, key, reason = self.at_the_stop(replay, later=10)
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.assertEqual(key, "re")

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
