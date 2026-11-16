"""n1-c life-216 (2026-11-16): Recall read on 64F at full HP for a sleeping summoner, recorded.

Owner complaint: n1-c recalls abnormally often.  At 20:35:43 the first 64F board after the
town's Recall (HP 784/784) read Word of Recall (``re`` ``deep-teleport:recall``).  The absorbed
*Destruction* was held (22 charges; destruction_means ``depth_gate`` True, as the departure's
depth condition read it): the threat tiers' ``escape_means`` leaves "destruction" out only
because its scene test asks for an awake monster in view (destruction_use ``_threat_in_range``),
not for the means.

What happened: the emergency ladder's summoner rung (policy_combat ``summoner_open``: a summoner
may summon on its next move asleep or not, ``_summoner_may_summon_next_turn``) left a sleeping
ミッド・タイタン at game distance 15 beside a sleeping 白衣の高位修行僧 at 10.  *Destruction*
(``leaving`` the engagement) refused: the Titan, the most dangerous from contact, is beyond the
sure radius 13.  The Teleportation scroll came next and deep_teleport (owner 2026-11-14
「当てはまらない時は破壊または近寄って破壊を試みる」) asked its substitute: ``concerned`` counted only
the awake, so it found no monster and read Recall.  The walk was also held by the nearer monk
inside the radius ("any target in reach") although the use waited for the Titan.

Fixed: ``concerned`` counts the engagement's hostiles awake or asleep, and the walk goes until
the monster the use asks about (destruction_use ``reach_subject``) is within the sure radius.

Recorded: tests/fixtures/n1c-216-deep-recall-1116.pkl.xz
(tests/extract_n1c_216_deep_recall_1116_fixture.py): the town visit's arrival checkpoint replayed
67/67 through tests/replay_town_arrival.py, then the first 64F board.

Game (C:/hengband/src): cmd-item/cmd-usestaff.cpp:282 radius 13 + randint0(5); the distance is
the game's (grid.cpp distance: the larger axis plus half the smaller), 15 for (10, 10).

DECLARED CONSTRUCTED: the control empties the absorbed *Destruction*'s charges.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import deep_teleport, destruction_means, destruction_use, threat_tiers
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import game_distance, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-deep-recall-1116.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
TITAN, MONK = 702, 1173


def restored():
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    return policy, parse_snapshot(copy.deepcopy(CASE["board"]), policy._monrace_knowledge)


def monster(policy, snapshot, race):
    return next(m for m in policy._physical_hostiles(snapshot) if m.race_id == race)


class TheRecordingTest(unittest.TestCase):

    def test_means_held_and_both_asleep(self):
        self.assertEqual((CASE["decision"]["key"], CASE["decision"]["reason"]),
                         ("re", deep_teleport.RECALL_REASON))
        policy, snapshot = restored()
        self.assertEqual(snapshot.dungeon_level, 64)
        self.assertEqual(snapshot.player.hp, snapshot.player.max_hp)
        means = destruction_means.Means(policy, snapshot)
        self.assertEqual(means.absorbed_charges, 22)
        self.assertTrue(means.depth_gate())
        self.assertEqual(destruction_means.violations(policy, snapshot), ())
        here = snapshot.player.position
        titan, monk = monster(policy, snapshot, TITAN), monster(policy, snapshot, MONK)
        self.assertTrue(titan.asleep and monk.asleep)
        self.assertEqual(game_distance(here, titan.position), 15)
        self.assertEqual(game_distance(here, monk.position), 10)
        self.assertFalse(deep_teleport.allows(policy, snapshot))


class SleepingSummonerTest(unittest.TestCase):

    def test_sleeping_hostiles_are_concerned(self):
        policy, snapshot = restored()
        races = {m.race_id for m in deep_teleport.concerned(policy, snapshot)}
        self.assertIn(TITAN, races)

    def test_walks_toward_the_titan_instead_of_recall(self):
        policy, snapshot = restored()
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, threat_tiers.APPROACH_REASON)
        self.assertNotEqual(key, "re")
        policy2, snapshot2 = restored()
        step = deep_teleport._walk_step(policy2, snapshot2, deep_teleport.concerned(policy2, snapshot2))
        titan = monster(policy2, snapshot2, TITAN)
        self.assertLess(game_distance(step, titan.position),
                        game_distance(snapshot2.player.position, titan.position))

    def test_the_walk_aims_at_the_use_subject_not_the_nearer_monk(self):
        policy, snapshot = restored()
        targets = deep_teleport.concerned(policy, snapshot)
        subject = destruction_use.reach_subject(
            policy, snapshot, targets, destruction_use._target_race(policy, snapshot))
        self.assertEqual(subject.race_id, TITAN)
        self.assertFalse(destruction_use.usable(policy, snapshot, leaving=targets))


class NoMeansControlTest(unittest.TestCase):

    def test_without_a_charge_no_walk(self):
        # DECLARED CONSTRUCTED control: the absorbed *Destruction* has no charge left; no walk
        # toward a use that cannot be made (the 11-14 rule's Recall, destruction_use
        # means_spent_recall_key, is the floor's leave).
        policy, snapshot = restored()
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        emptied = tuple(dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)
        self.assertNotEqual(emptied, rows)
        policy._me_device_lists = dict(lists, staff=(turn, emptied))
        self.assertFalse(destruction_use.holds_means(policy, snapshot))
        self.assertTrue(destruction_use.means_spent(policy, snapshot))
        self.assertIsNone(deep_teleport._walk_step(policy, snapshot, deep_teleport.concerned(policy, snapshot)))
        policy.choose_key(snapshot)
        self.assertNotEqual(policy.last_reason, threat_tiers.APPROACH_REASON)


if __name__ == "__main__":
    unittest.main()
