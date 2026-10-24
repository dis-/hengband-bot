"""ROOT-FIX S2 (c): refusal servers name the town needs that serve them.

Design 3.4 (plans/DESIGN-town-claim-rootfix-1023.md): the right side of
``REFUSAL_SERVERS`` is ``Server(family, category | None)`` and a category is a
name of ``_town_need_registry``.  S1 left the identification, pack-space and
overweight rows without the categories of the design table; these are the
registry names of that table.
"""

import tests  # noqa: F401

import unittest

from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import REFUSAL_SERVERS, Server


class RefusalServerCategoryTest(unittest.TestCase):
    def test_design_table_rows_carry_registry_categories(self):
        self.assertEqual(REFUSAL_SERVERS["identification-flow"], (
            Server("identification"), Server("cross-town"),
            Server("home-errand", "identification-withdrawal"),
            Server("shop-buy", "identification-source"),
        ))
        space = (
            Server("home-visit", "space-deposit"),
            Server("shop-sell", "organization-sale"),
            Server("town-plan"),
        )
        self.assertEqual(REFUSAL_SERVERS["pack-space"], space)
        self.assertEqual(REFUSAL_SERVERS["pack-space-required:*"], space)
        self.assertEqual(REFUSAL_SERVERS["overweight"], (
            Server("shop-sell", "overweight-surplus"),
            Server("home-visit", "weight-overload"),
        ))

    def test_named_categories_are_registry_names(self):
        categories = {spec.category for spec in HengbotPolicy()._town_need_registry()}
        named = {server.category for servers in REFUSAL_SERVERS.values()
                 for server in servers if server.category is not None}
        self.assertIn("identification-withdrawal", named)
        self.assertLessEqual(named, categories)


if __name__ == "__main__":
    unittest.main()
