"""Revert one production seam in memory, running one authorized pin."""
import ast
import importlib
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CASES = {
    "calibration": ("hengbot.policy_home", "HomeMixin", "_plan_calibration_supply_restore",
                    "tests.test_calibration_live25.Live25CalibrationTest.test_full_owed_restore_at_limit_and_one_over_after_checkpoint"),
    "alternation": ("hengbot.policy_home", "HomeMixin", "_weight_deposit_candidates",
                    "tests.test_home_withdraw_deposit_alternation_recorded.HomeWithdrawDepositAlternationRecordedTest.test_first_divergence_preserves_identification_then_clears_weight"),
    "home": ("hengbot.input_executor", "OperationExecutor", "submit",
             "tests.test_equipment_in_home_stage1.EquipmentInHomeBehaviorPins.test_h1_incident_finishes_with_one_exit_and_zero_reentries"),
}
module_name, class_name, method, pin = CASES[sys.argv[1]]
module = importlib.import_module(module_name)
source = subprocess.check_output(["git", "show", f"a4e51bf9:src/{module_name.replace('.', '/')}.py"], encoding="utf8")
tree = ast.parse(source)
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method)
namespace = dict(vars(module))
exec(compile(ast.Module(body=[node], type_ignores=[]), "a4e51bf9:" + method, "exec"), namespace)
with patch.object(getattr(module, class_name), method, namespace[method]):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(pin))
detected = bool(result.failures) and not result.errors
print("REVERT", sys.argv[1], "detected", detected)
raise SystemExit(not detected)
