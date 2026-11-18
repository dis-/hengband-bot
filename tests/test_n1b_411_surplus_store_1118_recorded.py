"""A new full-Home relief is not refused by the last one's give-up (n1-b life-411, 2026-11-18 15:52).

Live (n1-b life-411, Magic-Eater Lv50, tests/extract_n1b_411_surplus_store_1118_fixture.py):
over the weight limit with a full Home, the relief skipped every carried ware (see
tests/test_n1b_411_relief_identify_1118_recorded.py) and gave up, leaving the weight to the
surplus producer with ``home_relief_exhausted``.  The next board began a new relief (the
Home still full), which identified the gauntlet (row 31) and chose the shelf's
耐久力の指輪 (+2) for the Magic shop, to be taken from the Home first.  The surplus producer
still read the old give-up and blocked the town (``overweight-home-full-no-legal-relief``),
and that block refused the relief's walk to the Home:
``town:blocked:home-full-surplus-store-unreachable`` on every board (rows 33-56, key ``5``)
until the loop stop.  No store was unreachable.

Now Home's give-up holds only while no relief is open.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import STORE_HOME, STORE_MAGIC
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-411-surplus-store-1118"
RING = (45, 27)


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


class RenewedReliefRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, _journal, steps = load(FIXTURES / "row31", Path(scratch.name))
        cls.recorded = [recorded for recorded, _ in steps]
        replay(steps, policy, 2)
        cls.key = policy.choose_key(steps[2][1]())
        cls.reason = policy.last_reason
        cls.policy = policy

    def test_the_recorded_route_was_blocked(self):
        self.assertEqual({row["reason"] for row in self.recorded[2:]},
                         {"town:blocked:home-full-surplus-store-unreachable"})

    def test_the_new_relief_walks_home_for_its_sale(self):
        # Live: '5' town:blocked:home-full-surplus-store-unreachable.
        self.assertEqual(self.reason, "shop:approach")
        self.assertIsNone(self.policy._town_blocked_reason)
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)
        signature, store_type, _before = self.policy._home_full_relief["sale"]
        self.assertEqual((signature[1:], store_type), (RING, STORE_MAGIC))
        self.assertIsNone(self.policy._overweight_surplus_disposal)


if __name__ == "__main__":
    unittest.main()
