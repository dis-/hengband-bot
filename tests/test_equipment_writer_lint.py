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

    def test_e2_api_calls_and_ability_reads_are_counted(self):
        mutant = """
def store(policy, preparation):
    equipment_target.replace_loadout_target(policy, preparation)
def reset(policy):
    equipment_target.invalidate_loadout_search(policy)
def read(policy):
    return equipment_target.loadout_target(policy)
def resists(snapshot, player):
    return "resist_fire" in snapshot.player.abilities or player.ability_sources.get("x")
def flags():
    return RESIST_FLAG_BY_ABILITY["telepathy"]
"""
        self.assertEqual(dict(analyze_source(mutant)),
                         {"target-store-call": 1, "search-reset-call": 1,
                          "ability-read": 2, "ability-table": 1})
        # A monster's abilities (its spells) are not the character's.
        monster = "def f(knowledge):" + chr(10) + "    return knowledge.abilities" + chr(10)
        self.assertEqual(dict(analyze_source(monster)), {})

    def test_revert_proof_a_direct_read_of_the_old_internals_fails(self):
        with TemporaryDirectory() as raw:
            tree = Path(raw) / "hengbot"
            shutil.copytree(POLICY_ROOT, tree, ignore=shutil.ignore_patterns("__pycache__"))
            self.assertEqual(findings(repository_counts(tree)), [])
            # Undo one routed reader of each API (the pre-E2 source).
            for name, old, new in (
                    ("item_need.py", "equipment_target.loadout_target(policy)",
                     "policy._equipment_optimization_preparation"),
                    # Equipment review E6: the only-source keep read outside item_need.
                    ("item_fate.py", "    if item_need.needed(policy, snapshot, item):\n        return KEEP",
                     "    if ability_sources.sole_depth_source(policy, snapshot, item):\n"
                     "        return KEEP"),
                    ("search_coverage.py", 'not ability_sources.has_ability(snapshot.player, "telepathy")',
                     '"telepathy" not in snapshot.player.abilities'),
                    ("arena_odds.py", "ability_sources.held_ability_flags(snapshot.player)",
                     "frozenset(f for a, f in RESIST_FLAG_BY_ABILITY.items()"
                     " if a in snapshot.player.abilities)")):
                path = tree / name
                text = path.read_text(encoding="utf-8")
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1), encoding="utf-8")
            problems = [problem.split(" -- ")[0] for problem in findings(repository_counts(tree))]
        self.assertEqual(problems, [
            "arena_odds: ability-read 1 > allowed 0",
            "arena_odds: ability-table 1 > allowed 0",
            "item_fate: need-read 1 > allowed 0",
            "item_need: target-read 1 > allowed 0",
            "search_coverage: ability-read 1 > allowed 0",
        ])


if __name__ == "__main__":
    unittest.main()
