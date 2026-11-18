"""A full Home's relief awaits its ID only once posted (n1-b life-411, 2026-11-18 15:52).

Live (n1-b life-411, Magic-Eater Lv50, tests/extract_n1b_411_surplus_store_1118_fixture.py):
back from the Castle over the weight limit (2120 of 1950) with a full Home (240/240), the
full-Home relief sold three carried devices at the Magic shop (rows 6-21), then chose the
carried unidentified ガントレット [2] to identify (row 22).  Two readers decided that board:
``_decide`` offered the relief's ID (``mAfn``) and armed its watch, then the closing-
equipment weight transition (``_town_procurement_decision``) asked the relief again, which
found the watch armed with no ID posted and skipped the ware
(``home:full-skip:identification-effect-unresolved``).  The same happened to each carried
ware in turn (rows 22-30) until the relief gave up (see
tests/test_n1b_411_surplus_store_1118_recorded.py for what followed).

Now the offered ID is pending and confirm_key_posted arms the watch, as the relief's
destroy already did; a key that replaced it (the entrance step-off) leaves it to be
offered again.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-411-surplus-store-1118"
ID_ROW = 22
GAUNTLET = (31, 2)


def post(policy, key):
    policy.confirm_key_posted(key)
    chain = policy.peek_staged_prompt_chain()
    if chain is not None and staged_prompt_chain_matches(chain, key):
        policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def replay(steps, policy, rows):
    """Decide and post ``rows`` recorded boards, each matching the journal."""
    for recorded, supply in steps[:rows]:
        key = policy.choose_key(supply())
        assert (key, policy.last_reason) == (recorded["key"], recorded["reason"]), recorded
        if key:
            post(policy, key)


class ReliefIdentificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURES / "arrival", Path(scratch.name))
        cls.recorded = [recorded for recorded, _ in steps]
        replay(steps, policy, ID_ROW)
        cls.key = policy.choose_key(steps[ID_ROW][1]())
        cls.reason = policy.last_reason
        cls.relief = copy.deepcopy(policy._home_full_relief)
        cls.offered = copy.deepcopy(policy)
        # Live, the CLI posted the entrance step-off ``7`` on this board.
        post(policy, cls.recorded[ID_ROW]["key"])
        cls.rewritten_relief = copy.deepcopy(policy._home_full_relief)
        cls.next_key = policy.choose_key(steps[ID_ROW + 1][1]())
        cls.next_reason = policy.last_reason

    def test_the_recorded_relief_skipped_its_offered_id(self):
        self.assertEqual(self.recorded[ID_ROW]["reason"],
                         "town:entrance-step-off:home:full-skip:identification-effect-unresolved")
        self.assertEqual({row["reason"] for row in self.recorded[ID_ROW + 1:31]},
                         {"home:full-skip:identification-effect-unresolved"})

    def test_the_relief_identifies_the_gauntlet(self):
        # Live: '7' town:entrance-step-off:home:full-skip:identification-effect-unresolved.
        self.assertEqual((self.key, self.reason), ("mAfn", "identify:normal"))
        self.assertEqual(self.relief["sale"][0][1:], GAUNTLET)
        self.assertNotIn("skipped", self.relief)
        self.assertNotIn("identifying", self.relief)

    def test_the_posted_id_arms_its_watch(self):
        policy = copy.deepcopy(self.offered)
        post(policy, self.key)
        self.assertEqual(policy._home_full_relief["identifying"][0], GAUNTLET[0])
        self.assertNotIn("identify_pending", policy._home_full_relief)

    def test_a_rewritten_id_is_offered_again(self):
        self.assertNotIn("identifying", self.rewritten_relief)
        self.assertNotIn("identify_pending", self.rewritten_relief)
        # Live: '5' home:full-skip:identification-effect-unresolved (the dagger next).
        self.assertEqual((self.next_key, self.next_reason), ("mAfn", "identify:normal"))


if __name__ == "__main__":
    unittest.main()
