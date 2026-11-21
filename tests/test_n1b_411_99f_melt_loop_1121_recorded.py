"""n1-b life-411 2026-11-21 13:18 (Angband 99F): Stone to Mud from one cell read as a loop.

Recorded: the incident capture 20261121-131825-loop-detected (bot main 45486042b, the first
99F/100F expedition), its decision rows reduced to what the driver's cell loop guard reads
(tests/fixtures/n1b-411-99f-melt-loop-1121).  The battle's stand at (11,169) opened its line to
the target with twelve absorbed Stone to Mud uses (angband-finale:melt:absorbed-power), each
board after naming one more wall turned to mud; a Teleportation and rests followed, then at
(4,192) the sealed pocket's digging (livelock:stone-to-mud:absorbed-power) melted twelve walls
west, one a use, and the player stepped west along the tunnel.  The driver's window (40
decisions on at most six cells, cli._is_looping) counted every one of these uses and stopped the
bot: loop-detected, confined to (4,191) (4,192) (11,169) (12,168) (13,102) (13,167).

Game (C:/hengband/src): wall_to_mud is a beam of KILL_WALL that stops at the first grid without
PROJECTION; effect/effect-feature.cpp turns that STONE grid into floor and prints
「{}が溶けて泥になった！」 for it -- each of these boards names the wall the previous use melted, so
the map changed.  Pinned: a board on the same cell that names a melted wall is no confined
decision (as a recovering rest is not), so the recorded run is not stopped; the 40-decision
window without the melts still is.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-99f-melt-loop-1121" / "decisions.json.xz"
AILMENTS = ("blind", "confused", "afraid", "poisoned", "stunned", "cut", "paralyzed",
            "hallucinated")


def rows():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()))


def board(row, messages=None, hp=None):
    floor = row["floor"]
    player = SimpleNamespace(position=Position(row["position"]["y"], row["position"]["x"]),
                             hp=row["hp"] if hp is None else hp, mp=row["mp"],
                             cut_rank=None, stun_rank=None,
                             **{name: False for name in AILMENTS})
    return SimpleNamespace(inside_arena=False, in_town=False,
                           floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
                           player=player,
                           messages=row["messages"] if messages is None else messages)


def first_stop(recorded, *, drop_messages=False, hold_hp=False) -> int | None:
    """The row whose decision the driver's cell window stops (cli's dungeon loop), else None."""
    recent, previous_position, previous_player = [], None, None
    for index, row in enumerate(recorded):
        snapshot = board(row, [] if drop_messages else None,
                         recorded[0]["hp"] if hold_hp else None)
        applies = cli._cell_loop_guard_applies(
            snapshot, row["reason"], previous_position, previous_player)
        previous_position, previous_player = snapshot.player.position, snapshot.player
        if not applies:
            recent.clear()
            continue
        recent.append((snapshot.floor_key, snapshot.player.position.y, snapshot.player.position.x))
        if cli._is_looping(recent, window=LOOP_WINDOW):
            return index
    return None


class N1b411MeltLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.recorded = rows()

    def test_the_record_is_the_stop(self):
        self.assertEqual(self.recorded[-1]["reason"], "loop-detected")
        window = self.recorded[-1 - LOOP_WINDOW:-1]
        melts = [row for row in window
                 if row["reason"] in {"angband-finale:melt:absorbed-power",
                                      "livelock:stone-to-mud:absorbed-power"}]
        self.assertEqual(len(melts), 25)
        self.assertEqual({(row["position"]["y"], row["position"]["x"]) for row in melts},
                         {(11, 169), (4, 192), (4, 191)})

    def test_melting_from_one_cell_is_no_loop(self):
        decided = self.recorded[:-1]
        self.assertIsNone(first_stop(decided))
        # The HP held still (the battle's healing rests, another exemption, taken away): the
        # melts alone keep the window open ...
        self.assertIsNone(first_stop(decided, hold_hp=True))
        # ... and the same decisions, their boards naming no melted wall, are still stopped.
        self.assertEqual(first_stop(decided, drop_messages=True, hold_hp=True), len(decided) - 1)


if __name__ == "__main__":
    unittest.main()
