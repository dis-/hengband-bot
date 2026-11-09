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
import dataclasses
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import breeder_stalemate, quest25_battle as battle, quest25_battle_record, quest25_geometry as geo
from hengbot.model import _parse_items, parse_snapshot
from hengbot.quest_find_exit import MELEE_REASON
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
        # The recording held on every board around it; the plan's key, not Word of Recall.  Owner
        # 2026-11-08 「射線にいれば範囲で撃つ」: the plan now shoots the masses in its line of fire
        # instead of holding (quest25_battle._breeders_in_line_key; no absorbed list on these boards,
        # so the crossbow at the nearest one, two grids west).
        self.assertEqual(answer(RECALL)[:2], ("fp*p44t5", battle.SHOT_REASON))

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
        # DECLARED WALL: the recorded build's 20-attack window too (owner 2026-11-09 made it 100).
        with patch.object(breeder_stalemate, "_exempt_races", lambda policy, snapshot: frozenset()),                 patch.object(breeder_stalemate, "FLEE_AFTER_PLAYER_ACTIONS", 20):
            answers = replay()
        self.assertEqual(answers[RECALL][:2], ("rk", RECALL_REASON))
        self.assertEqual([s for s, (_k, reason, _l) in answers.items() if reason == RECALL_REASON], [RECALL])


def mass_phase_decide(sequence, position):
    """(key, reason) of board ``sequence`` decided by a fresh policy restarted in the corpse-mass
    phase.  DECLARED CONSTRUCTED: the previous process's battle record (quest25_battle_record, read
    by the real restore at the first decision) in phase4 with the corridor lit, as a visit that
    reached it leaves it; the player moved to ``position`` (the recorded masses as they stood)."""
    raw = copy.deepcopy(BY_SEQUENCE[sequence][0])
    raw["player"]["y"], raw["player"]["x"] = position
    fresh = battle.Battle(phase=battle.PHASE_NAMES.index("corpse-masses"), ready=True, lit=True)
    with TemporaryDirectory() as directory:
        path = Path(directory) / "q25-battle.json"
        path.write_text(json.dumps({
            "version": quest25_battle_record.VERSION, "floor": [0, 48, geo.QUEST_ID], "turn": raw["turn"],
            "battle": {field.name: quest25_battle_record._encode(getattr(fresh, field.name))
                       for field in dataclasses.fields(fresh) if field.name != "observed"},
            "board": None}), encoding="utf-8")
        policy = new_policy(raw)
        policy._q25_battle_record_path = path
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
    return key, policy.last_reason


class MassWidestFiringCellTest(unittest.TestCase):
    """Owner 2026-11-09 「一番多く届く位置へ」: in the corpse-mass phase the shot is taken from the cell
    that reaches the most masses (quest_firing_cells ``reach``, the Q2 fix's measure) of the cells
    the plan may stand on, not from the fixed [1,6].  Board 1: seven masses at [1,14]-[1,17],
    [2,14], [2,16], [2,17]; the crossbow reaches 10, so [1,6] reaches five, the open door [1,7]
    all seven (trapless, out of every caster's fire and the dreadmaster's vision, beside none)."""

    def test_from_1_6_one_step_to_the_door_that_reaches_all_seven(self):
        self.assertEqual(mass_phase_decide(1, (1, 6)), ("6", battle.MASS_CELL_REASON))

    def test_on_1_7_the_shot(self):
        key, reason = mass_phase_decide(1, (1, 7))
        self.assertEqual(reason, battle.SHOT_REASON)
        self.assertTrue(key.startswith("f"), key)

    def test_when_1_6_reaches_them_all_it_stays_and_shoots(self):
        # Board 43: six masses within [1,14]-[2,16], all within reach of [1,6] as of [1,7].
        key, reason = mass_phase_decide(43, (1, 6))
        self.assertEqual(reason, battle.SHOT_REASON)
        self.assertTrue(key.startswith("f"), key)


if __name__ == "__main__":
    unittest.main()
