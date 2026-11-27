"""Quest 25 on n1-c life-223 (2026-11-27 06:56:13-06:56:41): the restock read on phase 2's first board.

The chain (Zombie Magic-Eater CL42, HP 810/810, measured 568 per 10 game turns against the row's 200;
build bot-f108be477; one process, decisions 3958-4340 of the quest floor):

 * Acceptance (``fixedquest_readiness.strategy_force``): the always-hasted row, its five Healing
   potions lowered to two by ``required_force.over_match`` (HP 700 and 400 per 10 game turns);
   ``"heal_potions": {"measured": 2, "required": 2}``, ready.
 * Phases 0-1 (the ambush, the wall-passers) fought on [10,1] and [7,1], HP never under 674, back to
   810; no Healing potion drunk.
 * 4340 (turn 4303902), phase 2's first board, HP 810/810: ``quest25:restock-recall`` 'ri' -- the
   restock's potion arm (``HEALING_FLOOR`` 2) read the two potions it entered with as spent.  The
   walk out by '<' failed the quest (quest-attempts.jsonl ``failed``, then ``failed-done``) and the
   guaranteed Amulet of Telepathy was lost.

The rule (2026-11-27, supervisor; refines the owner's 2026-11-16 answer A 「隘路で迎え撃ち尽きる前に
帰還」): the potion arm fires only when the quest spent its potions down to the floor
(quest_entry_supply ``spent_to_floor``: at or under the floor and below the count the floor was
entered with).  The look-out arm is unchanged.

Recorded: tests/fixtures/n1c-223-q25-restock-1127.json.gz
(tests/extract_n1c_223_q25_restock_1127_fixture.py).  A fresh policy (no battle record: the quest's
first decision) decides the recorded boards in order through the public ``choose_key``, each key
confirmed as posted; the recorded boards are the player's recorded cells, not where the replayed
keys lead.  The skill knowledge is the last row before the floor.

DECLARED PARTIAL STATE: the magic-eater device lists.  The life's logs keep none (the bA/bB/bC
screens are not in the boards and no checkpoint was written in the window), so the replay runs
with no remembered list (``new_policy``'s ``{}``): the absorbed attacks and the absorbed Speed the
recording used are not offered, and the replayed keys before 4340 differ from the recorded ones.
The battle's phases advance from the recorded kill lines, and the decision pinned (4340) reads the
phase, the look-outs and the pack's potions, none of them from the lists.

DECLARED CONSTRUCTED (``SpentTest``): the recorded boards through 4339, then 4340 with one of the two
Healing potions taken off the pack (as drunk on the floor); or the recorded boards through 4340 and
4340's board decided once more with the battle's look-outs set to the limit.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_hall as hall, quest_entry_supply
from hengbot.model import SV_POTION_HEALING, TVAL_POTION, parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-223-q25-restock-1127.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

RESTOCK = "quest25:restock-recall"
PHASE2 = 4340
FRESH = {"version": 1, "floor": [0, 48, 25], "turn": 0, "battle": None}


def drive(boards=None, before=None, sequences=None):
    """{sequence: (phase name, key, reason, entered Healing)} of the replayed boards (``sequences``
    names them, default the recorded ones); ``before(sequence, policy)`` runs before each board's
    decision."""
    boards = CASE["second"]["boards"] if boards is None else boards
    sequences = [row["sequence"] for row in CASE["second"]["recorded"]] if sequences is None else sequences
    case = dict(CASE, second=dict(CASE["second"], boards=boards), battle_record=FRESH)
    answers = {}
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), {}, None, case)
        for raw, sequence in zip(boards, sequences):
            if before is not None:
                before(sequence, policy)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(snapshot)
            fight = policy._quest_navigators[25].phase_battle
            entered = getattr(policy, quest_entry_supply.STATE, None)
            answers[sequence] = (battle.PHASE_NAMES[fight.phase], key, policy.last_reason,
                                        None if entered is None else entered[1][quest_entry_supply.HEALING])
            policy.confirm_key_posted(key)
    return answers


def _healing(raw) -> int:
    return sum(item["count"] for item in raw["inventory"]
               if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_HEALING and item.get("aware"))


def _drunk_one(raw) -> dict:
    """DECLARED CONSTRUCTED: ``raw`` with one Potion of Healing fewer."""
    raw = copy.deepcopy(raw)
    for item in raw["inventory"]:
        if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_HEALING:
            item["count"] -= 1
    raw["inventory"] = [item for item in raw["inventory"] if item["count"] > 0]
    return raw


class TheRecordingTest(unittest.TestCase):

    def test_entered_with_the_rows_two_and_read_recall_on_phase_two_at_full_hp(self):
        recorded = CASE["second"]["recorded"]
        self.assertEqual(recorded[0]["heal_potions"], {"measured": 2, "required": 2})
        boards = dict(zip((row["sequence"] for row in recorded), CASE["second"]["boards"]))
        self.assertTrue(all(_healing(board) == 2 for board in boards.values()))
        last = recorded[-1]
        self.assertEqual((last["sequence"], last["turn"], last["reason"], last["key"]),
                         (PHASE2, 4303902, RESTOCK, "ri"))
        self.assertEqual((boards[PHASE2]["player"]["hp"], boards[PHASE2]["player"]["max_hp"]), (810, 810))
        self.assertEqual([row["event"] for row in CASE["attempts"]],
                         ["taken", "entered", "failed", "left", "failed-done"])


class EnteredWithTheRequirementTest(unittest.TestCase):

    def test_phase_two_goes_on_with_the_potions_it_entered_with(self):
        answers = drive()
        phase, key, reason, entered = answers[PHASE2]
        self.assertEqual((phase, entered), ("ipsissimus", 2))
        self.assertNotEqual(reason, RESTOCK)
        self.assertFalse(key.startswith("r"), (key, reason))
        self.assertTrue(all(answer[2] != RESTOCK for answer in answers.values()))


class SpentTest(unittest.TestCase):

    def test_a_potion_drunk_on_the_floor_down_to_the_floor_reads_recall(self):
        boards = copy.deepcopy(CASE["second"]["boards"])
        boards[-1] = _drunk_one(boards[-1])
        phase, key, reason, entered = drive(boards)[PHASE2]
        self.assertEqual((phase, entered, reason), ("ipsissimus", 2, RESTOCK))
        self.assertTrue(key.startswith("r"), key)

    def test_the_look_out_arm_still_reads_recall(self):
        # DECLARED CONSTRUCTED: phase 2 begins on 4340's own decision (which sets its look-outs to
        # 0), so 4340's board is decided once more with the look-outs at the limit.
        again = PHASE2 + 0.5
        sequences = [row["sequence"] for row in CASE["second"]["recorded"]] + [again]

        def before(sequence, policy):
            if sequence == again:
                policy._quest_navigators[25].phase_battle.lookouts = hall.LOOKOUT_LIMIT

        boards = [*CASE["second"]["boards"], CASE["second"]["boards"][-1]]
        answers = drive(boards, before, sequences)
        self.assertNotEqual(answers[PHASE2][2], RESTOCK)
        phase, key, reason, _entered = answers[again]
        self.assertEqual((phase, reason), ("ipsissimus", RESTOCK))
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
