"""Record every public choose_key decision plus the town errand hold's answers.

usage: python -I replay_hold.py [--claim-row] <tree> <out.jsonl> <test id> [<test id> ...]

validation/manifest-tax-1101/replay_choose_key.py plus the hold's inputs that a
same key does not show (structure-s2-3): the decision_claim fields the cli town
fuse reads (claim_id, goal kind, distance) and the owner, the decision's
``_decision_errand_deferred`` rows, and every ``_defer_town_errand`` result and
errand hold answer (``_claim_errand_hold``: holder claim id and owner) since
the previous decision, each with its four nearest callers.  Calls a test makes after its last decision are written
as one more row with ordinal "end".  With --claim-row each decision row also
carries the whole decision_claim row (JSON, sorted keys), for a step that must
not change the recorded claim row either.  compare_hold.py compares the rows.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest

claim_row_wanted = sys.argv[1:2] == ['--claim-row']
if claim_row_wanted:
    del sys.argv[1]
tree = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sys.path[:0] = [str(tree / 'src'), str(tree / 'tests'), str(tree)]
os.chdir(tree)

from hengbot import policy as policy_module  # noqa: E402
from hengbot import town_work  # noqa: E402

Policy = policy_module.HengbotPolicy
original = Policy.choose_key
current = {'test': None, 'n': 0, 'calls': []}
stream = out.open('w', encoding='utf8', newline='\n')


def receipt_row(receipt):
    work = receipt.get('work') or {}
    return [receipt.get('seam'), receipt.get('producer'), receipt.get('valid'), receipt.get('reason'),
            work.get('producer'), work.get('rows'), work.get('delegation')]


def claim_row(claim):
    if not isinstance(claim, dict):
        return repr(claim)
    goal = claim.get('goal') or {}
    return [claim.get('claim_id'), claim.get('owner'), goal.get('kind') if isinstance(goal, dict) else repr(goal),
            claim.get('distance')]


def write(row):
    stream.write(json.dumps(row, ensure_ascii=False, default=repr) + '\n')


def record(policy, key):
    current['n'] += 1
    calls, current['calls'] = current['calls'], []
    write([current['test'], current['n'], key, getattr(policy, 'last_reason', None),
           [receipt_row(r) for r in town_work.receipts(policy)],
           claim_row(getattr(policy, 'decision_claim', None)),
           repr(getattr(policy, '_decision_errand_deferred', None)),
           *([json.dumps(getattr(policy, 'decision_claim', None), ensure_ascii=False, sort_keys=True, default=repr)]
             if claim_row_wanted else []),
           calls])


def flush_end():
    if current['test'] is not None and current['calls']:
        write([current['test'], 'end', None, None, [], None, None, current['calls']])
    current['calls'] = []


# Compiled under policy.py's file name: tests derive policy.py from choose_key.__code__.co_filename.
# Its frame returns after town_work_decision's observer has stopped, so nothing records it as work.
namespace = {'__name__': 'replay_hold', 'original': original, 'record': record}
exec(compile('def choose_key(self, snapshot):\n key = original(self, snapshot)\n record(self, key)\n'
             ' return key\n', policy_module.__file__, 'exec'), namespace)
Policy.choose_key = namespace['choose_key']

original_defer = Policy._defer_town_errand
original_hold = Policy._claim_errand_hold


def callers():
    # The four nearest calling functions, so a comparison can leave out the
    # calls of record-only code a step deleted (the S3.3 shadow verdict).
    names, frame = [], sys._getframe(2)
    while frame is not None and len(names) < 4:
        names.append(frame.f_code.co_name)
        frame = frame.f_back
    return names


def defer(self, family, reason, **kwargs):
    result = original_defer(self, family, reason, **kwargs)
    current['calls'].append(['defer', family, reason, repr(sorted(kwargs.items())), result, callers()])
    return result


def hold(self, family, **kwargs):
    result = original_hold(self, family, **kwargs)
    current['calls'].append(['hold', family, bool(kwargs.get('enforced')), kwargs.get('arrival_board') is not None,
                             None if result is None else [getattr(result, 'claim_id', None),
                                                          getattr(getattr(result, 'owner', None), 'value', None)],
                             callers()])
    return result


Policy._defer_town_errand = defer
Policy._claim_errand_hold = hold


class Result(unittest.TextTestResult):
    def startTest(self, test):
        flush_end()
        current.update(test=test.id(), n=0, calls=[])
        super().startTest(test)

    def stopTest(self, test):
        flush_end()
        super().stopTest(test)


suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:])
result = unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=sys.stderr).run(suite)
stream.close()
print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped))))
raise SystemExit(0 if result.wasSuccessful() else 1)
