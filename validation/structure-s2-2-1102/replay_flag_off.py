"""Record every public choose_key decision the given tests make, for a main/branch comparison.

usage: python -I replay_choose_key.py <tree> <out.jsonl> <test id> [<test id> ...]

<tree> is a checkout (or an exported copy) with src/ and tests/. Each line of
<out.jsonl> is one decision: test id, ordinal, key, last_reason and the town-work
receipts of that decision (seam, producer, valid, reason, work producer/rows).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest

tree = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
sys.path[:0] = [str(tree / 'src'), str(tree / 'tests'), str(tree)]
os.chdir(tree)

from hengbot import policy as policy_module  # noqa: E402
from hengbot import town_work  # noqa: E402

original = policy_module.HengbotPolicy.choose_key
# structure-s2-2: the live setting -- the S3.3 town-claim switch reads False and ignores writes.
policy_module.HengbotPolicy._town_claim_bar_enforced = property(lambda self: False, lambda self, value: None)
current = {'test': None, 'n': 0}
stream = out.open('w', encoding='utf8', newline='\n')


def receipt_row(receipt):
    work = receipt.get('work') or {}
    return [receipt.get('seam'), receipt.get('producer'), receipt.get('valid'), receipt.get('reason'),
            work.get('producer'), work.get('rows'), work.get('delegation')]


def record(policy, key):
    current['n'] += 1
    stream.write(json.dumps([current['test'], current['n'], key, getattr(policy, 'last_reason', None),
                             [receipt_row(r) for r in town_work.receipts(policy)]],
                            ensure_ascii=False, default=repr) + '\n')


# Compiled under policy.py's file name: tests derive policy.py from choose_key.__code__.co_filename.
# Its frame returns after town_work_decision's observer has stopped, so nothing records it as work.
namespace = {'__name__': 'replay_choose_key', 'original': original, 'record': record}
exec(compile('def choose_key(self, snapshot):\n key = original(self, snapshot)\n record(self, key)\n'
             ' return key\n', policy_module.__file__, 'exec'), namespace)
policy_module.HengbotPolicy.choose_key = namespace['choose_key']


class Result(unittest.TextTestResult):
    def startTest(self, test):
        current.update(test=test.id(), n=0)
        super().startTest(test)


suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:])
result = unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=sys.stderr).run(suite)
stream.close()
print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped))))
raise SystemExit(0 if result.wasSuccessful() else 1)
