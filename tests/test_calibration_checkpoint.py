import tests  # noqa: F401
import json
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_calibration import LegacyCalibrationDebtError, refuse_legacy_calibration_debt


class CalibrationCheckpointTest(unittest.TestCase):
    def test_empty_upgrade_has_exact_fresh_key_set_and_is_idempotent(self):
        fresh = HengbotPolicy(monrace_knowledge={})
        restored = HengbotPolicy.__new__(HengbotPolicy)
        normalize_policy_state(restored)
        self.assertEqual(set(vars(restored)), set(vars(fresh)))
        before = pickle.dumps(restored)
        normalize_policy_state(restored)
        self.assertEqual(pickle.dumps(restored), before)
        self.assertEqual(set(vars(pickle.loads(before))), set(vars(fresh)))

    def test_each_old_debt_is_named_and_never_executed(self):
        for name, value in (("_calibration_phase", "deposit"),
                            ("_calibration_suspended_phase", "strip"),
                            ("_calibration_stripped_unrestored", True),
                            ("_calibration_restore_signatures", [("oil", 77, 0)])):
            with self.subTest(name=name), self.assertRaisesRegex(LegacyCalibrationDebtError, name):
                refuse_legacy_calibration_debt({name: value})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            original = json.dumps({"redress_obligation": [["body", "identity"]]})
            path.write_text(original)
            with self.assertRaisesRegex(LegacyCalibrationDebtError, "redress_obligation"):
                refuse_legacy_calibration_debt({}, path)
            self.assertEqual(path.read_text(), original)
