"""Show which individual pins fail with exactly the source change reverted."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    sys.path.insert(0, r"C:\hengband-backups\guard-tools")
    from gate_lock import wait_for_gate
    wait_for_gate("dump-pin-reversion")
    path = Path("src/hengbot/input_executor.py")
    current = path.read_bytes()
    assert current.replace(b"\r\n", b"\n") == subprocess.check_output(
        ["git", "show", f"HEAD:{path.as_posix()}"])
    baseline = subprocess.check_output(["git", "show", f"main:{path.as_posix()}"])
    assert baseline != current
    runner = """
import json, unittest
__file__ = 'validation/me-dump-stuck-1029/revert_pins.py'
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_character_dump_more_recorded')
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('PIN_RESULTS=' + json.dumps(dict(tests=result.testsRun,
    failures=[t.id() for t, _ in result.failures], errors=[t.id() for t, _ in result.errors])))
"""
    try:
        path.write_bytes(baseline)
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", runner],
                                capture_output=True, text=True, encoding="utf-8", timeout=120)
    finally:
        path.write_bytes(current)
    log = result.stdout + result.stderr
    Path("validation/me-dump-stuck-1029/revert-pins.log").write_text(log, encoding="utf-8")
    row = next(line for line in result.stdout.splitlines() if line.startswith("PIN_RESULTS="))
    evidence = json.loads(row.partition("=")[2])
    assert evidence["tests"] == 5 and not evidence["errors"], evidence
    failed = {name.split(" (")[0].rsplit(".", 1)[-1] for name in evidence["failures"]}
    assert failed == {
        "test_public_choose_and_follow_replay_both_linux_stops_to_map",
        "test_first_dump_without_existing_file_still_owns_success_more",
        "test_centered_more_uses_same_rendered_origin_in_both_languages",
    }, evidence
    print(json.dumps(evidence, ensure_ascii=False))
    print("Each repaired path fails on reversion; the original warrior control stays green.")


if __name__ == "__main__":
    main()
