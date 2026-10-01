"""One Class C2 revert experiment plus the requested b24fd077 seam replay."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "src/hengbot" / name for name in
         ("policy.py", "policy_calibration.py", "policy_equipment.py",
          "policy_shop.py", "policy_town.py")]


def main():
    saved = {path: path.read_bytes() for path in FILES}
    env = dict(os.environ, PYTHONPATH="src;tests;scripts")
    cache = TemporaryDirectory(prefix="classC2-revert-cache-")
    # Each source version gets a separate bytecode cache. The restore cannot
    # accidentally reuse a same-second cache compiled from the other version.
    env["PYTHONPYCACHEPREFIX"] = str(Path(cache.name) / "baseline")
    output = []
    try:
        for path in FILES:
            path.write_bytes(subprocess.check_output([
                "git", "show", "b24fd077:" + path.relative_to(ROOT).as_posix()], cwd=ROOT))
        probe = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from test_classC2_departure_recorded import *
with TemporaryDirectory() as directory:
    policy, board, capture = attachment(Path(directory))
    key = policy.choose_key(board)
    pair = (str(key), policy.last_reason)
    failed = policy._departure_block['failed']
    print('BASELINE b24fd077', pair, failed, 'target', policy._target_dungeon_id)
    assert pair == ('1', 'town:blocked:departure-unsatisfiable'), pair
    assert failed == ['inventory_weight_ready', 'recall_landing_not_guardian_blocked'], failed
'''
        probe_path = Path(cache.name) / "baseline_probe.py"
        probe_path.write_text(probe, encoding="utf8")
        baseline = subprocess.run([sys.executable, str(probe_path)], cwd=ROOT,
            env=env, capture_output=True, text=True, encoding="utf8")
        output.append(baseline.stdout + baseline.stderr)
        if baseline.returncode:
            raise RuntimeError("b24fd077 baseline did not reproduce the stop")
        for path, content in saved.items():
            path.write_bytes(content)
        town = ROOT / "src/hengbot/policy_town.py"
        town.write_bytes(subprocess.check_output([
            "git", "show", "e8824223:src/hengbot/policy_town.py"], cwd=ROOT))
        env["PYTHONPYCACHEPREFIX"] = str(Path(cache.name) / "reverted")
        reverted = subprocess.run([sys.executable, "-m", "unittest",
            "tests.test_classC2_departure_recorded"], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding="utf8")
        output.append("SINGLE REVERT e8824223 town runtime\n" + reverted.stdout + reverted.stderr)
        if reverted.returncode == 0 or "FAILED (failures=2)" not in reverted.stderr:
            raise RuntimeError("revert must fail exactly the remedy and no-alternate pins")
    finally:
        for path, content in saved.items():
            path.write_bytes(content)
        output.append("All five runtime files restored byte-for-byte.\n")
        cache.cleanup()
        (ROOT / "reports/classC2-single-revert.txt").write_text("\n".join(output), encoding="utf8")
        print("\n".join(output))


if __name__ == "__main__":
    main()
