import subprocess, sys
from pathlib import Path
case = sys.argv[1]
if case == "continuation":
    target = Path("src/hengbot/policy_calibration.py")
    old = target.read_bytes()
    changed = old.replace(b'continuation="calibration.capture.observe",', b'continuation="calibration.restore",', 1)
    pin = "Live9CalibrationTest.test_recorded_dump_continues_capture_and_restore_after_checkpoint"
elif case == "dispatch":
    target = Path("src/hengbot/policy.py")
    old = target.read_bytes()
    changed = old.replace(b'holder is not None and holder.owner.value == "calibration"', b'False and holder is not None and holder.owner.value == "calibration"', 1)
    pin = "Live9CalibrationTest.test_recorded_dump_continues_capture_and_restore_after_checkpoint"
elif case == "absent":
    target = Path("src/hengbot/policy_home.py")
    old = target.read_bytes()
    changed = old.replace(b'signature in self._calibration_restore_signatures\n                and getattr(self, "_crossarea_fundraising_enforced", False)', b'signature in self._calibration_restore_signatures\n                and False', 1)
    pin = "Live8RestoreTest.test_completed_empty_home_scan_keeps_absent_restore_debt_and_typed_stop"
else:
    raise ValueError(case)
assert changed != old
try:
    target.write_bytes(changed)
    result = subprocess.run([sys.executable, "-m", "unittest", "tests.test_live8." + pin])
    if result.returncode == 0:
        raise SystemExit("revert survived")
    print("SINGLE_REVERT_KILLED", case)
finally:
    target.write_bytes(old)
