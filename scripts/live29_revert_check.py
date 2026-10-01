"""Run the short recorded r14 pin with only the live29 gate fix reverted."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'src/hengbot/policy_shop.py'
original = path.read_bytes()
fixed = (b'        if (not self._town_gate_exempt(writer_family, travel_reason, snapshot)\n'
         b'                and self._defer_town_errand(writer_family, "shopping-approach")):\n')
old = b'        if self._defer_town_errand(writer_family, "shopping-approach"):\n'
assert original.count(fixed) == 1
try:
    path.write_bytes(original.replace(fixed, old, 1))
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONPATH='src;tests;scripts')
    result = subprocess.run([
        sys.executable, '-m', 'unittest',
        'tests.test_declarations_r14.DeclarationR14Test.'
        'test_recorded_router_entry_keeps_its_declared_wait_through_detector_repair',
    ], cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf8')
    output = result.stdout + result.stderr
    (ROOT / 'reports/live29-revert.txt').write_text(output, encoding='utf8', newline='\n')
    print(output)
    assert result.returncode == 1
    assert "None != '2'" in output
    assert 'FAILED (failures=2)' in output
finally:
    path.write_bytes(original)
print('Single revert rejected by both ON checkpoint cases; source restored.')
