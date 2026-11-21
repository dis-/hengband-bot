"""n1-b life-411 2026-11-21 13:59 (Angband 99F): the battle's healing rests read as a loop.

Recorded: the incident capture 20261121-135909-loop-detected (bot main b9efeeca0), its decision
rows reduced to what the driver's cell loop guard reads (tests/fixtures/n1b-411-99f-rest-loop-1121).
The 99F/100F battle held its stand at (8,76) (angband-finale:hold), left by Teleportation at 1035
HP (angband-finale:teleport) and rested where it landed (angband-finale:rest, 'R&\\r'): at (7,20)
and, after another Teleportation, at (3,75).  Every rest was cut short (no monster in view;
the monsters sensed by telepathy moving), yet the HP rose 1041 -> 1111 of 1153 over 29 rests.
The driver exempts a recovering rest from its cell window only under the reason "rest"; the
battle's rest was counted, and the 40-decision window stopped the bot: loop-detected, confined
to (3,75) (7,20) (8,76).

Pinned: a battle rest on the same cell that raised the HP is no confined decision, as the
ordinary rest is not, so the recorded run is not stopped; the same rests with the HP held still
(a rest that restores nothing) are still stopped by the window.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli
from hengbot.angband_finale_battle import REST_REASON
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-99f-rest-loop-1121" / "decisions.json.xz"
AILMENTS = ("blind", "confused", "afraid", "poisoned", "stunned", "cut", "paralyzed",
            "hallucinated")


def rows():
    return json.loads(lzma.decompress(FIXTURE.read_bytes()))


def board(row, hp=None):
    floor = row["floor"]
    player = SimpleNamespace(position=Position(row["position"]["y"], row["position"]["x"]),
                             hp=row["hp"] if hp is None else hp, mp=row["mp"],
                             cut_rank=None, stun_rank=None, **{name: False for name in AILMENTS})
    return SimpleNamespace(inside_arena=False, in_town=False,
                           floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
                           player=player, messages=row["messages"])


def first_stop(recorded, *, hold_hp=False) -> int | None:
    """The row whose decision the driver's cell window stops (cli's dungeon loop), else None."""
    recent, previous_position, previous_player = [], None, None
    for index, row in enumerate(recorded):
        snapshot = board(row, recorded[0]["hp"] if hold_hp else None)
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


class N1b411RestLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.recorded = rows()

    def test_the_record_is_the_stop(self):
        self.assertEqual(self.recorded[-1]["reason"], "loop-detected")
        rests = [row for row in self.recorded[-1 - LOOP_WINDOW:-1] if row["reason"] == REST_REASON]
        self.assertEqual({(row["position"]["y"], row["position"]["x"]) for row in rests},
                         {(7, 20), (3, 75)})
        self.assertEqual((rests[0]["hp"], rests[-1]["hp"]), (1041, 1111))

    def test_healing_battle_rests_are_no_loop(self):
        decided = self.recorded[:-1]
        self.assertIsNone(first_stop(decided))
        # The same decisions with the HP held still: the rests restore nothing and still stop.
        self.assertEqual(first_stop(decided, hold_hp=True), len(decided) - 1)


if __name__ == "__main__":
    unittest.main()
