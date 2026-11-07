"""Quest 25 on n1-c life-164 (2026-11-08 03:29:46-03:29:49), recorded.

Recorded: tests/fixtures/q25-recall-n1c-164-1108.json.gz (tests/extract_q25_recall_1108_fixture.py),
every board of the process started at 03:29:46 on the quest floor through decision 50, with the
recorded reason and key.  The process resumed on [1,18] with the corpse masses (死体の塊, race 202)
west of it, struck the one beside it twice (decisions 1-2), held, and on decision 43 read Word of
Recall for ``breeder-breakthrough:recall``: the breeder stalemate's window went from seven masses to
five (kept) and then from five to six (latched).  Leaving the floor fails Q25 (PRESET+ONCE,
KILL_ALL: quest.cpp leave_quest_check).  The latch came from this process's own window, not from a
carried breeder-floor record: a fresh policy deciding the boards in order reproduces it.

Owner 2026-11-08, verbatim: 「Q25の死体の塊では帰らない。」  One policy decides the boards in order
(``replay``), from a fresh state, through the public ``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import breeder_stalemate, quest25_geometry as geo
from hengbot.model import _parse_items, parse_snapshot
from hengbot.quest_find_exit import HOLD_REASON, MELEE_REASON
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "q25-recall-n1c-164-1108.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BY_SEQUENCE = {row["sequence"]: (board, row) for board, row in zip(CASE["boards"], CASE["recorded"])}
RECALL = 43
RECALL_REASON = "breeder-breakthrough:recall"


def new_policy(first):
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(first)
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    return policy


def replay():
    """sequence -> (key, reason, latched): one policy deciding every recorded board in order."""
    policy = new_policy(CASE["boards"][0])
    answers = {}
    for raw, row in zip(CASE["boards"], CASE["recorded"]):
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = str(policy.choose_key(snapshot))
        answers[row["sequence"]] = (key, policy.last_reason,
                                    policy._breeder_breakthrough_floor == snapshot.floor_key)
        policy.confirm_key_posted(key)
    return answers


ANSWERS = {}


def answer(sequence):
    if not ANSWERS:
        ANSWERS.update(replay())
    return ANSWERS[sequence]


def masses(raw):
    return sorted((m["y"], m["x"]) for m in raw["visible_monsters"] if m["race_id"] == geo.MASS)


class Q25MassNoRecallTest(unittest.TestCase):
    """Owner 2026-11-08 「Q25の死体の塊では帰らない。」"""

    def test_the_recording(self):
        raw, row = BY_SEQUENCE[RECALL]
        self.assertEqual((raw["floor"]["quest_id"], raw["floor"]["level"]), (geo.QUEST_ID, 48))
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (1, 18))
        self.assertEqual((row["key"], row["reason"]), ("rk", RECALL_REASON))
        self.assertEqual(len(masses(raw)), 6)
        self.assertEqual({race for race in (m["race_id"] for m in raw["visible_monsters"])}, {geo.MASS})
        self.assertEqual([r["sequence"] for r in CASE["recorded"] if r["reason"] == RECALL_REASON], [RECALL])
        self.assertEqual([(BY_SEQUENCE[s][1]["key"], BY_SEQUENCE[s][1]["reason"]) for s in (1, 2)],
                         [("4", MELEE_REASON), ("1", MELEE_REASON)])

    def test_the_recall_board_answers_with_the_plan(self):
        # The recording held on every board around it; the plan's key, not Word of Recall.
        self.assertEqual(answer(RECALL)[:2], ("5", HOLD_REASON))

    def test_no_board_latches_the_floor_or_reads_recall(self):
        for raw, row in zip(CASE["boards"], CASE["recorded"]):
            with self.subTest(sequence=row["sequence"]):
                key, reason, latched = answer(row["sequence"])
                self.assertFalse(latched)
                self.assertFalse((reason or "").startswith("breeder-breakthrough"), (key, reason))
                self.assertNotEqual(key[:1], "r")

    def test_the_masses_beside_are_still_struck(self):
        # The plan's adjacent-mass rule (owner 2026-11-07) is unchanged: decisions 1 and 2.
        self.assertEqual(answer(1)[:2], ("4", MELEE_REASON))
        self.assertEqual(answer(2)[:2], ("1", MELEE_REASON))

    def test_control_without_the_exemption_the_replay_reads_the_recorded_recall(self):
        # The fixture reproduces the incident: with the masses counted as before, the window
        # latches on 42 and decision 43 reads Word of Recall as recorded.
        with patch.object(breeder_stalemate, "_exempt_races", lambda policy, snapshot: frozenset()):
            answers = replay()
        self.assertEqual(answers[RECALL][:2], ("rk", RECALL_REASON))
        self.assertEqual([s for s, (_k, reason, _l) in answers.items() if reason == RECALL_REASON], [RECALL])


if __name__ == "__main__":
    unittest.main()
