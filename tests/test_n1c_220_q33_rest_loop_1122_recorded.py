"""n1-c life-220 2026-11-22 18:29 (Quest 33): the plan's recovering rests read as a loop.

Recorded: the capture 20261122-182956-loop-detected (bot main 5c5f6c353), reduced by
tests/extract_n1c_220_q33_rest_loop_1122_fixture.py (tests/fixtures/n1c-220-q33-rest-loop-1122).
After the disengage's fight with the giant fire ants on (2,4), nothing acted on the player and Quest
33's summon answer rested ('R&\\r', quest-strategy:summoned-rest, quest_summon_answer._rest_key: HP
short of the maximum).  Every rest was cut short after a turn (no monster in view; the ants, the
Dark elven warlocks and Bokrug sensed by telepathy moving: monster-floor/monster-move.cpp disturbs
a sensed hostile's move), yet the HP rose 737 -> 973 of 978 over 40 rests.  The driver exempted a
recovering rest from its cell window only under the reasons "rest" and "angband-finale:rest"; the
plan's rest was counted, and the 40-decision window stopped the bot: loop-detected, confined to
(2,4), one rest short of the full HP the plan goes on from.

Pinned: the driver reads the rest by its command (REST_MACRO) as cli.main feeds it the decided key,
so a rest on the same cell that raised the HP is no confined decision whichever producer sent it:
the recorded run is not stopped; the same rests with the HP held still (a rest that restores
nothing) are still stopped, and so is the record read by its reason alone (the old reading).
Through the public choose_key the captured boards are answered by the plan's rest while the HP is
short, and the board after the stop (HP 978 of 978) by the plan's next step, not a rest.

DECLARED CONSTRUCTED (the choose_key replay): the policy is n1-c life-217's town arrival
(tests/test_quest33_alignment_split ``recorded``), not life-220's; the Q33 navigator is put in the
disengaged state the capture's plan was in (the summon answer's steps after a disengage), and the
board's skill-list values are filled (that policy never read life-220's ~f list).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hengbot import cli, quest_summon_answer
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import REST_MACRO
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-q33-rest-loop-1122"
AILMENTS = ("blind", "confused", "afraid", "poisoned", "stunned", "cut", "paralyzed",
            "hallucinated")
REST_CELL = (2, 4)
LAST_TURN = 3148214  # the stop's board
# me_staff_sequence's periodic reads of the absorbed lists: the constructed policy never saw
# life-220's lists, so it asks for them between the rests.
LIST_READ_REASON = "periodic:magic-eater-powers"


def load(name):
    return json.loads(lzma.decompress((FIXTURE / name).read_bytes()))


def board(row, hp=None):
    floor = row["floor"]
    player = SimpleNamespace(position=Position(row["position"]["y"], row["position"]["x"]),
                             hp=row["hp"] if hp is None else hp, mp=row["mp"],
                             cut_rank=None, stun_rank=None, **{name: False for name in AILMENTS})
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


def recorded_feed(rows, *, hold_hp=False, by_reason=False):
    return [(board(row, rows[0]["hp"] if hold_hp else None), row["reason"],
             None if by_reason else row["key"]) for row in rows]


class N1c220RestLoopRecordedTest(unittest.TestCase):
    def setUp(self):
        self.recorded = load("decisions.json.xz")

    def test_the_record_is_the_stop(self):
        self.assertEqual(self.recorded[-1]["reason"], "loop-detected")
        rests = self.recorded[-1 - LOOP_WINDOW:-1]
        self.assertEqual({(row["reason"], row["key"]) for row in rests},
                         {(quest_summon_answer.REST_REASON, REST_MACRO)})
        self.assertEqual({(row["position"]["y"], row["position"]["x"]) for row in rests}, {REST_CELL})
        self.assertEqual((rests[0]["hp"], rests[-1]["hp"]), (737, 973))
        self.assertEqual(self.recorded[-2]["turn"], LAST_TURN)

    def test_recovering_plan_rests_are_no_loop(self):
        decided = self.recorded[:-1]
        self.assertIsNone(first_stop(recorded_feed(decided)))
        # The same rests with the HP held still restore nothing and are still stopped ...
        self.assertEqual(first_stop(recorded_feed(decided, hold_hp=True)), len(decided) - 1)
        # ... and read by the reason alone (the old reading) they were stopped at the record.
        self.assertEqual(first_stop(recorded_feed(decided, by_reason=True)), len(decided) - 1)


class N1c220RestChooseKeyTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)

    def answers(self):
        out = []
        for raw in load("boards.json.xz"):
            snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
            snapshot = replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0,
                                                        shield_skill=0))
            navigator = _navigator(self.policy, snapshot, QUEST)
            if navigator.summon_state is None:
                navigator.summon_state = quest_summon_answer.DISENGAGED
            key = str(self.policy.choose_key(snapshot))
            out.append((snapshot, self.policy.last_reason, key))
            self.policy.confirm_key_posted(key)
        return out

    def test_the_plan_rests_while_short_and_goes_on_at_full_hp(self):
        answers = self.answers()
        *resting, (after, after_reason, after_key) = answers
        self.assertEqual(after.turn, 3148221)
        self.assertEqual((after.player.hp, after.player.max_hp), (978, 978))
        for snapshot, reason, key in resting:
            self.assertEqual(snapshot.player.position, Position(*REST_CELL))
            self.assertLess(snapshot.player.hp, snapshot.player.max_hp)
            self.assertIn((reason, key) if reason != LIST_READ_REASON else (reason,),
                          {(quest_summon_answer.REST_REASON, REST_MACRO), (LIST_READ_REASON,)}, snapshot.turn)
        rests = [answer for answer in resting if answer[1] == quest_summon_answer.REST_REASON]
        self.assertGreaterEqual(len(rests), 30)
        self.assertNotEqual(after_key, REST_MACRO)
        self.assertNotEqual(after_reason, quest_summon_answer.REST_REASON)
        # The driver's window fed these answers as cli.main feeds them: no stop.
        self.assertIsNone(first_stop(answers))
        self.assertIsNotNone(first_stop([(snapshot, reason, None) for snapshot, reason, _ in answers]))


if __name__ == "__main__":
    unittest.main()
