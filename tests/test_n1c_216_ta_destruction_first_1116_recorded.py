"""n1-c life-216 (2026-11-16): *Destruction* before the absorbed Teleport Away, recorded.

Owner 2026-11-16 (question 「勝てない敵が射程内にいて *破壊* も使える時、今は テレポート・アウェイ を
先に撃っています。どちらを先にしますか？」, answer 「常に *破壊* を先」): the THREAT occasion's Teleport
Away (me_powers ``unbeatable-in-range``) offers its target to *Destruction* first
(me_powers ``_destruction_first``, destruction_use ``key`` with ``leaving`` the same target); only
where *Destruction* is not usable is the Teleport Away cast.  In n1-c 17:01-19:44, 198 Teleport
Away casts, 193 with *Destruction* available.

Recorded: tests/fixtures/n1c-216-ta-destruction-1116.pkl.xz
(tests/extract_n1c_216_ta_destruction_1116_fixture.py): 64F, game turn 3030658 (19:44:11, decision
15311), アイアン・リッチ (a summoner: T3, left as a T1 is) beside the player, the absorbed
*Destruction* at 97%; live ``mCn3`` ``me-power:unbeatable-in-range:teleport-away``.

Game (C:/hengband/src): spell-kind/spells-floor.cpp destroy_area deletes every monster in the
circle but a QUESTOR; radius 13 + randint0(5) (cmd-item/cmd-usestaff.cpp:282), so the adjacent
target is always inside.

DECLARED: the skill knowledge the checkpoint lacks is given as the investigation gave it (skills
1 and 3 at exp 0, the board's level).  DECLARED CONSTRUCTED: the controls set the destruction_use
memory's fallback (the previous use failed) and empty the absorbed *Destruction*'s charges.
Not covered here: a held-T1 target (this board's supply fight is stopped, which overrides the held
side, threat_tiers ``decided``); the trigger offers *Destruction* whatever the tier that made it
due (me_powers ``_destruction_first``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import destruction_use, me_powers, threat_tiers
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-ta-destruction-1116.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
TELEPORT_AWAY = "me-power:unbeatable-in-range:teleport-away"
DESTRUCTION = "emergency:destruction:before-teleport-away:absorbed-power"
TARGET = "アイアン・リッチ"


def restored():
    """(policy, snapshot) of the recorded board."""
    raw = CASE["board"]
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    policy.consume_skill_knowledge({"player": {"level": raw["player"]["level"]},   # DECLARED
                                    "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}})
    return policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)


def target(policy, snapshot):
    return next(m for m in policy._physical_hostiles(snapshot) if m.name == TARGET)


class TheRecordingTest(unittest.TestCase):

    def test_live_teleport_away_with_destruction_usable(self):
        self.assertEqual((CASE["decision"]["k"], CASE["decision"]["r"]), ("mCn3", TELEPORT_AWAY))
        self.assertIn("destruction", CASE["decision"]["esc"])
        policy, snapshot = restored()
        monster = target(policy, snapshot)
        self.assertEqual(monster.distance, 1)
        self.assertTrue(threat_tiers.leave_due(policy, snapshot, [monster]))
        self.assertTrue(destruction_use.usable(policy, snapshot, leaving=[monster]))
        self.assertEqual(destruction_use.success(policy, snapshot), 97)


class DestructionFirstTest(unittest.TestCase):

    def test_t3_leave_target_is_destroyed_not_sent_away(self):
        policy, snapshot = restored()
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("mA3", DESTRUCTION))


class DestructionNotUsableTest(unittest.TestCase):

    def test_previous_use_failed_teleport_away_is_cast(self):
        # DECLARED CONSTRUCTED control: the last *Destruction* on this floor failed.
        policy, snapshot = restored()
        setattr(policy, destruction_use.MEMORY,
                destruction_use.Memory(fallback=snapshot.floor_key))
        self.assertEqual((policy.choose_key(snapshot), policy.last_reason), ("mCn3", TELEPORT_AWAY))

    def test_no_destruction_charge_on_50f_recall_comes_first(self):
        # DECLARED CONSTRUCTED control: the absorbed *Destruction* has no charge left.  On 64F
        # the 11-14 rule (destruction_use.means_spent_recall_key, above the emergency layer)
        # reads Recall before either; neither *Destruction* nor the Teleport Away.
        policy, snapshot = restored()
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        emptied = tuple(dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)
        self.assertNotEqual(emptied, rows)
        policy._me_device_lists = dict(lists, staff=(turn, emptied))
        self.assertFalse(destruction_use.usable(policy, snapshot, leaving=[target(policy, snapshot)]))
        self.assertTrue(destruction_use.means_spent(policy, snapshot))
        self.assertEqual((policy.choose_key(snapshot), policy.last_reason),
                         ("rf", destruction_use.MEANS_SPENT_REASON))


class OneTargetSetTest(unittest.TestCase):

    def test_the_trigger_set_is_destructions_leaving(self):
        self.assertEqual(me_powers.DESTRUCTION_FIRST_TRIGGERS, frozenset({"unbeatable-in-range"}))
        self.assertTrue(all("unbeatable-in-range" not in power.triggers or power.effect == "teleport-away"
                            for power in me_powers.POWERS))


if __name__ == "__main__":
    unittest.main()
