"""Read-only mutation check: load the actual base methods into this process.

No files are reverted, no other worktree is created, and no bot is run.
"""
import tests  # noqa: F401
import ast
import subprocess
import unittest

import hengbot.policy_supply as supply
from test_manafood_departure_recorded import ManafoodRecordedTest


def main():
    base = subprocess.check_output([
        'git', 'show', '96c20795:src/hengbot/policy_supply.py'
    ]).decode('utf8')
    klass = next(node for node in ast.parse(base).body
                 if isinstance(node, ast.ClassDef) and node.name == 'SupplyMixin')
    names = {'_count_mana_food_uses', '_count_mana_food_devices',
             '_mana_food_survival_override_key'}
    for node in klass.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            namespace = dict(vars(supply))
            tree = ast.Module(body=[node], type_ignores=[])
            exec(compile(tree, '<actual-base-method>', 'exec'), namespace)
            setattr(supply.SupplyMixin, node.name, namespace[node.name])
    suite = unittest.TestSuite(ManafoodRecordedTest(name) for name in (
        'test_recorded_recovery_reads_recall',
        'test_recorded_recovery_public_decision_after_observed_skills',
        'test_recorded_departure_home_stock_cannot_satisfy_food_leaf',
    ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert len(result.failures) == 3 and not result.errors
    print('REVERT-PROOF: actual base methods fail all 3 defect pins.')


if __name__ == '__main__':
    main()
