from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
files = [root / "src/hengbot" / name for name in (
    "policy.py", "policy_calibration.py", "policy_equipment.py", "policy_home.py")]
fixed = {path: path.read_bytes() for path in files}
env = dict(os.environ, PYTHONPATH="src;tests;scripts", PYTHONDONTWRITEBYTECODE="1",
           PYTHONPYCACHEPREFIX=str(root / ".live19-revert-pycache"), PYTHONIOENCODING="utf-8")
try:
    for path in files:
        relative = path.relative_to(root).as_posix()
        path.write_bytes(subprocess.check_output(["git", "show", "eacb335d:" + relative], cwd=root))
    result = subprocess.run([sys.executable, "-m", "unittest", "tests.test_calibration_live19"],
                            cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
    (root / "reports/live19-revert-before.log").write_text(
        result.stdout + result.stderr, encoding="utf-8")
    print("single revert exit:", result.returncode)
    print(result.stdout)
    print(result.stderr[-12000:])
    if result.returncode == 0:
        raise AssertionError("new pins did not detect removal of the fix")
finally:
    for path, data in fixed.items():
        path.write_bytes(data)
    assert all(path.read_bytes() == data for path, data in fixed.items())
    print("all fixed production bytes restored")
