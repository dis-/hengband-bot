"""Run the new pin once with only the live27 production hunk reverted."""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'src/hengbot/policy_town.py'
original = path.read_bytes()
start = original.index(b'                if (\n                    self._planned_depth() >= STAFF_IDENTIFY_MIN_DEPTH', original.index(b'                supplier = self._departure_supplier_counterfactual(snapshot)'))
end = original.index(b'                self._town_blocked_reason = "departure-unsatisfiable"', start)
try:
    path.write_bytes(original[:start] + original[end:])
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONPATH='src;tests;scripts')
    result = subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_identify_staff_live27_recorded'], cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8')
    output = result.stdout + result.stderr
    print(output)
    (ROOT / 'reports/live27-revert.txt').write_text(output, encoding='utf-8', newline='\n')
    assert result.returncode == 1
    assert 'town:blocked:departure-unsatisfiable' in output
    assert 'FAILED (failures=1)' in output
finally:
    path.write_bytes(original)
print('Single revert rejected by the recorded pin; production hunk restored.')
