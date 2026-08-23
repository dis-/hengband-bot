import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "owner_map.py"
POLICY = ROOT / "src" / "hengbot"


def load_owner_map():
    spec = importlib.util.spec_from_file_location("owner_map", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OwnerMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_owner_map()
        cls.report = cls.module.build_report(POLICY)

    def test_reason_inventory_covers_known_static_and_dynamic_sites(self):
        reasons = self.report["reasons"]
        self.assertGreaterEqual(len(reasons), 400)
        static_reasons = {site["reason"] for site in reasons}
        self.assertIn("home:request-knowledge-scan", static_reasons)
        self.assertIn("opening-q34:rearm", static_reasons)
        self.assertTrue(any(site["reason"] == "<dynamic>" and site["skeleton"] for site in reasons))

    def test_home_knowledge_has_expected_truthy_producer_and_consumers(self):
        fact = self.report["facts"]["_home_knowledge_current"]
        truthy_producers = {
            site["function"] for site in fact["writes"] if site["truthiness"] is True
        }
        self.assertEqual(truthy_producers, {"consume_home_knowledge"})
        self.assertIn("_atomic_home_withdraw_key", fact["consumer_functions"])
        self.assertIn("_resolve_observed_uncomposable_stop", fact["consumer_functions"])

    def test_named_watch_and_queue_facts_have_producers_and_consumers(self):
        expected = {
            "_emergency_consumable_issue_watch": {"_issue_emergency_consumable"},
            "_dungeon_recall_issue_watch": {"_read_dungeon_recall_scroll_key"},
        }
        for name, producer_subset in expected.items():
            with self.subTest(fact=name):
                fact = self.report["facts"][name]
                self.assertTrue(fact["producer_functions"])
                self.assertTrue(fact["consumer_functions"])
                self.assertTrue(producer_subset <= set(fact["producer_functions"]))

    def test_starvation_report_contains_home_knowledge(self):
        starvation = {item["fact"]: item for item in self.report["starvation_prone"]}
        self.assertIn("_home_knowledge_current", starvation)
        self.assertEqual(starvation["_home_knowledge_current"]["producer"], "consume_home_knowledge")
        ordering = [(-item["consumer_count"], item["fact"]) for item in self.report["starvation_prone"]]
        self.assertEqual(ordering, sorted(ordering))

    def test_literal_and_dynamic_getattr_setattr_are_counted(self):
        source = """\
class Example:
    def inspect(self, name):
        self._direct = getattr(self, '_literal')
        setattr(self, '_literal', True)
        getattr(self, name)
        setattr(self, name, False)
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            path.write_text(source, encoding="utf-8")
            report = self.module.build_report(path)
        self.assertEqual(report["facts"]["_literal"]["producer_functions"], ["inspect"])
        self.assertEqual(report["facts"]["_literal"]["consumer_functions"], ["inspect"])
        self.assertEqual(len(report["facts"]["<dynamic>"]["writes"]), 1)
        self.assertEqual(len(report["facts"]["<dynamic>"]["reads"]), 1)

    def test_json_and_markdown_outputs_are_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            outputs = []
            for run in range(2):
                json_path = directory / f"map-{run}.json"
                markdown_path = directory / f"map-{run}.md"
                subprocess.run(
                    [sys.executable, str(SCRIPT), "--json", str(json_path), "--markdown", str(markdown_path)],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                outputs.append((json_path.read_bytes(), markdown_path.read_bytes()))
            self.assertEqual(outputs[0], outputs[1])
            parsed = json.loads(outputs[0][0])
            self.assertEqual(parsed["facts"]["_home_knowledge_current"]["producer_functions"], self.report["facts"]["_home_knowledge_current"]["producer_functions"])


if __name__ == "__main__":
    unittest.main()
