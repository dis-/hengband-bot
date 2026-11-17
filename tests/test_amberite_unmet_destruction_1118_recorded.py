"""With resist curse and the kill's conditions unmet, an Amberite is the no-resist one, recorded.

Owner 2026-11-18 (the chosen answer, verbatim): 「条件がそろうまで *破壊* で消す」 --
「呪力耐性があっても条件がそろわない間は、耐性が無い時と同じく T1 として扱い、*破壊* で消す（届かな
ければ近寄る・無理なら離れる）。条件がそろえば今のとおり加速と耐性の薬の後に倒す。」
amberite_curse.t1_amberites asks ``refusal`` (the one reader of the conditions) for each Amberite;
the gate's kept-alive answer for those verdicts is the no-resist one (*Destruction*).

Recorded: tests/fixtures/n1b-410-amberite-1117.pkl.xz (tests/extract_n1b_410_amberite_1117_fixture.py),
n1-b life-410's Angband 80F boards #17762 (アンバーの狂気の夢想家『ブランド』 awake two cells off, a
sleeping グレート・ドラコリスク three off) and #17763 (the dracolisk awake), HP 1153/1153, hasted,
the absorbed *Destruction* at 98%.

DECLARED CONSTRUCTED (each test says which): ``resist_curse`` added to the player's abilities and
the status bar given the five Resistance elements (every test: the resist-curse path, prepared);
the HP lowered to 500 (below the low-HP line); the absorbed *Destruction*'s charges emptied with
the player recalling (no means); #17763's dracolisk put back to sleep (the conditions met again on
the same board).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import amberite_curse, destruction_use, threat_tiers
from hengbot.model import parse_snapshot
from tests.test_n1b_410_amberite_curse_1117_recorded import BAR, CASE, RESIST_CURSE, restored

BRAND = 773
DRACOLISK = 1242


def brand(snapshot):
    return next(m for m in snapshot.visible_monsters if m.race_id == BRAND)


def reading(policy, snapshot):
    return threat_tiers.assess(policy, snapshot, threat_tiers.engagement(policy, snapshot))


def met_board(policy):
    """CONSTRUCTED: #17763 as ``restored("next_board", curse, bar, no_destruction)`` builds it,
    with the dracolisk asleep again."""
    board = copy.deepcopy(CASE["next_board"])
    player = board["player"]
    player["ability_sources"]["resist_curse"] = dict(RESIST_CURSE)
    player["status_bar"] = copy.deepcopy(BAR)
    player["recalling"] = True
    next(m for m in board["visible_monsters"] if m["race_id"] == DRACOLISK)["asleep"] = True
    return parse_snapshot(board, policy._monrace_knowledge)


class UnmetIsT1Test(unittest.TestCase):

    def test_other_awake_reads_t1(self):
        """#17763 (the dracolisk awake), resist curse: T1 as without it (was T3)."""
        policy, snapshot = restored("next_board", curse=True, bar=True)
        self.assertTrue(amberite_curse.resists_curse(snapshot))
        self.assertEqual(amberite_curse.refusal(policy, snapshot, [brand(snapshot)]),
                         amberite_curse.OTHER_AWAKE)
        result = reading(policy, snapshot)
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertEqual(result.amberite_t1, (brand(snapshot).index,))

    def test_other_awake_destruction(self):
        """#17763, resist curse: the T1 rules' *Destruction* (was threat:avoid-engagement)."""
        policy, snapshot = restored("next_board", curse=True, bar=True)
        key = policy.choose_key(snapshot)
        self.assertTrue(policy.last_reason.startswith(destruction_use.REASON), policy.last_reason)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])

    def test_low_hp_reads_t1(self):
        """CONSTRUCTED: #17762 at HP 500: T1 for the low HP (amberite_t1 was ())."""
        policy, snapshot = restored(curse=True, bar=True, hp=500)
        self.assertEqual(amberite_curse.refusal(policy, snapshot, [brand(snapshot)]),
                         amberite_curse.HP_LOW)
        result = reading(policy, snapshot)
        self.assertEqual((result.tier, result.amberite_t1),
                         (threat_tiers.T1, (brand(snapshot).index,)))

    def test_the_gate_uses_destruction_for_an_unmet_strike(self):
        """The gate alone with the recorded Rocket on #17763: *Destruction* on Brand, as
        without resist curse (was the engagement retreat)."""
        policy, snapshot = restored("next_board", curse=True, bar=True)
        policy.last_reason = CASE["decision"]["reason"]
        key = amberite_curse.after_ladder(policy, snapshot, CASE["decision"]["key"])
        self.assertTrue(policy.last_reason.startswith(
            destruction_use.REASON + amberite_curse.SIGHT_SUFFIX), policy.last_reason)
        self.assertEqual(amberite_curse.struck(policy, snapshot, key), [])
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.OTHER_AWAKE)


class MetIsKilledTest(unittest.TestCase):

    def test_met_conditions_keep_the_prepared_kill(self):
        """#17762 (the dracolisk asleep), resist curse, prepared: not T1, the Rocket is sent."""
        policy, snapshot = restored(curse=True, bar=True)
        self.assertIsNone(amberite_curse.refusal(policy, snapshot, [brand(snapshot)]))
        self.assertEqual(reading(policy, snapshot).amberite_t1, ())
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason),
                         (CASE["decision"]["key"], CASE["decision"]["reason"]))
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.PERMITTED)

    def test_fresh_met_board_strikes(self):
        """CONSTRUCTED: the met board below read with no unmet board before it: the kill."""
        policy, _ = restored("next_board", curse=True, bar=True, no_destruction=True)
        met = met_board(policy)
        self.assertEqual(reading(policy, met).amberite_t1, ())
        key = policy.choose_key(met)
        self.assertEqual(amberite_curse.report(policy)["verdict"], amberite_curse.PERMITTED)
        self.assertEqual(key, CASE["decision"]["key"])


class NoFlipTest(unittest.TestCase):
    """CONSTRUCTED: no *Destruction* (charges emptied, recalling), so the unmet board leaves
    instead of deleting Brand; the next board (#17763 with the dracolisk asleep again) reads the
    conditions met.  The decided side (threat_tier_memory ``held_tier``) holds the engagement's
    T1 while the projection is inside the band: the leave goes on, no strike is sent."""

    def test_the_leave_is_held_when_the_conditions_come_back(self):
        policy, unmet = restored("next_board", curse=True, bar=True, no_destruction=True)
        first = policy.choose_key(unmet)
        self.assertEqual(policy.last_reason, "no-wait:flee")
        self.assertEqual(amberite_curse.struck(policy, unmet, first), [])
        met = met_board(policy)
        self.assertIsNone(amberite_curse.refusal(policy, met, [brand(met)]))
        raw = reading(policy, met)
        self.assertEqual((raw.tier, raw.amberite_t1), (threat_tiers.T3, ()))
        held = threat_tiers.tiered(policy, met, threat_tiers.engagement(policy, met))
        self.assertEqual(held.tier, threat_tiers.T1)
        second = policy.choose_key(met)
        self.assertEqual(policy.last_reason, "no-wait:flee")
        self.assertEqual(amberite_curse.struck(policy, met, second), [])


if __name__ == "__main__":
    unittest.main()
