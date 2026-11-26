"""n1-b life-419 2026-11-26 08:54 (Quest 33): the summon answer's blows at the Queen's ants read as a loop.

Recorded: life-419's decision rows of the session bot main 5175c3635 started (08:54:05) to its stop,
reduced by tests/extract_n1b_419_q33_fire_ants_1126_fixture.py (tests/fixtures/n1b-419-q33-fire-ants-1126).
The Queen Ant (race 581, S_ANT 1_IN_2, lib/edit/MonraceDefinitions.jsonc) came into view at (26,48) and
summoned ants at the player (「『女王アリ』が魔法でアリを召喚した。」), the giant fire ants (548, FRIENDS) among
them.  Quest 33's summon answer went after her (quest_summon_answer ``_go_after``: the absorbed powers at
her, the blows at the ants on the way) and killed her beside the player on (26,42) (「『女王アリ』を葬り去った。」);
then, as its chase order says, the summoned nearest first: a blow a board
(quest-strategy:summoned-strike), each killing about one ant, the ants in view falling 63 -> 41 and no
summon after the Queen died.  The blow was no row of the loop guard's stationary table (reasons.py,
the QUEST_COMBAT rows hold quest-strategy:melee, the plan's other blow from one post), so the
40-decision window stopped the bot: loop-detected, confined to (26,42).

Pinned: quest-strategy:summoned-strike is a fixed-quest attack from one post like quest-strategy:melee
(the wave or the quest ends it): the recorded run is not stopped; the same rows with the summon answer's
blow read as a walk (the reasoning before) are stopped at the record's stop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli, quest_summon_answer, reasons
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-q33-fire-ants-1126"
AILMENTS = ("blind", "confused", "afraid", "poisoned", "stunned", "cut", "paralyzed",
            "hallucinated")
STOP_CELL = (26, 42)
QUEEN_KILLED = "『女王アリ』を葬り去った。"
QUEEN_SUMMONS = "『女王アリ』が魔法でアリを召喚した。"


def load(name):
    return json.loads(lzma.decompress((FIXTURE / name).read_bytes()))


def board(row):
    floor = row["floor"]
    player = SimpleNamespace(position=Position(row["position"]["y"], row["position"]["x"]),
                             hp=row["hp"], mp=row["mp"], cut_rank=None, stun_rank=None,
                             **{name: False for name in AILMENTS})
    return SimpleNamespace(inside_arena=False, in_town=False,
                           floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
                           player=player, messages=row["messages"])


def first_stop(fed) -> int | None:
    """The index of the (snapshot, reason, key) the driver's cell window stops (cli's dungeon
    loop), else None."""
    recent, previous_position, previous_player = [], None, None
    for index, (snapshot, reason, key) in enumerate(fed):
        applies = cli._cell_loop_guard_applies(
            snapshot, reason, previous_position, previous_player, key)
        previous_position, previous_player = snapshot.player.position, snapshot.player
        if not applies:
            recent.clear()
            continue
        recent.append((snapshot.floor_key, snapshot.player.position.y, snapshot.player.position.x))
        if cli._is_looping(recent, window=LOOP_WINDOW):
            return index
    return None


def recorded_feed(rows, *, strike_as=None):
    return [(board(row), strike_as if strike_as and row["reason"] == quest_summon_answer.STRIKE_REASON
             else row["reason"], row["key"]) for row in rows]


class N1b419FireAntsRecordedTest(unittest.TestCase):
    def setUp(self):
        self.recorded = load("decisions.json.xz")
        self.decided = self.recorded[:-1]

    def test_the_record_is_the_stop(self):
        self.assertEqual(self.recorded[-1]["reason"], "loop-detected")
        last = self.recorded[-1]
        self.assertEqual((last["position"]["y"], last["position"]["x"]), STOP_CELL)
        self.assertEqual(last["floor"]["quest_id"], 33)
        # The Queen summoned at the player and died beside him before the window.
        killed = next(index for index, row in enumerate(self.decided)
                      if any(QUEEN_KILLED in message for message in row["messages"]))
        self.assertTrue(any(QUEEN_SUMMONS in message for row in self.decided[:killed]
                            for message in row["messages"]))
        after = self.decided[killed:]
        self.assertFalse(any(QUEEN_SUMMONS in message for row in after for message in row["messages"]))
        # After her: the summon answer's blows on (26,42), the ants in view falling.
        strikes = [row for row in after if row["reason"] == quest_summon_answer.STRIKE_REASON]
        self.assertGreaterEqual(len(strikes), 25)
        self.assertEqual({(row["position"]["y"], row["position"]["x"]) for row in after}, {STOP_CELL})
        self.assertEqual((after[0]["visible_hostiles"], after[-1]["visible_hostiles"]), (63, 41))
        kills = sum(message.count("巨大火アリを葬り去った") for row in after for message in row["messages"])
        self.assertGreaterEqual(kills, 15)

    def test_the_summon_answers_blow_is_a_quest_combat_row(self):
        self.assertTrue(reasons.stationary(quest_summon_answer.STRIKE_REASON))
        self.assertIn(quest_summon_answer.STRIKE_REASON, cli.QUEST_COMBAT_REASON_PREFIXES)

    def test_the_blows_from_one_post_are_no_loop(self):
        self.assertIsNone(first_stop(recorded_feed(self.decided)))
        # The same rows with the blow read as a reason the table does not hold were stopped where the
        # record stopped.
        self.assertEqual(first_stop(recorded_feed(self.decided, strike_as="quest-strategy:summoned-walk")),
                         len(self.decided) - 1)


if __name__ == "__main__":
    unittest.main()
