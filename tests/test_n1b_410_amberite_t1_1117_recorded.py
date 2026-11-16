"""Without resist curse every Amberite is read T1 by the threat tiers, recorded.

Owner 2026-11-17 (verbatim): 「呪力耐性がないときは王族をT1扱いにする。行動はT1の処理に準じる。」
amberite_curse.t1_amberites, asked by threat_projection ``_tier`` (the one place a tier is
assigned), makes an engagement with an Amberite T1 whatever the projection; the T1 rules answer.

Recorded: tests/fixtures/n1b-410-amberite-1117.pkl.xz (tests/extract_n1b_410_amberite_1117_fixture.py),
n1-b life-410's 80F board of decision #17762: アンバーの狂気の夢想家『ブランド』 awake two cells away,
a sleeping グレート・ドラコリスク three away, no resist_curse.  Live the projection read the
engagement T3 and the bot fired the Rocket ``mB39`` that led to the fatal kill on #17763.

DECLARED CONSTRUCTED (each test says which): Brand asleep; Brand removed from view and shown as a
detected monster at (5, 60), game distance 10 (a known floor cell), awake or asleep;
``resist_curse`` added to the player's abilities.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import amberite_curse, destruction_use, threat_tiers
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-410-amberite-1117.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
BRAND = 773
SENSED_AT = (5, 60)


def restored(*, asleep=None, sensed=False, curse=False):
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])
    board = copy.deepcopy(CASE["board"])
    if curse:
        board["player"]["ability_sources"]["resist_curse"] = {
            "equipment": True, "permanent": False, "temporary": False}
    shown = next(m for m in board["visible_monsters"] if m["race_id"] == BRAND)
    if asleep is not None:
        shown["asleep"] = asleep
    if sensed:
        board["visible_monsters"].remove(shown)
        board.setdefault("detected_monsters", []).append(
            dict(shown, y=SENSED_AT[0], x=SENSED_AT[1]))
    return policy, parse_snapshot(board, policy._monrace_knowledge)


def brand(snapshot):
    return next(m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                if m.race_id == BRAND)


class AmberiteT1Test(unittest.TestCase):

    def test_brand_is_t1_on_the_recorded_board(self):
        policy, snapshot = restored()
        engagement = threat_tiers.engagement(policy, snapshot)
        reading = threat_tiers.assess(policy, snapshot, engagement)
        self.assertEqual(reading.tier, threat_tiers.T1)
        self.assertEqual(reading.amberite_t1, (brand(snapshot).index,))
        alone = threat_tiers.assess(policy, snapshot, [brand(snapshot)], contact=True)
        self.assertEqual(alone.tier, threat_tiers.T1)

    def test_the_t1_rules_answer_instead_of_the_rocket(self):
        policy, snapshot = restored()
        key = policy.choose_key(snapshot)
        self.assertNotEqual(key, CASE["decision"]["key"])
        self.assertTrue(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_sleeping_brand_is_t1_and_left(self):
        """CONSTRUCTED: Brand asleep: the T1 leave from a strong sleeper (owner 2026-11-07)."""
        policy, snapshot = restored(asleep=True)
        self.assertEqual(threat_tiers.assess(policy, snapshot, [brand(snapshot)]).tier,
                         threat_tiers.T1)
        key = policy.choose_key(snapshot)
        self.assertEqual(policy.last_reason, "flee")
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_sensed_awake_brand_is_destroyed(self):
        """CONSTRUCTED: Brand known by detection alone, awake, ten cells off."""
        policy, snapshot = restored(asleep=False, sensed=True)
        self.assertNotIn(BRAND, [m.race_id for m in snapshot.visible_monsters])
        reading = threat_tiers.assess(policy, snapshot, threat_tiers.engagement(policy, snapshot))
        self.assertEqual(reading.tier, threat_tiers.T1)
        key = policy.choose_key(snapshot)
        self.assertTrue(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_sensed_sleeping_brand_reads_t1(self):
        """CONSTRUCTED: detected alone and asleep.  The engagement (design 3) takes only the awake
        detected monsters, so it is left asleep, as every sensed sleeping T1 is; read on its own
        it is T1."""
        policy, snapshot = restored(asleep=True, sensed=True)
        self.assertNotIn(brand(snapshot).index,
                         [m.index for m in threat_tiers.engagement(policy, snapshot)])
        self.assertEqual(threat_tiers.assess(policy, snapshot, [brand(snapshot)], contact=True).tier,
                         threat_tiers.T1)

    def test_resist_curse_reads_the_projection(self):
        """CONSTRUCTED: resist_curse worn: no forced T1 (the projection's T3 here)."""
        policy, snapshot = restored(curse=True)
        reading = threat_tiers.assess(policy, snapshot, threat_tiers.engagement(policy, snapshot))
        self.assertEqual(reading.amberite_t1, ())
        self.assertEqual(reading.tier, threat_tiers.T3)


if __name__ == "__main__":
    unittest.main()
