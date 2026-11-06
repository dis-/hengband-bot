"""A remembered never-moving monster is forgotten once it is killed (owner 2026-11-06
「脅威が見えなくなったら消す」, immobile_threat_memory with retreat_veto_life's test).

Recorded: n1-c life-156, Labyrinth 10F (MAZE + FORGET), build 87d9fd576, 2026-11-06
23:06:02-23:06:52, 442 stuck:wander.  A レッド・ゼリー (index 11, race 131, NEVER_MOVE,
TOUCH:LOSE_STR) at (10,42) was shot dead from (13,42): turn 1033667 prints
「レッド・ゼリーは死んだ。」 with the jelly in view on the board before.  The forgetting maze kept
its cell, three away and unlit, out of the empty-cell test, so the memory kept the jelly and its
ring (9..11, 41..43) cut the one-wide junction: from turn 1034095 no frontier and no known stair
was reachable and the bot wandered.

Fixture: tests/extract_immobile_kill_1106_fixture.py: every Labyrinth 10F board from the arrival
through 1034095.

DECLARED CONSTRUCTED: the live map-area cast of turn 1031502 (the bot notes it from its own
command, which an open-loop replay does not see) is added to the exploration ledger as the live
bot had it: centre (18,55), radius 30.  The controls drop the kill line from board 1033667 (the
jelly alive) or show index 11 with another race on a later board.

The stuck walk to a remembered stair (``RememberedStairOnForgettingMaze``): the recorded upstairs
(14,28) leads to the wilderness from 10F, the Labyrinth's top (wilderness_exit), and the
recorded downstairs (4,38) was expired, so on the recorded floor nothing named a stair to take.
DECLARED CONSTRUCTED there: every board on 11F (its '<' leads to 10F), and on the stall board
every remembered frontier given up and the mapped corridor (14,29..31) between the frontier
(14,32) and the upstairs remembered as walked floor -- the floor nothing is left to explore on.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path

from test_floor_dwell_seen_floor_recorded import EDIT, _Replay

from hengbot import goal_route, immobile_threat_memory
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge

FIXTURE = Path(__file__).parent / "fixtures" / "immobile-kill-1106.jsonl.xz"
JELLY = Position(10, 42)
JELLY_INDEX, JELLY_RACE = 11, 131
KILL_TURN = 1033667
KILL_LINE = "レッド・ゼリーは死んだ。"
MAP_AREA_TURN = 1031502
MAP_AREA = (18, 55, 30)
STALL_TURN = 1034095


def without_the_kill(raw):
    """DECLARED: the jelly survives the last bolt."""
    if raw["turn"] == KILL_TURN:
        raw["messages"] = [line for line in raw["messages"]
                           if (line if isinstance(line, str) else line.get("text")) != KILL_LINE]


def another_race_at_its_index(turn):
    """DECLARED: index 11 shown with another race (the jelly gone, the index reused)."""
    def edit(raw):
        if raw["turn"] == turn:
            raw["detected_monsters"] = [*raw.get("detected_monsters", []), {
                "asleep": True, "confused": False, "detected": True, "esp": False, "fast": False,
                "fearful": False, "friendly": False, "health": "unhurt", "index": JELLY_INDEX,
                "invulnerable": False, "level": None, "name": "ジャイアント・白ネズミ", "pet": False,
                "race_id": 21, "slow": False, "stunned": False, "x": 60, "y": 2}]
    return edit


class ImmobileKillReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, edit=None, until=STALL_TURN):
        """Every recorded board through choose_key up to ``until``: (replay, {turn: reason})."""
        replay = _Replay(self, self.monrace)
        reasons, remembered = {}, {}
        for line in self.lines:
            raw = json.loads(line)
            if raw["turn"] > until:
                break
            if edit is not None:
                edit(raw)
            board, _key, reason = replay.decide(json.dumps(raw, ensure_ascii=False))
            reasons[board.turn] = reason
            remembered[board.turn] = {monster.position
                                      for monster in immobile_threat_memory.remembered(replay.policy)}
            if board.turn == MAP_AREA_TURN:
                replay.policy._exploration_ledger.mapped_areas.add(MAP_AREA)
        return replay, reasons, remembered

    def test_the_jelly_is_remembered_and_ringed_before_its_kill(self):
        replay, _reasons, remembered = self.replay(until=KILL_TURN - 1)
        self.assertIn(JELLY, remembered[max(remembered)])
        self.assertTrue(immobile_threat_memory.ring_cells(JELLY)
                        <= immobile_threat_memory.route_cells(replay.policy))

    def test_its_kill_line_forgets_the_jelly_and_the_maze_is_walked_on(self):
        replay, reasons, remembered = self.replay()
        self.assertNotIn(JELLY, remembered[KILL_TURN])
        self.assertFalse(immobile_threat_memory.route_cells(replay.policy))
        self.assertNotEqual(reasons[STALL_TURN], "stuck:wander")
        self.assertEqual(reasons[STALL_TURN], "explore")

    def test_alive_the_jelly_keeps_its_ring(self):
        replay, _reasons, remembered = self.replay(without_the_kill)
        self.assertIn(JELLY, remembered[STALL_TURN])
        self.assertTrue(immobile_threat_memory.ring_cells(JELLY)
                        <= immobile_threat_memory.route_cells(replay.policy))

    def test_its_index_shown_with_another_race_forgets_it(self):
        later = sorted(json.loads(line)["turn"] for line in self.lines
                       if json.loads(line)["turn"] > KILL_TURN)[2]

        def edit(raw):
            without_the_kill(raw)
            another_race_at_its_index(later)(raw)

        _replay, _reasons, remembered = self.replay(edit, until=later)
        self.assertIn(JELLY, remembered[KILL_TURN])
        self.assertNotIn(JELLY, remembered[later])


UPSTAIRS = Position(14, 28)
CORRIDOR = {(14, 29), (14, 30), (14, 31)}


def on_11f(raw):
    """DECLARED: the Labyrinth's 11F, whose '<' leads to 10F."""
    raw["floor"]["level"] = 11


class RememberedStairOnForgettingMaze(ImmobileKillReplay):
    """Nothing to explore on a forgetting maze: the walk takes a remembered stair out of view."""

    def test_the_stuck_walk_routes_to_the_remembered_upstairs(self):
        replay, _reasons, _remembered = self.replay(on_11f, until=STALL_TURN - 1)
        raw = json.loads(self.lines[-1])
        self.assertEqual(raw["turn"], STALL_TURN)
        on_11f(raw)
        line = json.dumps(raw, ensure_ascii=False)
        board = replay.board(line)
        policy = replay.policy
        self.assertTrue(policy._is_forgetting_maze(board))
        self.assertNotIn(UPSTAIRS, board.grids)
        self.assertIn(UPSTAIRS, policy._remembered_upstairs)
        corridor = {Position(*cell) for cell in CORRIDOR}
        policy._remembered_floor_t.update(CORRIDOR)
        policy._remembered_known_t.update(CORRIDOR)
        policy._remembered_marked_t.update(CORRIDOR)
        ground = [*board.grids, *(Position(*cell) for cell in policy._floor_t), *corridor]
        policy._probed_frontiers.update(ground)
        policy._visit_counts.update(ground)
        board, _key, reason = replay.decide(line)
        self.assertEqual(reason, "stuck:seek-stairs")
        routes = [commitment.path for commitment in goal_route._commitments(policy).values()
                  if commitment.turn == STALL_TURN]
        self.assertIn(UPSTAIRS, [path[-1] for path in routes])


if __name__ == "__main__":
    unittest.main()
