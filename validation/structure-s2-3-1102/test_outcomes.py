"""Write each test's outcome (ok / FAIL / ERROR / skip, with the first message line) for a tree.

usage: python -I test_outcomes.py <tree> <out.json> <test id> [<test id> ...]
Used to compare the recorded Home-window tests before and after a step.
"""
import json
import os
from pathlib import Path
import sys
import unittest

tree = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sys.path[:0] = [str(tree / 'src'), str(tree / 'tests'), str(tree / 'scripts'), str(tree)]
os.chdir(tree)
outcomes = {}


def first_line(err):
    return str(err[1]).strip().splitlines()[0][:200] if str(err[1]).strip() else type(err[1]).__name__


class Result(unittest.TextTestResult):
    def addSuccess(self, test):
        outcomes.setdefault(test.id(), 'ok')
        super().addSuccess(test)

    def addFailure(self, test, err):
        outcomes[test.id()] = 'FAIL: ' + first_line(err)
        super().addFailure(test, err)

    def addError(self, test, err):
        outcomes[test.id()] = 'ERROR: ' + first_line(err)
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            kind = 'FAIL' if issubclass(err[0], test.failureException) else 'ERROR'
            outcomes[subtest.id()] = f'{kind}: ' + first_line(err)
        super().addSubTest(test, subtest, err)

    def addSkip(self, test, reason):
        outcomes[test.id()] = 'skip'
        super().addSkip(test, reason)


suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:])
unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=sys.stderr).run(suite)
out.write_text(json.dumps(outcomes, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf8')
print(json.dumps({'tests': len(outcomes), 'ok': sum(v == 'ok' for v in outcomes.values())}))
