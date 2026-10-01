"""Evidence-only pin: supplied incident contradicts the stock-out premise."""
import tests  # noqa: F401 -- runtime isolation
import gzip
import hashlib
import json
from pathlib import Path
import unittest

FIXTURE = Path(__file__).parent / "fixtures/tpstockout-20261002.json.gz"


class TPStockoutRecordedEvidenceTest(unittest.TestCase):
    def test_supplied_capture_has_affordable_teleport_stock(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                         "b926f9a35f727efd003d34524e7d88e7ac1cfc9aaf0ff04f9a3dc04927156b5f")
        capture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        shelf = capture["shelves"]["4"]
        self.assertEqual((shelf["turn"], shelf["store"]["store_type"]), (2570072, 4))
        teleports = [item for item in shelf["store"]["items"]
                     if item["tval"] == 70 and item["sval"] == 9]
        self.assertEqual([(i["letter"], i["name"], i["count"], i["price"])
                          for i in teleports],
                         [("e", "テレポートの巻物", 99, 61),
                          ("f", "テレポートの巻物 {25%引き}", 4, 46)])
        decision = capture["decision"]
        self.assertEqual((decision["decision_sequence"], decision["turn"],
                          decision["reason"], decision["key"]),
                         (37, 2571984, "town:blocked:no-actionable-claim-owner", "5"))
        self.assertEqual(decision["departure_block"]["failed"], ["teleport_ready"])
        self.assertEqual(capture["board"]["player"]["gold"], 10903)
        self.assertEqual(decision["procurement_requirements"],
                         [{"item": "Teleport scrolls", "current": 4, "target": 15, "missing": 11}])
        self.assertEqual(4 * teleports[1]["price"] + 7 * teleports[0]["price"], 611)
        print("TPSTOCKOUT EVIDENCE", [(i["letter"], i["name"], i["count"], i["price"])
                                    for i in teleports], "gold", 10903, "missing cost", 611)


if __name__ == "__main__":
    unittest.main()
