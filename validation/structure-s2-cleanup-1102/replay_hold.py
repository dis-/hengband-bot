"""Record every public choose_key decision plus the town hold it leaves behind.

usage: python -I replay_hold.py [--claim-row] <tree> <out.jsonl> <test id> [<test id> ...]

structure-s2-4-1102/replay_hold.py; the hold's functions are read from
``town_hold`` when the tree has it (structure-s2-cleanup moves the hold out
of town_terminal), else from ``town_terminal``.  Made independent of where the
hold's code lives (structure-s2-4 moved it from the policy into town_terminal
and deleted the decision_claim row):

* the errand hold is wrapped at its function, ``town_terminal.errand_hold``,
  and every module global bound to it, so a call counts once whether it
  comes through the policy's delegate or straight from town_terminal;
* each decision row carries the cli town fuse's input -- ``(claim_id,
  distance)`` of the decision's Reach claim -- from
  ``town_terminal.decision_reach`` when it exists, else from the
  decision_claim row (the same values before slice 4 step 2);
* each decision row carries a digest of the hold's state after the decision:
  the standing claim (id, owner, goal, state, closed, execution), the
  suspended stack, the bars and the delegations, read by attribute so that
  the record type may change while the values must not.

Each failing, erroring or skipped test (and subtest) also gets an "outcome"
row with the first line of its message, so a comparison also shows a changed
test result.

With --claim-row the whole decision_claim row is added as well (only for a
step that keeps the row).  compare_hold.py compares the rows.
"""
from __future__ import annotations

import json
import os
import re
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
try:  # noqa: E402
    from hengbot import town_hold as hold_module
except ImportError:  # a tree before the hold moved to its own module
    from hengbot import town_terminal as hold_module
from hengbot import town_work  # noqa: E402

Policy = policy_module.HengbotPolicy
original = Policy.choose_key
current = {'test': None, 'n': 0, 'calls': []}
stream = out.open('w', encoding='utf8', newline='\n')


def receipt_row(receipt):
    work = receipt.get('work') or {}
    return [receipt.get('seam'), receipt.get('producer'), receipt.get('valid'), receipt.get('reason'),
            work.get('producer'), work.get('rows'), work.get('delegation')]


def value(item):
    return getattr(item, 'value', item)


def goal_row(goal):
    if goal is None:
        return None
    return [getattr(goal, name, None) for name in ('kind', 'cell', 'monster', 'place', 'expectation',
                                                    'within', 'effect', 'source')]


def execution_row(execution):
    if execution is None:
        return None
    return [getattr(execution, name, None) for name in (
        'producer', 'work_id', 'state', 'next_step', 'arguments', 'expected_effect', 'continuation',
        'budget_ref', 'operation_ref')]


def claim_digest(claim):
    if claim is None:
        return None
    return [getattr(claim, 'claim_id', None), value(getattr(claim, 'owner', None)),
            goal_row(getattr(claim, 'goal', None)), value(getattr(claim, 'state', None)),
            getattr(claim, 'closed', None), getattr(claim, 'closed_reason', None),
            getattr(claim, 'non_discardable', None), getattr(claim, 'rank', None),
            getattr(claim, 'rung', None), getattr(claim, 'floor', None),
            execution_row(getattr(claim, 'execution', None))]


def bar_digest(bar):
    return [value(getattr(bar, 'owner', None)), goal_row(getattr(bar, 'goal', None)),
            getattr(bar, 'kind', None), getattr(bar, 'ending', None),
            getattr(bar, 'trigger_monsters', None), getattr(bar, 'clearance', None),
            getattr(bar, 'hold', None)]


def delegation_digest(record):
    return [getattr(record, name, None) for name in (
        'parent_claim_id', 'parent_family', 'delegate_family', 'work_identity', 'purpose_identity',
        'opening_decision', 'expected_effect', 'budget_reference', 'lifecycle', 'ending')]


def hold_digest(policy):
    hold = getattr(policy, '_town_hold', None)
    claims = getattr(hold, 'claims', None)
    if hold is None:
        return None
    return [claim_digest(getattr(claims, 'current', None)),
            [claim_digest(claim) for claim in getattr(claims, 'suspended', ())],
            [bar_digest(bar) for bar in getattr(claims, 'bars', ())],
            [delegation_digest(record) for record in getattr(hold, 'delegations', ())]]


def fuse_row(policy):
    reach = getattr(hold_module, 'decision_reach', None)
    if reach is not None:
        found = reach(policy)
        return list(found) if found is not None else None
    claim = getattr(policy, 'decision_claim', None) or {}
    goal = claim.get('goal') or {}
    return ([claim.get('claim_id'), claim['distance']]
            if goal.get('kind') == 'Reach' and isinstance(claim.get('distance'), int) else None)


def write(row):
    stream.write(json.dumps(row, ensure_ascii=False, default=repr) + '\n')


def record(policy, key):
    current['n'] += 1
    calls, current['calls'] = current['calls'], []
    write([current['test'], current['n'], key, getattr(policy, 'last_reason', None),
           [receipt_row(r) for r in town_work.receipts(policy)],
           [fuse_row(policy), hold_digest(policy)],
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
original_hold = hold_module.errand_hold


def callers():
    # The four nearest calling functions, so a comparison can leave out the
    # calls of record-only code a step deleted.
    names, frame = [], sys._getframe(2)
    while frame is not None and len(names) < 4:
        names.append(frame.f_code.co_name)
        frame = frame.f_back
    return names


def defer(self, family, reason, **kwargs):
    result = original_defer(self, family, reason, **kwargs)
    current['calls'].append(['defer', family, reason, repr(sorted(kwargs.items())), result, callers()])
    return result


def hold(policy, family, **kwargs):
    result = original_hold(policy, family, **kwargs)
    current['calls'].append(['hold', family, bool(kwargs.get('enforced')), kwargs.get('arrival_board') is not None,
                             None if result is None else [getattr(result, 'claim_id', None),
                                                          getattr(getattr(result, 'owner', None), 'value', None)],
                             callers()])
    return result


Policy._defer_town_errand = defer


def wrap_hold():
    # Every module global bound to the errand hold (modules a test imports
    # later too: this runs again before each test).
    for module in list(sys.modules.values()):
        if getattr(module, '__name__', '').startswith('hengbot'):
            for name, bound in list(vars(module).items()):
                if bound is original_hold:
                    setattr(module, name, hold)


wrap_hold()


def outcome(test_id, status, err=None):
    message = ''
    if err is not None:
        text = str(err[1]).strip()
        message = text.splitlines()[0][:200] if text else type(err[1]).__name__
        # Object addresses differ between processes.
        message = re.sub(r'0x[0-9a-fA-F]+', '0x?', message)
    write([test_id, 'outcome', status, message, [], None, 'None', []])


class Result(unittest.TextTestResult):
    def addFailure(self, test, err):
        outcome(test.id(), 'FAIL', err)
        super().addFailure(test, err)

    def addError(self, test, err):
        outcome(test.id(), 'ERROR', err)
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            outcome(subtest.id(), 'FAIL' if issubclass(err[0], test.failureException) else 'ERROR', err)
        super().addSubTest(test, subtest, err)

    def addSkip(self, test, reason):
        outcome(test.id(), 'skip')
        super().addSkip(test, reason)

    def startTest(self, test):
        flush_end()
        wrap_hold()
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
