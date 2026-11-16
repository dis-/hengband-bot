"""Quest 25 phase 2 on n1-a life-528 (2026-11-16 13:12-13:13): the choke and the restock, recorded.

The chain (warrior Lv41, build bot-0f3b00a68; phase 2, Ipsissimus; no Teleportation read up to
phase 3, owner 2026-11-12):

 * The first process (its ring: decisions 11659-11753): from the chokes [7,1] and [3,1] the walk
   to the pen's sight stepped out ([6,1], [4,1]), Ipsissimus summoned at once, the summons were
   fought there -- beside the choke, on a cell the summons reaches -- and the rally walked back.
   Back on the choke at 11694, 11698 and 11704 with no shot at the pen; the same again at 11708 and
   11749, then the loop guard stopped the bot.
 * The last process (decisions 0-49): on [4,1] beside the choke [3,1] it fought the summons board
   after board (Ipsissimus summoned at 7 and 12), drank its Healing potions at 6, 8, 16 and 24
   (two left from decision 9 on), and died at 49.

The rules (owner 2026-11-16, answer A, verbatim 「隘路で迎え撃ち尽きる前に帰還」):

 * ``_rally`` / ``_choke_step_back``: with a monster beside the player and a choke (a cell no
   summons reaches) one step away, the step back to it; the fight is there.
 * ``_restock_recall``: three look-outs in a row back on the choke with no shot at the pen
   (``Battle.lookouts``, kept in the battle record over a restart), or the Healing potions
   (Healing and stronger) down to two: Word of Recall, past the ONCE floor's hold; the quest
   fails.

Recorded: tests/fixtures/n1a-528-q25-death-1116.json.gz
(tests/extract_n1a_528_q25_death_1116_fixture.py).  A fresh policy restores the record through the
real path and decides the recorded boards in order through the public ``choose_key``, each key
confirmed as posted (``confirm_key_posted``); the recorded boards are the player's recorded cells,
not where the replayed keys lead.

DECLARED: the record is the one the last process left (13:13:13), its turn set to the first
board's; for the first process's boards (an earlier time) its rally is cleared (``rallying``
False, no ``strong``), as the board before 11659 (a quiet hold on [7,1]) shows none; the skill
knowledge is the last process's.  The character is a warrior: no magic-eater lists.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.model import SV_POTION_HEALING, SV_POTION_LIFE, SV_POTION_STAR_HEALING, parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-528-q25-death-1116.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CHOKE_BACK = "quest25:choke-step-back"
RESTOCK = "quest25:restock-recall"


def drive(part, record=None, until=None):
    """[(sequence, cell, healing potions, key, reason, lookouts)] of ``part``'s boards."""
    case = dict(CASE, second=CASE[part], battle_record=record or CASE["battle_record"])
    boards, recorded = case["second"]["boards"], case["second"]["recorded"]
    answers = []
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), {}, None, case)
        for raw, row in zip(boards, recorded):
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(snapshot)
            battle = policy._quest_navigators[25].phase_battle
            answers.append((row["sequence"], (snapshot.player.position.y, snapshot.player.position.x),
                            healing(snapshot), key, policy.last_reason,
                            getattr(battle, "lookouts", None)))
            if row["sequence"] == until:
                break
            policy.confirm_key_posted(key)
    return answers


def healing(snapshot) -> int:
    """The recorded pack's Healing potions and stronger (the test's own count)."""
    return sum(item.count for item in snapshot.inventory
               if item.is_potion and item.aware and item.sval in (SV_POTION_HEALING,
                                                                  SV_POTION_STAR_HEALING,
                                                                  SV_POTION_LIFE))


def quiet_record():
    record = copy.deepcopy(CASE["battle_record"])   # DECLARED (module note)
    record["battle"]["rallying"] = False
    record["battle"]["strong"] = {"tuple": []}
    return record


class TheRecordingTest(unittest.TestCase):

    def test_fought_beside_the_choke_and_walked_out_again(self):
        rows = {(row["sequence"], row["reason"]) for row in CASE["lookouts"]["recorded"]}
        for sequence in (11704, 11708, 11749):
            self.assertIn((sequence, "quest25:walk-to-sight"), rows)
        last = {row["sequence"]: (board["player"]["y"], board["player"]["x"], row["reason"])
                for board, row in zip(CASE["second"]["boards"], CASE["second"]["recorded"])}
        self.assertEqual(last[9], (4, 1, "quest-strategy:melee"))
        self.assertEqual(last[49], (4, 1, "emergency:cornered-attack"))


class ChokeTest(unittest.TestCase):

    def test_beside_the_choke_the_step_back_to_it(self):
        answers = drive("second", until=2)
        sequence, cell, _potions, key, reason, _lookouts = answers[-1]
        self.assertEqual((sequence, cell), (2, (4, 1)))
        self.assertEqual((key, reason), ("8", CHOKE_BACK))   # to [3,1]


class LookoutTest(unittest.TestCase):

    def test_the_third_fruitless_look_out_reads_recall(self):
        answers = drive("lookouts", quiet_record(), until=11704)
        backs = [(sequence, lookouts) for sequence, _cell, _p, _k, _r, lookouts in answers]
        self.assertEqual([row for row in backs if row[0] in (11694, 11698)], [(11694, 1), (11698, 2)])
        self.assertTrue(all(reason != RESTOCK for *_rest, reason, _l in answers[:-1]))
        sequence, cell, potions, key, reason, lookouts = answers[-1]
        self.assertEqual((sequence, cell, lookouts, reason), (11704, (3, 1), 3, RESTOCK))
        self.assertGreater(potions, 2)
        self.assertTrue(key.startswith("r"), key)

    def test_a_shot_at_the_pen_sets_the_count_back(self):
        from hengbot import quest25_battle as battle

        ctx = type("Ctx", (), {})()
        ctx.battle = battle.Battle(phase=battle.phase_index("ipsissimus"), lookouts=2)
        self.assertEqual(battle._pen_shot(ctx, "f1"), "f1")
        self.assertEqual(ctx.battle.lookouts, 0)
        ctx.battle.lookouts = 2
        battle._pen_shot(ctx, None)
        self.assertEqual(ctx.battle.lookouts, 2)


class HealingFloorTest(unittest.TestCase):

    def test_two_healing_potions_left_recall_is_read(self):
        answers = drive("second", until=9)
        self.assertTrue(all(reason != RESTOCK for *_rest, reason, _l in answers[:-1]))
        sequence, _cell, potions, key, reason, _lookouts = answers[-1]
        self.assertEqual((sequence, potions, reason), (9, 2, RESTOCK))
        self.assertTrue(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
