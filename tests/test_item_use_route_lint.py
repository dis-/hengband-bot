"""Lint: every item kind some owner keeps has a registered consumer (item-use-route-1113).

Owner 2026-11-13 「アイテムが整理できていない」: the bot keeps (carries, shelves, buys) only what
a consumer uses.  The kept kinds are the owner's two tables' keep rows (consumable_policy.json
「購入する」「持ち歩く」「自宅に片付ける」「使う」 and the reserves; me_device_policy.json's buy and
absorb rows) and the in-scope kinds the retention authority names (item_use_route.RETENTION_KINDS).
A kept kind needs its own row in item_use_route.ROUTES, or an OWNER_PENDING entry naming the
owner's open question.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from unittest.mock import patch

from hengbot import item_use_route


class ItemUseRouteLintTest(unittest.TestCase):
    def test_every_kept_kind_has_a_consumer(self):
        self.assertEqual(item_use_route.unregistered_kinds(), {})

    def test_a_kept_kind_without_its_row_fails(self):
        remove_curse = (70, 14)
        routes = tuple(route for route in item_use_route.ROUTES
                       if (route.tval, route.sval) != remove_curse)
        with patch.object(item_use_route, "ROUTES", routes):
            self.assertIn(remove_curse, item_use_route.unregistered_kinds())

    def test_every_route_names_a_known_condition(self):
        for route in item_use_route.ROUTES:
            self.assertIn(route.when, item_use_route.WHEN, route)

    def test_departure_supplies_always_have_a_use(self):
        """The departure ledger buys recall, teleport and Cure Critical Wounds by requirement,
        past the registry's purchase gate: their rows hold for every character."""
        for kind in ((70, 11), (70, 9), (75, 36)):
            self.assertIn("always", [route.when for route in item_use_route.rows(*kind)], kind)

    def test_owner_pending_is_not_also_routed(self):
        """A pending kind has no consumer yet; a consumer row ends its question."""
        for kind in item_use_route.OWNER_PENDING:
            self.assertFalse([route for route in item_use_route.ROUTES
                              if (route.tval, route.sval) == kind], kind)


if __name__ == "__main__":
    unittest.main()
