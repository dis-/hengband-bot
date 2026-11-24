"""Quest 25 phase 2 on n1-a life-536 (2026-11-24 20:52:17-20:52:52): the pen seen, counted escaped.

The chain (Zombie warrior Lv38, HP 903, no telepathy nor evil ESP; one process, decisions
10525-10910 of the quest floor):

 * Phases 0-1 (the ambush from [10,1], the wall-passers on [7,1]) as the plan says.
 * Phase 2 (Ipsissimus): from [5,2] twelve crossbow bolts at [7,17] (``quest25:shot``,
   10894-10905).  The Ipsissimus on [7,17] is on every one of those boards (``visible_monsters``)
   and at 10904 「イプシシマスがあなたを指さして恐ろしげに呪文を唱えた！」; the bolts after 10896 miss
   it.  At 10906 the ten misses counted all three escaped (``Battle.assumed_escaped`` 3), the plan
   went on to the stragglers and walked to their stand [5,1] (10908) -- a cell the pen's summons
   reaches through [5,2] -- where the summons were fought until the Healing potions were gone
   (11077) and the player died (11126), phase 2's choke and restock (owner 2026-11-16 A) no
   longer asked.

The rule (owner 2026-11-06 phase2): escaped is read from 「テレポートしたメッセージで判断」, with
telepathy or evil ESP from the sight of the pen, and without them 「当たらない撃ちで補う」 (ten
shots at [7,17] with no hit).  The misses stand in for a pen the player cannot see; an Ipsissimus
the board shows on the pen is there, and the two behind it cannot leave while it stands
(「一体倒すと歩き回る」).  So a board showing one in the pen answers the shot (``_note_pen_shot``).

Recorded: tests/fixtures/n1a-536-q25-pen-seen-1124.json.gz
(tests/extract_n1a_536_q25_pen_seen_1124_fixture.py).  A fresh policy (no battle record: the
quest's first decision) decides the recorded boards in order through the public ``choose_key``,
each key confirmed as posted; the recorded boards are the player's recorded cells, not where the
replayed keys lead.  The skill knowledge is the last row before the floor.

DECLARED CONSTRUCTED (``UnseenPenTest``): the recorded boards through 10905, then nine misses
already counted (``Battle.pen_misses`` 9, a shot at the pen posted) and the board of 10906 with
or without its Ipsissimus.  An unseen pen draws no arrow (owner 2026-11-09, ``_unseen_fire``), so
the misses build up only from what is aimed at the grid (a ball); with the pen unseen as the
owner's rule supposes, the tenth still counts the three escaped.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.model import parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-536-q25-pen-seen-1124.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

IPSISSIMUS = 571
SHOT = "quest25:shot"
FRESH = {"version": 1, "floor": [0, 48, 25], "turn": 0, "battle": None}


def drive(boards=None, before=None):
    """{sequence: (cell, phase name, assumed escaped, key, reason)} of the replayed boards;
    ``before(sequence, policy)`` runs before each board's decision."""
    boards = CASE["second"]["boards"] if boards is None else boards
    case = dict(CASE, second=dict(CASE["second"], boards=boards), battle_record=FRESH)
    answers = {}
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), {}, None, case)
        for raw, row in zip(boards, CASE["second"]["recorded"]):
            if before is not None:
                before(row["sequence"], policy)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(snapshot)
            fight = policy._quest_navigators[25].phase_battle
            answers[row["sequence"]] = ((snapshot.player.position.y, snapshot.player.position.x),
                                        battle.PHASE_NAMES[fight.phase], fight.assumed_escaped,
                                        key, policy.last_reason)
            policy.confirm_key_posted(key)
    return answers


def nine_misses(seen: bool):
    """DECLARED CONSTRUCTED (module note): the boards through 10906, nine misses counted before it,
    its Ipsissimus kept (``seen``) or taken off."""
    last = [row["sequence"] for row in CASE["second"]["recorded"]].index(10906)
    boards = copy.deepcopy(CASE["second"]["boards"][:last + 1])
    if not seen:
        boards[-1]["visible_monsters"] = [monster for monster in boards[-1]["visible_monsters"]
                                          if monster["race_id"] != IPSISSIMUS]

    def before(sequence, policy):
        if sequence == 10906:
            fight = policy._quest_navigators[25].phase_battle
            fight.pen_misses, fight.pen_shot = 9, True

    return drive(boards, before)


class TheRecordingTest(unittest.TestCase):

    def test_the_shots_missed_the_ipsissimus_seen_on_the_pen(self):
        rows = dict(zip((row["sequence"] for row in CASE["second"]["recorded"]),
                        zip(CASE["second"]["boards"], CASE["second"]["recorded"])))
        for sequence in range(10894, 10906):
            board, row = rows[sequence]
            self.assertEqual((row["reason"], (board["player"]["y"], board["player"]["x"])),
                             (SHOT, (5, 2)))
            self.assertIn((IPSISSIMUS, 7, 17), {(monster["race_id"], monster["y"], monster["x"])
                                                for monster in board["visible_monsters"]})
        self.assertIn("イプシシマスがあなたを指さして恐ろしげに呪文を唱えた！", rows[10904][0]["messages"])
        self.assertEqual([rows[sequence][1]["reason"] for sequence in (10906, 10908, 10909)],
                         ["ranged:fire", "quest25:walk", "quest-strategy:hold"])
        self.assertEqual((rows[10909][0]["player"]["y"], rows[10909][0]["player"]["x"]), (5, 1))
        # The death's record: no Ipsissimus killed, all three counted escaped by the misses.
        fight = CASE["death_record"]["battle"]
        self.assertEqual(fight["assumed_escaped"], 3)
        self.assertNotIn(IPSISSIMUS, [race for race, _count in fight["kills"]["dict"]])


class SeenPenTest(unittest.TestCase):

    def test_the_pen_seen_phase_two_goes_on(self):
        answers = drive()
        for sequence in range(10894, 10909):
            _cell, phase, escaped, _key, reason = answers[sequence]
            self.assertEqual((sequence, phase, escaped), (sequence, "ipsissimus", 0))
        self.assertEqual(answers[10906][4], SHOT)   # the fire stays on the pen
        self.assertEqual(answers[10910][1], "ipsissimus")


class UnseenPenTest(unittest.TestCase):

    def test_the_tenth_miss_at_an_unseen_pen_counts_it_escaped(self):
        self.assertEqual(nine_misses(seen=False)[10906][1:3], ("stragglers", 3))

    def test_the_tenth_miss_at_a_seen_pen_does_not(self):
        self.assertEqual(nine_misses(seen=True)[10906][1:3], ("ipsissimus", 0))


if __name__ == "__main__":
    unittest.main()
