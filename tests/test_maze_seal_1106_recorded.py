"""A retreat's vetoes sealed a dead end in a forgetting maze (n1-c life-153, 2026-11-06 20:50).

Recorded: n1-c life-153, Labyrinth 13F (MAZE + FORGET), build cbdf723f5, turns 888821-889635.
On turn 889573 at (2,33) a 大蜘蛛 (index 13, race 175) lay asleep 7 cells west along the
one-wide top corridor.  ``threat:avoid-engagement`` (``_flee_step#4``) stepped east twice and
vetoed (2,33) and (2,34), the only way out of the three-cell dead end (2,34..36).  The explore,
descent and stair routes refused the vetoes; the idle fallback walked (2,35)<->(2,36)
(stuck:wander) until the loop guard, and the vetoes rode the checkpoint into the restart.

A sleeping monster does not act until it wakes (monster/monster-processor.cpp awake_monster),
so it is not retreated from.  DECLARED CONSTRUCTED for the retreat itself: the spider awake and
no ammunition carried on the boards from 889573 (``awake_spider``).  The retreat then still vetoes (2,33) -- the far end
of the pocket was a frontier when it stepped -- but not (2,34), which the pocket's end, seen by
then, shows would seal it (engagement_avoid_seal); and in the pocket the idle fallback takes
the enclosure ladder (retreat_enclosure ``sealed_in_key``) instead of the wander.

Fixture: tests/extract_maze_seal_1106_fixture.py.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path

from test_floor_dwell_seen_floor_recorded import EDIT, _Replay

from hengbot import retreat_enclosure
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge

FIXTURE = Path(__file__).parent / "fixtures" / "maze-seal-1106.jsonl.xz"
SPIDER_INDEX, SPIDER_RACE = 13, 175
FIRST_RETREAT_TURN, SECOND_RETREAT_TURN = 889573, 889585
STALL_TURNS = (889591, 889599, 889611, 889621, 889635)
FIRST_VETO, SECOND_VETO = Position(2, 33), Position(2, 34)
LADDER_REASONS = {
    retreat_enclosure.TELEPORT_REASON, retreat_enclosure.DIG_REASON,
    retreat_enclosure.DIG_WIELD_REASON, retreat_enclosure.MELT_REASON,
    retreat_enclosure.DISARM_REASON, retreat_enclosure.STRIKE_REASON,
    retreat_enclosure.RECALL_REASON,
}


AMMO_TVALS = {16, 17, 18}  # shots, arrows, bolts


def awake_spider(raw):
    """DECLARED: the spider awake from the first retreat's board on, and no ammunition
    carried there (awake, it would be shot at instead)."""
    if raw["turn"] >= FIRST_RETREAT_TURN:
        for monster in raw["visible_monsters"]:
            if (monster["index"], monster["race_id"]) == (SPIDER_INDEX, SPIDER_RACE):
                monster["asleep"] = False
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in AMMO_TVALS]


class MazeSealReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, edit=None):
        """Every recorded board through choose_key: (replay, {turn: reason}, {turn: vetoes})."""
        replay = _Replay(self, self.monrace)
        reasons, vetoes = {}, {}
        for line in self.lines:
            raw = json.loads(line)
            if edit is not None:
                edit(raw)
            board, _key, reason = replay.decide(json.dumps(raw, ensure_ascii=False))
            reasons[board.turn] = reason
            vetoes[board.turn] = set(replay.policy._engagement_owned_avoid_cells)
        return replay, reasons, vetoes

    def test_the_sleeping_spider_is_not_retreated_from(self):
        _replay, reasons, vetoes = self.replay()
        # Recorded: threat:avoid-engagement on both boards, then stuck:wander.
        self.assertNotEqual(reasons[FIRST_RETREAT_TURN], "threat:avoid-engagement")
        self.assertNotEqual(reasons[SECOND_RETREAT_TURN], "threat:avoid-engagement")
        self.assertFalse(vetoes[STALL_TURNS[-1]])

    def test_the_retreat_does_not_veto_the_pockets_last_way_out(self):
        _replay, reasons, vetoes = self.replay(awake_spider)
        self.assertEqual(reasons[FIRST_RETREAT_TURN], "threat:avoid-engagement")
        self.assertEqual(reasons[SECOND_RETREAT_TURN], "threat:avoid-engagement")
        self.assertEqual(vetoes[SECOND_RETREAT_TURN], {FIRST_VETO})
        self.assertNotIn(SECOND_VETO, vetoes[STALL_TURNS[-1]])

    def test_the_sealed_pocket_takes_the_enclosure_ladder_not_the_wander(self):
        _replay, reasons, vetoes = self.replay(awake_spider)
        self.assertIn(FIRST_VETO, vetoes[STALL_TURNS[0]])
        for turn in STALL_TURNS:
            self.assertNotEqual(reasons[turn], "stuck:wander", turn)
            self.assertIn(reasons[turn], LADDER_REASONS, turn)


if __name__ == "__main__":
    unittest.main()
