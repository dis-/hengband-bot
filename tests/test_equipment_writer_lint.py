import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from equipment_writer_lint import (  # noqa: E402
    ALLOWED, POLICY_ROOT, analyze_source, findings, repository_counts,
)


class EquipmentWriterLintTest(unittest.TestCase):
    def test_the_repository_matches_its_pins(self):
        self.assertEqual(findings(repository_counts()), [])

    def test_each_kind_of_direct_writer_is_counted(self):
        mutant = """
def wear(policy, snapshot, item):
    return policy._equipment_wield(snapshot, "mine", item, "light")
def strip(policy, snapshot, item):
    return reserved_item_command(policy, snapshot, "takeoff", item)
def reset(policy):
    policy._equipment_optimization_signature = None
def peek(policy):
    return policy._equipment_optimization_preparation.result
def peek_by_name(policy):
    return getattr(policy, "_equipment_optimization_preparation")
"""
        self.assertEqual(dict(analyze_source(mutant)),
                         {"wear-exit": 1, "wear-command": 1, "search-reset": 1,
                          "target-read": 1, "target-name": 1})

    def test_revert_proof_a_new_writer_in_the_tree_fails(self):
        with TemporaryDirectory() as raw:
            tree = Path(raw) / "hengbot"
            shutil.copytree(POLICY_ROOT, tree, ignore=shutil.ignore_patterns("__pycache__"))
            self.assertEqual(findings(repository_counts(tree)), [])
            # A new direct wear in an allowed module, and a new module that forces a re-search.
            with (tree / "policy_town.py").open("a", encoding="utf-8") as stream:
                stream.write("\n\ndef _e0_mutant(policy, snapshot, item):\n"
                             "    return policy._equipment_wield(snapshot, 'mutant', item, 'light')\n")
            (tree / "e0_mutant.py").write_text(
                "def reset(policy):\n    policy._equipment_optimization_signature = None\n",
                encoding="utf-8")
            problems = findings(repository_counts(tree))
        allowed = ALLOWED["policy_town"]["wear-exit"]
        self.assertEqual(problems[0].split(" -- ")[0], "e0_mutant: search-reset 1 > allowed 0")
        self.assertEqual(problems[1].split(" -- ")[0],
                         f"policy_town: wear-exit {allowed + 1} > allowed {allowed}")
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
