"""Census: the light questions are answered through one judgment (#47).

The single structural check the light and fuel ROOT-FIX allows.  Each
enumerated site (LUNA-DIAG-light-rootfix.txt) that answers "is the light
faint", "may this trip go" or "may the one-shot quest lock open" must call
``_light_judgment``, and the faint value LANTERN_DIM_WARNING_FUEL may appear
only inside the judgment and the one listed exception.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import ast
import unittest
from pathlib import Path

POLICY_ROOT = Path(__file__).resolve().parents[1] / "src" / "hengbot"

# (file, function) sites that must ask the judgment.
ROUTED_SITES = {
    ("policy_supply.py", "_expedition_light_ready"),
    ("policy_town.py", "_return_exit_locked"),
    ("policy_quest.py", "_evaluate_fixed_quest_readiness"),
    ("policy.py", "_decide"),
}
# Functions allowed to name the faint value.  _unknown_light_last_resort
# compares ``fuel > 100`` (inclusive at 100) for the unknown-light fallback;
# folding it in would change which light is wielded at exactly 100.
FAINT_VALUE_OWNERS = {
    ("policy_supply.py", "_light_judgment"),
    ("policy_supply.py", "_unknown_light_last_resort"),
}


def _functions():
    for path in sorted(POLICY_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield path.name, node


def _calls_judgment(node):
    return any(
        isinstance(sub, ast.Attribute) and sub.attr == "_light_judgment"
        for sub in ast.walk(node)
    )


def _names_faint_value(node):
    return any(
        isinstance(sub, ast.Name) and sub.id == "LANTERN_DIM_WARNING_FUEL"
        for sub in ast.walk(node)
    )


class LightJudgmentCensusTest(unittest.TestCase):
    def test_enumerated_sites_ask_the_light_judgment(self):
        found = {
            (name, node.name): _calls_judgment(node)
            for name, node in _functions()
            if (name, node.name) in ROUTED_SITES
        }
        self.assertEqual(set(found), ROUTED_SITES)
        self.assertEqual(
            sorted(site for site, routed in found.items() if not routed), []
        )

    def test_faint_value_is_named_only_by_the_judgment(self):
        owners = set()
        for name, node in _functions():
            # Nested functions are counted with their enclosing definition.
            if _names_faint_value(node) and not any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _names_faint_value(child)
                for child in ast.walk(node)
                if child is not node
            ):
                owners.add((name, node.name))
        self.assertEqual(owners, FAINT_VALUE_OWNERS)


if __name__ == "__main__":
    unittest.main()
