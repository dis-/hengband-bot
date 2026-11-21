import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import re
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from equipment_rules_lint import (  # noqa: E402
    POLICY_ROOT, analyze_source, repository_findings,
)

from hengbot import equipment_rules  # noqa: E402


class EquipmentRulesLintTest(unittest.TestCase):
    def test_the_repository_keeps_the_rules_in_one_table(self):
        self.assertEqual(repository_findings(), [])

    def test_each_kind_of_copy_is_found(self):
        mutant = """
TR_NO_AC = 141
SHOT_POWER_FLOOR = 100.0
def launcher_is_high_grade(item):
    return item.pseudo_feeling in {"excellent", "special"}
def armor(flags):
    return 0 if 141 in flags else 1
SEEN = frozenset({134, 7})
"""
        found = [finding.split(" -- ")[0] for finding in analyze_source(mutant, "mutant")]
        self.assertEqual(found, [
            "mutant:2: definition of TR_NO_AC",
            "mutant:3: definition of SHOT_POWER_FLOOR",
            "mutant:4: definition of launcher_is_high_grade",
            "mutant:5: grade-literal",
            "mutant:7: flag-literal 141",
            "mutant:8: flag-literal 134",
        ])

    def test_the_depth_table_stays_in_policy_constants(self):
        source = "DEPTH_ABILITY_REQUIREMENTS = ()\ndef _required_abilities_for_depth(depth):\n    return 0\n"
        self.assertEqual(analyze_source(source, "policy_constants"), [])
        self.assertEqual(len(analyze_source(source, "policy_town")), 2)

    def test_the_search_keys_read_the_version(self):
        self.assertEqual(analyze_source('KEY = {"schema": 4}\n', "warrior_optimization"),
                         ["warrior_optimization: version -- the search key does not read "
                          "equipment_rules.RULES_VERSION (a hand-bumped schema goes stale)"])

    def test_revert_proof_the_former_copies_fail(self):
        """Put back E1's removed copies (TR_NO_AC in warrior_optimization, the robe ban's literal
        in character_sheet, the schema by hand): the lint names each."""
        with TemporaryDirectory() as raw:
            tree = Path(raw) / "hengbot"
            shutil.copytree(POLICY_ROOT, tree, ignore=shutil.ignore_patterns("__pycache__"))
            self.assertEqual(repository_findings(tree), [])
            optimization = tree / "warrior_optimization.py"
            source = optimization.read_text(encoding="utf-8")
            self.assertIn('"schema": equipment_rules.RULES_VERSION,', source)
            optimization.write_text(
                source.replace('"schema": equipment_rules.RULES_VERSION,', '"schema": 4,')
                + "\n\nTR_NO_AC = 141\n", encoding="utf-8")
            sheet = tree / "character_sheet.py"
            source = sheet.read_text(encoding="utf-8")
            self.assertIn("0 if TR_NO_AC in worn.flags", source)
            sheet.write_text(source.replace("0 if TR_NO_AC in worn.flags", "0 if 141 in worn.flags"),
                             encoding="utf-8")
            problems = [re.sub(r":\d+:", ":", finding.split(" -- ")[0])
                        for finding in repository_findings(tree)]
        self.assertEqual(problems, ["character_sheet: flag-literal 141",
                                    "warrior_optimization: definition of TR_NO_AC",
                                    "warrior_optimization: version"])


class EquipmentRulesVersionTest(unittest.TestCase):
    def test_the_version_is_the_tables_digest(self):
        table = equipment_rules._rules_table()
        self.assertEqual(equipment_rules.RULES_VERSION, equipment_rules.rules_version(table))
        self.assertEqual(table["loadout_banned_flags"], [equipment_rules.TR_NO_AC])
        self.assertEqual(table["revision"], 4)

    def test_changing_a_rule_changes_the_version(self):
        table = equipment_rules._rules_table()
        for name, value in (("loadout_banned_flags", [134, 141]), ("revision", 5),
                            ("unscored_launcher", [16, 50, 90.0]),
                            ("yields_to_light_crossbow_svals", [2, 12, 13])):
            with self.subTest(name):
                self.assertNotEqual(equipment_rules.rules_version({**table, name: value}),
                                    equipment_rules.RULES_VERSION)


if __name__ == "__main__":
    unittest.main()
