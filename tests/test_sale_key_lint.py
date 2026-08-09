import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sale_key_lint import POLICY, analyze_source  # noqa: E402


class SaleKeyLintTest(unittest.TestCase):
    def test_repository_sale_keys_are_inscription_bound(self):
        self.assertEqual(analyze_source(POLICY.read_text(encoding="utf-8")), [])

    def test_item_letter_sale_mutant_is_rejected(self):
        mutant = """
SELL_KEY = 'd'
def _store_sell_key(item):
    return SELL_KEY + item.slot + '\\r'
"""
        findings = analyze_source(mutant)
        self.assertTrue(any("item letter" in finding for finding in findings))
        self.assertTrue(any("observation gate" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
