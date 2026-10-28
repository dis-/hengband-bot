"""Import one complete module, preserving the repository's named hang exclusion."""
import importlib
import json
from pathlib import Path
import sys
import time
import unittest

module = sys.argv[1]
suite = unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(module))


def cases(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from cases(case)
        elif not case.id().startswith('tests.test_cli.DecisionTimingTest.'):
            yield case


started = time.monotonic()
result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(cases(suite)))
data = dict(module=module, ran=result.testsRun, skipped=len(result.skipped),
            failures=[case.id() for case, _ in result.failures],
            errors=[case.id() for case, _ in result.errors],
            seconds=round(time.monotonic() - started, 3))
Path(sys.argv[2]).write_text(json.dumps(data, indent=2), encoding='utf-8')
raise SystemExit(not result.wasSuccessful())
