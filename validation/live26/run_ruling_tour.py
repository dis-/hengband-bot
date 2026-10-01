"""Run the explicitly authorized tour module and preserve ownership evidence."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_unaffordable_claim_tour_recorded import UnaffordableClaimTourRecordedTest as T
from hengbot.ownership_metrics import gate_numbers
from tour_probe import summarize
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
rows = T.claim_rows or []
summary = summarize(rows)
summary['endings'] = gate_numbers(rows)['endings']
summary['tests'] = result.testsRun
summary['failures'] = len(result.failures)
summary['errors'] = len(result.errors)
(ROOT / 'validation/live26/ruling-tour-summary.json').write_text(json.dumps(summary, indent=2, default=str), encoding='utf8')
raise SystemExit(0 if result.wasSuccessful() else 1)
