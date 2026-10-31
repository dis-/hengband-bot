"""Sale knowledge names match the game's names without trailing spaces.

Game develop 664240d477 removed the trailing space of 「チーターマン『アリエス』 」,
「『死神ももえ』 」 and "The Orb of Fate " (lib/edit), which
store_sale_knowledge.json still carries.  The public valuation must still
find those identities in the names the game now prints.

DECLARED CONSTRUCTED: the items (names as the game prints a statue of the
monster and the artifact light; tval/sval from the knowledge rows).
"""
import tests  # noqa: F401 -- isolate live runtime files

import unittest

from policy_fixtures import item
from hengbot import store_sale


class StrippedSaleNamesTest(unittest.TestCase):
    def test_monster_names_lost_their_trailing_space(self):
        for name, level in (("『死神ももえ』の像", 78), ("チーターマン『アリエス』の像", 11)):
            with self.subTest(name=name):
                statue = item("a", 8, 0, aware=False, known=False, name=name)
                race = store_sale.sale_monrace(statue)
                self.assertIsNotNone(race)
                self.assertEqual(race["level"], level)
                self.assertEqual(store_sale.known_sale_value(statue, None), None)
                self.assertTrue(store_sale.has_positive_sale_value(statue, None))

    def test_fixed_artifact_name_lost_its_trailing_space(self):
        orb = item("a", 39, 10, known=True, fully_known=True, is_artifact=True,
                   name="The Orb of Fate")
        self.assertEqual(store_sale.known_sale_value(orb, None), 45000)


if __name__ == "__main__":
    unittest.main()
